"""One call to the model by an OpenAI-compatible API, its first two checks and its retry
(docs/fiches-veille.md, "Contrôles" and "États nommés").

A call sends the system prompt of a stage, a module constant, and its data, encoded in JSON in
the user message, the only place where a text of a source goes (.claude/rules/poc.md, rule 8).
The output is checked before any use: its finish_reason (check 1), its schema (check 2), then the
checks of the stage (3 to 6, #205 and #206). At most one retry per call: after an output
refused, with the constant reminder of the check that refused it; after a 429, a 5xx or a failed
connection, after waiting Retry-After. Nothing is logged here: the caller handles the state, and
logs it once, with the measures of the call.

The HTTP client is httpx2 alone, not the SDK of a provider (ADR of 2026-10-15, "Appel du
modèle"): changing it later changes this module, behind call_model and LlmCall.
"""

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Annotated, Literal, get_args

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from k_b.ai_api.connectors.llm_replay import ReplayTransport
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.connectors.outbound import open_http_client
from k_b.ai_api.deadline import Deadline
from k_b.core.config import (
    LLM_CALL_TIMEOUT_SECONDS,
    LLM_CONNECT_TIMEOUT_SECONDS,
    LLM_POOL_TIMEOUT_SECONDS,
    LLM_RETRY_AFTER_MAX_SECONDS,
    LLM_RETRY_WAIT_SECONDS,
    LLM_WRITE_TIMEOUT_SECONDS,
    MAX_TOKENS_READ_PER_ANSWER,
)

# Relative to the base URL, which keeps its path (/openai/v1, /v1).
CHAT_COMPLETIONS_PATH = "chat/completions"
PROMPT_CACHE_OFF: Mapping[str, str] = {"mode": "explicit"}

# The states of a call that failed (docs/fiches-veille.md, "États nommés"); a call is ok or one
# of them.
type LlmFailure = Literal[
    "llm_invalid_output",
    "llm_truncated",
    "llm_content_filtered",
    "llm_rate_limited",
    "llm_unavailable",
    "llm_timeout",
]
type LlmOutcome = Literal["ok"] | LlmFailure
# The check that refused the output (docs/fiches-veille.md, "Contrôles"); 1 and 2 here, 3 to 6
# by the stage.
type FailedCheck = Literal[
    "content_filter",
    "finish_reason",
    "schema",
    "subject",
    "item_id",
    "completeness",
    "markup",
]
FAILED_CHECKS: tuple[FailedCheck, ...] = get_args(FailedCheck.__value__)
# The delay-seconds form of Retry-After (RFC 9110, § 10.2.3), compared to the maximum. Its
# HTTP-date form, rare, is read as no header. Read up to 9 digits, about 31 years: int() refuses
# 4,301 digits or more, and a longer value is a wait beyond any maximum (review of #156).
MAX_RETRY_AFTER_DIGITS = 9
RETRY_AFTER_SECONDS = re.compile(rf"[0-9]{{1,{MAX_RETRY_AFTER_DIGITS}}}")
RETRY_AFTER_TOO_LONG = re.compile(rf"[0-9]{{{MAX_RETRY_AFTER_DIGITS + 1},}}")
# A finish_reason is read whatever its length, and cut to this length in the call: it goes to a
# metric line.
MAX_FINISH_REASON_LENGTH = 64


class EnvelopeModel(BaseModel):
    """The envelope a provider gives around the output: the fields read are typed, the others
    ignored, since a provider adds its own (Azure: the results of its content filter). The
    output of the model, inside, is the one that refuses a field in excess."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class Message(EnvelopeModel):
    content: str | None = None


class Choice(EnvelopeModel):
    message: Message
    # Null or out of the list: refused by check 1, not by the envelope.
    finish_reason: str | None = None


# A token count of the provider, bounded: beyond, the answer is not read.
type TokenCount = Annotated[int, Field(ge=0, le=MAX_TOKENS_READ_PER_ANSWER)]


class CompletionTokensDetails(EnvelopeModel):
    reasoning_tokens: TokenCount | None = None


class Usage(EnvelopeModel):
    prompt_tokens: TokenCount
    completion_tokens: TokenCount
    completion_tokens_details: CompletionTokensDetails | None = None


class ChatCompletion(EnvelopeModel):
    choices: list[Choice] = Field(min_length=1)
    usage: Usage | None = None


class ErrorDetail(EnvelopeModel):
    code: str | None = None


class ErrorBody(EnvelopeModel):
    """The error of a 4xx: its code only, the rest neither kept nor logged, since its message
    may quote the input."""

    error: ErrorDetail


@dataclass(frozen=True)
class LlmCall[OutputT: BaseModel]:
    """A call, its outcome and its measures, never a text: the output, checked, only when the
    outcome is ok. The tokens are those of both attempts; the other measures are those of the
    last one: a Retry-After waited before a retry is not kept, llm_ms counts its wait."""

    outcome: LlmOutcome
    output: OutputT | None
    attempts: int
    finish_reason: str | None
    schema_valid: bool
    failed_check: FailedCheck | None
    # The check that refused the first attempt, when a second one followed; None otherwise.
    first_failed_check: FailedCheck | None
    tokens_in: int
    tokens_out: int
    reasoning_tokens: int | None
    input_chars: int
    # The attempts and the wait between them: the time of the call, seen by the request.
    llm_ms: int
    check_ms: int
    retry_after_seconds: int | None
    # None when no answer came: a timeout, a failed connection.
    http_status: int | None
    # Whether an attempt got a 429: a retry that times out, gets a 5xx or is cut by the deadline
    # does not erase it. After a call that failed with one, the request sends nothing more; a
    # retry answered after its Retry-After got past it, and the next calls go.
    saw_rate_limit: bool


@dataclass(frozen=True)
class Attempt[OutputT: BaseModel]:
    """One request and the checks of its answer."""

    outcome: LlmOutcome
    output: OutputT | None = None
    finish_reason: str | None = None
    schema_valid: bool = False
    failed_check: FailedCheck | None = None
    usage: Usage | None = None
    check_seconds: float = 0.0
    retry_after_seconds: int | None = None
    http_status: int | None = None
    # None: no retry. 0: a retry at once, after an output refused; else the wait before it.
    retry_wait_seconds: float | None = None


def to_failure(outcome: LlmOutcome) -> LlmFailure:
    """The failure of a call without output: ok there is a fault of the caller, raised."""
    if outcome == "ok":
        raise ValueError("a call without output is not ok")
    return outcome


def build_http_client(
    settings: LlmSettings, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    """The client of the provider of the settings, or of its replay, on the steps read with the
    settings, when no transport is given. The rules of open_http_client apply, and the transport
    makes no retry of its own."""
    if transport is None and settings.provider == "replay":
        if settings.replay_steps is None:
            raise ValueError("replay settings without replay steps")
        transport = ReplayTransport(list(settings.replay_steps))
    headers = (
        {}
        if settings.api_key is None
        else {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}
    )
    return open_http_client(
        settings.base_url,
        headers,
        httpx2.Timeout(
            connect=LLM_CONNECT_TIMEOUT_SECONDS,
            read=LLM_CALL_TIMEOUT_SECONDS,
            write=LLM_WRITE_TIMEOUT_SECONDS,
            pool=LLM_POOL_TIMEOUT_SECONDS,
        ),
        transport,
    )


def call_model[OutputT: BaseModel](
    http_client: httpx2.Client,
    settings: LlmSettings,
    *,
    system_prompt: str,
    user_data: Mapping[str, object],
    output_model: type[OutputT],
    json_schema: Mapping[str, object],
    schema_name: str,
    max_completion_tokens: int,
    check_output: Callable[[OutputT], FailedCheck | None],
    retry_reminders: Mapping[FailedCheck, str],
    deadline: Deadline | None,
    sleep: Callable[[float], None] = time.sleep,
) -> LlmCall[OutputT]:
    """Ask the model for an output of output_model, check it, and ask once more if the first
    answer may change on a retry. retry_reminders holds one reminder per check: one missing is a
    fault of the caller, raised before any request is paid.

    With a deadline, the timeouts of each request are shortened to the time left, and a retry
    that would not have the time it needs is not made: the call ends in llm_timeout, what the
    first attempt observed kept. The caller checks the deadline before the call."""
    missing_reminders = [c for c in FAILED_CHECKS if c not in retry_reminders]
    if missing_reminders:
        raise ValueError(f"retry_reminders without: {', '.join(missing_reminders)}")
    user_message = encode_user_message(user_data)
    started = time.perf_counter()

    def ask(prompt: str) -> Attempt[OutputT]:
        body = build_request_body(
            settings,
            prompt,
            user_message,
            json_schema,
            schema_name,
            max_completion_tokens,
        )
        timeout = (
            http_client.timeout
            if deadline is None
            else deadline.cap(http_client.timeout)
        )
        return send_and_check(http_client, body, output_model, check_output, timeout)

    attempts = [ask(system_prompt)]
    first = attempts[0]
    if (
        first.retry_wait_seconds is not None
        and deadline is not None
        and not deadline.allows_llm_request(first.retry_wait_seconds)
    ):
        call = summarize(attempts, len(user_message), time.perf_counter() - started)
        return replace(call, outcome="llm_timeout", output=None)
    if first.retry_wait_seconds is not None:
        if first.failed_check is None:
            sleep(first.retry_wait_seconds)
            attempts.append(ask(system_prompt))
        else:
            attempts.append(
                ask(f"{system_prompt}\n\n{retry_reminders[first.failed_check]}")
            )
    elapsed_seconds = time.perf_counter() - started
    return summarize(attempts, len(user_message), elapsed_seconds)


def encode_user_message(user_data: Mapping[str, object]) -> str:
    """The user message: the data of the stage in JSON, its text unescaped. Its length is the
    input_chars of the call, which the batches of the classification bound."""
    return json.dumps(user_data, ensure_ascii=False, allow_nan=False)


def build_request_body(
    settings: LlmSettings,
    system_prompt: str,
    user_message: str,
    json_schema: Mapping[str, object],
    schema_name: str,
    max_completion_tokens: int,
) -> dict[str, object]:
    body: dict[str, object] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": json_schema},
        },
        "max_completion_tokens": max_completion_tokens,
        # Explicit mode without a breakpoint: no prompt cache written, so the items are not kept
        # for its 30 minutes or more (GPT-5.6 and later cache the last message by default;
        # docs/registre-traitements.md). A model before GPT-5.6 refuses the field with a 400.
        "prompt_cache_options": PROMPT_CACHE_OFF,
    }
    # A reasoning model takes no temperature (docs/fiches-veille.md, "Réglages d'appel").
    if settings.reasoning_effort is None:
        body["temperature"] = 0
    else:
        body["reasoning_effort"] = settings.reasoning_effort
    return body


def send_and_check[OutputT: BaseModel](
    http_client: httpx2.Client,
    body: dict[str, object],
    output_model: type[OutputT],
    check_output: Callable[[OutputT], FailedCheck | None],
    timeout: httpx2.Timeout,
) -> Attempt[OutputT]:
    """One request: the state of a failure of the provider, or the checks of its completion."""
    try:
        response = http_client.post(CHAT_COMPLETIONS_PATH, json=body, timeout=timeout)
    except httpx2.TimeoutException:
        return Attempt(outcome="llm_timeout")
    except httpx2.TransportError:
        return Attempt(
            outcome="llm_unavailable", retry_wait_seconds=LLM_RETRY_WAIT_SECONDS
        )
    except httpx2.RequestError:
        # An answer that cannot be read (a body badly encoded): the same answer again.
        return Attempt(outcome="llm_unavailable")
    attempt = read_answer(response, output_model, check_output)
    return replace(attempt, http_status=response.status_code)


def read_answer[OutputT: BaseModel](
    response: httpx2.Response,
    output_model: type[OutputT],
    check_output: Callable[[OutputT], FailedCheck | None],
) -> Attempt[OutputT]:
    if response.status_code != httpx2.codes.OK:
        return read_failure(response)
    try:
        completion = ChatCompletion.model_validate_json(response.content)
    except ValidationError:
        return Attempt(outcome="llm_unavailable")
    return check_completion(completion, output_model, check_output)


def read_failure[OutputT: BaseModel](response: httpx2.Response) -> Attempt[OutputT]:
    """The state of an answer other than 200: a 429 or a 5xx gets a wait before a retry, none
    when Retry-After is above the maximum (wait_or_end); a 400 of a prompt filtered is not
    retried; any other is a provider that cannot answer this request."""
    status = response.status_code
    if status == httpx2.codes.TOO_MANY_REQUESTS:
        return wait_or_end(response, "llm_rate_limited")
    if status >= httpx2.codes.INTERNAL_SERVER_ERROR:
        return wait_or_end(response, "llm_unavailable")
    if (
        status == httpx2.codes.BAD_REQUEST
        and read_error_code(response) == "content_filter"
    ):
        return Attempt(outcome="llm_content_filtered", failed_check="content_filter")
    return Attempt(outcome="llm_unavailable")


def wait_or_end[OutputT: BaseModel](
    response: httpx2.Response, outcome: LlmOutcome
) -> Attempt[OutputT]:
    """A retry after Retry-After, or after the default wait without it; none when Retry-After
    is above the maximum, since a shorter wait would give the same answer."""
    value = response.headers.get("Retry-After")
    if value is not None and RETRY_AFTER_TOO_LONG.fullmatch(value):
        # Too long to read: a wait beyond the maximum, whose value is not given back.
        return Attempt(outcome=outcome)
    retry_after = read_retry_after(response)
    if retry_after is not None and retry_after > LLM_RETRY_AFTER_MAX_SECONDS:
        return Attempt(outcome=outcome, retry_after_seconds=retry_after)
    wait = LLM_RETRY_WAIT_SECONDS if retry_after is None else retry_after
    return Attempt(
        outcome=outcome, retry_after_seconds=retry_after, retry_wait_seconds=wait
    )


def read_retry_after(response: httpx2.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None or not RETRY_AFTER_SECONDS.fullmatch(value):
        return None
    return int(value)


def read_error_code(response: httpx2.Response) -> str | None:
    try:
        return ErrorBody.model_validate_json(response.content).error.code
    except ValidationError:
        return None


def check_completion[OutputT: BaseModel](
    completion: ChatCompletion,
    output_model: type[OutputT],
    check_output: Callable[[OutputT], FailedCheck | None],
) -> Attempt[OutputT]:
    """Checks 1 and 2, then those of the stage, in this order; the first refusal names the
    failure. Neither the output refused nor its ValidationError is kept (poc.md, rule 5)."""
    started = time.perf_counter()
    choice = completion.choices[0]
    finish_reason = (
        None
        if choice.finish_reason is None
        else choice.finish_reason[:MAX_FINISH_REASON_LENGTH]
    )

    def refuse(
        outcome: LlmOutcome,
        failed_check: FailedCheck | None,
        is_retried: bool,
        schema_valid: bool = False,
    ) -> Attempt[OutputT]:
        return Attempt(
            outcome=outcome,
            finish_reason=finish_reason,
            schema_valid=schema_valid,
            failed_check=failed_check,
            usage=completion.usage,
            check_seconds=time.perf_counter() - started,
            retry_wait_seconds=0 if is_retried else None,
        )

    # The same input to the same model most often gives the same output (determinism is not
    # guaranteed): a retry of a truncated or of a filtered output would most often give it again.
    if finish_reason == "length":
        return refuse("llm_truncated", None, is_retried=False)
    if finish_reason == "content_filter":
        return refuse("llm_content_filtered", "content_filter", is_retried=False)
    if finish_reason != "stop":
        return refuse("llm_invalid_output", "finish_reason", is_retried=True)
    if choice.message.content is None:
        return refuse("llm_invalid_output", "schema", is_retried=True)
    try:
        output = output_model.model_validate_json(choice.message.content, strict=True)
    except ValidationError:
        return refuse("llm_invalid_output", "schema", is_retried=True)
    failed_check = check_output(output)
    if failed_check is not None:
        return refuse(
            "llm_invalid_output", failed_check, is_retried=True, schema_valid=True
        )
    return Attempt(
        outcome="ok",
        output=output,
        finish_reason=finish_reason,
        schema_valid=True,
        usage=completion.usage,
        check_seconds=time.perf_counter() - started,
    )


def summarize[OutputT: BaseModel](
    attempts: list[Attempt[OutputT]], input_chars: int, elapsed_seconds: float
) -> LlmCall[OutputT]:
    """The call: the state of its last attempt, the tokens of both."""
    last = attempts[-1]
    usages = [attempt.usage for attempt in attempts if attempt.usage is not None]
    reasoning = [
        usage.completion_tokens_details.reasoning_tokens
        for usage in usages
        if usage.completion_tokens_details is not None
        and usage.completion_tokens_details.reasoning_tokens is not None
    ]
    check_seconds = sum(attempt.check_seconds for attempt in attempts)
    return LlmCall(
        outcome=last.outcome,
        output=last.output,
        attempts=len(attempts),
        finish_reason=last.finish_reason,
        schema_valid=last.schema_valid,
        failed_check=last.failed_check,
        first_failed_check=attempts[0].failed_check if len(attempts) == 2 else None,
        tokens_in=sum(usage.prompt_tokens for usage in usages),
        tokens_out=sum(usage.completion_tokens for usage in usages),
        reasoning_tokens=sum(reasoning) if reasoning else None,
        input_chars=input_chars,
        llm_ms=round((elapsed_seconds - check_seconds) * 1000),
        check_ms=round(check_seconds * 1000),
        retry_after_seconds=last.retry_after_seconds,
        http_status=last.http_status,
        saw_rate_limit=any(
            attempt.outcome == "llm_rate_limited" for attempt in attempts
        ),
    )
