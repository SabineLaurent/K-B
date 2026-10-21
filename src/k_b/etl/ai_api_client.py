"""The request of kb digest to the AI API: its settings, POST /digests, and the response it accepts
(docs/fiches-veille.md, "Réponse", "États nommés"; #209).

The AI API is reached by HTTP, never by its code: etl does not import ai_api. The response is an
input not trusted (OWASP API10:2023, LLM10): it is read by a closed schema, then its subjects and
its sources are checked against the closed lists, before any sheet is written. A failure is a named
state, raised as an AiApiError; nothing is logged here: kb digest logs it once. No retry, no wait
on a Retry-After. The body is read without a bound on its size (risk accepted by Sabine for the
POC, 2026-10-21: the service of K-B, at an address she sets).
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal, NoReturn

import httpx2
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
)

from k_b.core.api_keys import AI_API_KEY_VARIABLE_PREFIX, find_api_key_refusal
from k_b.core.api_request_log import REQUEST_ID_HEADER
from k_b.core.config import (
    AI_API_CONNECT_TIMEOUT_SECONDS,
    AI_API_POOL_TIMEOUT_SECONDS,
    AI_API_READ_TIMEOUT_SECONDS,
    AI_API_URL,
    AI_API_WRITE_TIMEOUT_SECONDS,
    MODEL_NAME,
)
from k_b.core.outbound import find_url_refusal, open_http_client
from k_b.core.quoting import locate_first_error, quote_value
from k_b.items import UtcDatetime

AI_API_URL_VARIABLE = "KB_AI_API_URL"
# The client KB_DIGEST of kb serve-ai: one value for both sides (README, "Changer une clé").
AI_API_KEY_VARIABLE = f"{AI_API_KEY_VARIABLE_PREFIX}KB_DIGEST"
# No TLS before Azure Container Apps, as for the data API: http on the machine and in the compose
# network.
AI_API_SCHEMES = ("http", "https")
DIGESTS_PATH = "digests"
RETRY_AFTER_HEADER = "Retry-After"
# The id log_request gives a request (core/api_request_log.py): uuid4, in lowercase.
REQUEST_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# A named state of K-B (docs/fiches-veille.md, "États nommés"), a stage of a digest, a kind of
# item: lowercase letters and _, nothing YAML or Markdown would read.
LOWERCASE_NAME = re.compile(r"[a-z_]{1,64}")
# A Retry-After in seconds; a date is quoted.
SECONDS = re.compile(r"[0-9]{1,6}")

type AiApiState = Literal[
    "ai_api_unavailable",
    "ai_api_timeout",
    "ai_api_unauthorized",
    "ai_api_failed",
    "ai_api_invalid_response",
]


class AiApiError(Exception):
    """A request of the digests stopped: its state, the HTTP status of the answer when one came,
    and what the answer says, each value checked by its rule or quoted (conventions.md, rule 3).
    Never the URL nor the key."""

    def __init__(
        self,
        state: AiApiState,
        http_status: int | None = None,
        details: Sequence[str] = (),
    ) -> None:
        status = () if http_status is None else (f"HTTP {http_status}",)
        super().__init__(", ".join((state, *status, *details)))
        self.state: AiApiState = state
        self.http_status = http_status


@dataclass(frozen=True)
class AiApiClientSettings:
    base_url: str
    api_key: SecretStr


def match_fully(pattern: re.Pattern[str]) -> Callable[[str], str]:
    """A validator of the whole text by pattern; its message never quotes the text."""

    def check(text: str) -> str:
        if not pattern.fullmatch(text):
            raise ValueError(f"not {pattern.pattern}")
        return text

    return check


class AiApiModel(BaseModel):
    """A part of the response of POST /digests: the fields read are typed, the others ignored
    (the facts, the counters kb digest does not write)."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class Window(AiApiModel):
    days: int
    since: UtcDatetime
    until: UtcDatetime
    # The kind cut by the cap of the reading, and the date of its first item left out; null when
    # nothing is cut (docs/fiches-veille.md, "Lecture plafonnée").
    capped_kind: Annotated[str, AfterValidator(match_fully(LOWERCASE_NAME))] | None
    covered_after: UtcDatetime | None


class Claim(AiApiModel):
    text: str
    # A claim without a source is never written (OWASP LLM07).
    item_ids: Annotated[list[int], Field(min_length=1)]


class Source(AiApiModel):
    item_id: int
    title: str
    url: str | None


class Digest(AiApiModel):
    subject: str
    claims: list[Claim]
    sources: list[Source]


class FailedSubject(AiApiModel):
    subject: str
    stage: Annotated[str, AfterValidator(match_fully(LOWERCASE_NAME))]
    error: Annotated[str, AfterValidator(match_fully(LOWERCASE_NAME))]


class DigestsResponse(AiApiModel):
    request_id: Annotated[str, AfterValidator(match_fully(REQUEST_ID))]
    model: Annotated[str, AfterValidator(match_fully(MODEL_NAME))]
    window: Window
    digests: list[Digest]
    failed_subjects: list[FailedSubject]
    items_capped: bool


class ErrorBody(AiApiModel):
    error: str


def read_ai_api_client_settings_or_refusal(
    environ: Mapping[str, str],
) -> AiApiClientSettings | str:
    """The settings of the AI API, or why a variable is refused: never the key nor the URL."""
    # Empty is not set, as for the settings of the AI API.
    base_url = environ.get(AI_API_URL_VARIABLE) or AI_API_URL
    api_key = environ.get(AI_API_KEY_VARIABLE)
    if not api_key:
        return f"{AI_API_KEY_VARIABLE}: not set"
    refusal = find_url_refusal(
        AI_API_URL_VARIABLE, base_url, AI_API_SCHEMES
    ) or find_api_key_refusal(
        AI_API_KEY_VARIABLE_PREFIX, AI_API_KEY_VARIABLE, api_key, {}
    )
    if refusal is not None:
        return refusal
    return AiApiClientSettings(base_url=base_url, api_key=SecretStr(api_key))


def build_ai_api_client(
    settings: AiApiClientSettings, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    return open_http_client(
        settings.base_url,
        {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
        httpx2.Timeout(
            connect=AI_API_CONNECT_TIMEOUT_SECONDS,
            read=AI_API_READ_TIMEOUT_SECONDS,
            write=AI_API_WRITE_TIMEOUT_SECONDS,
            pool=AI_API_POOL_TIMEOUT_SECONDS,
        ),
        transport,
    )


def request_digests(
    http_client: httpx2.Client, subject_names: Sequence[str]
) -> DigestsResponse:
    """The digests of the default window of the AI API (KB_DIGEST_WINDOW_DAYS), checked against
    subject_names. Raises AiApiError. Raised from None: the error of httpx2 names the URL, a
    ValidationError quotes the value received."""
    try:
        answer = http_client.post(DIGESTS_PATH, json={})
    except httpx2.TimeoutException:
        raise AiApiError("ai_api_timeout") from None
    except httpx2.TransportError:
        raise AiApiError("ai_api_unavailable") from None
    except httpx2.RequestError:
        # An answer that cannot be read (a body badly encoded).
        raise AiApiError("ai_api_invalid_response") from None
    response = read_response(answer)
    refuse_out_of_lists(response, subject_names)
    return response


def read_response(answer: httpx2.Response) -> DigestsResponse:
    """The body of a 200 in its schema; any other answer is a named state."""
    status = answer.status_code
    if status == httpx2.codes.UNAUTHORIZED:
        raise AiApiError("ai_api_unauthorized", status, describe_answer(answer))
    if status >= httpx2.codes.INTERNAL_SERVER_ERROR:
        raise AiApiError("ai_api_failed", status, describe_answer(answer))
    if status != httpx2.codes.OK:
        # A redirection not followed, a 404 of a route, a 422.
        raise AiApiError("ai_api_invalid_response", status, describe_answer(answer))
    try:
        return DigestsResponse.model_validate_json(answer.content)
    except ValidationError as error:
        raise AiApiError(
            "ai_api_invalid_response",
            status,
            (locate_first_error(error), *describe_answer(answer)),
        ) from None


def describe_answer(answer: httpx2.Response) -> list[str]:
    """What a failed answer says: the state of its body, the id of its request, to find it in the
    log of kb serve-ai, and its Retry-After."""
    details = []
    error = read_error_state(answer.content)
    if error is not None:
        details.append(f"error {describe_value(error, LOWERCASE_NAME)}")
    for header, pattern in (
        (REQUEST_ID_HEADER, REQUEST_ID),
        (RETRY_AFTER_HEADER, SECONDS),
    ):
        value = answer.headers.get(header)
        if value is not None:
            details.append(f"{header} {describe_value(value, pattern)}")
    return details


def read_error_state(content: bytes) -> str | None:
    try:
        return ErrorBody.model_validate_json(content).error
    except ValidationError:
        return None


def describe_value(value: str, pattern: re.Pattern[str]) -> str:
    """The value as it is when it follows its rule, else quoted, cut and escaped."""
    return value if pattern.fullmatch(value) else quote_value(value)


def refuse_out_of_lists(
    response: DigestsResponse, subject_names: Sequence[str]
) -> None:
    """Each subject is of the closed list, once in the response: its name makes the path of its
    sheet. Each source of a digest is there once, and each claim cites its sources once each,
    all of them sources of its digest: a sheet never cites what it does not list."""
    seen_subjects: set[str] = set()
    subjects = [
        (f"digests.{number}.subject", digest.subject)
        for number, digest in enumerate(response.digests)
    ] + [
        (f"failed_subjects.{number}.subject", failed.subject)
        for number, failed in enumerate(response.failed_subjects)
    ]
    for place, subject in subjects:
        if subject not in subject_names:
            raise_invalid(response, place, "subject_not_listed")
        if subject in seen_subjects:
            raise_invalid(response, place, "subject_twice")
        seen_subjects.add(subject)
    for number, digest in enumerate(response.digests):
        source_ids = [source.item_id for source in digest.sources]
        if len(set(source_ids)) != len(source_ids):
            raise_invalid(response, f"digests.{number}.sources", "item_twice")
        for claim_number, claim in enumerate(digest.claims):
            place = f"digests.{number}.claims.{claim_number}.item_ids"
            if not set(claim.item_ids) <= set(source_ids):
                raise_invalid(response, place, "item_not_in_sources")
            if len(set(claim.item_ids)) != len(claim.item_ids):
                raise_invalid(response, place, "item_twice")


def raise_invalid(response: DigestsResponse, place: str, check: str) -> NoReturn:
    """A response refused by a closed list, named by its place, and by its request_id, to find it
    in the log of kb serve-ai."""
    raise AiApiError(
        "ai_api_invalid_response",
        httpx2.codes.OK,
        (f"{place} ({check})", f"request_id {response.request_id}"),
    )
