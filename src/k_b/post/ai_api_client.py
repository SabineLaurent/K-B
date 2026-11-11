"""The requests of kb to the AI API, by HTTP: their settings and their answer, an untrusted input
read within its bounds, then by a closed schema; POST /digests and its response, checked against
the closed lists."""

import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    AI_API_REQUEST_DEADLINE_SECONDS,
    AI_API_URL,
    AI_API_WRITE_TIMEOUT_SECONDS,
    DIGEST_CLIENT,
    MAX_AI_API_ANSWER_BYTES,
    MAX_DIGEST_WINDOW_DAYS,
    MODEL_NAME,
)
from k_b.core.dates import DATABASE_DATE_FORMAT
from k_b.core.outbound import (
    BodyTooLargeError,
    BodyTooLateError,
    find_internal_api_url_refusal,
    open_http_client,
    read_bounded_body,
)
from k_b.core.quoting import locate_first_error, quote_value
from k_b.core.retry_after import RETRY_AFTER_SECONDS
from k_b.items import ItemKind, UtcDatetime

AI_API_URL_VARIABLE = "KB_AI_API_URL"
# The client KB_DIGEST of kb serve-ai: one value for both sides (README, "Changer une clé").
DIGEST_KEY_VARIABLE = f"{AI_API_KEY_VARIABLE_PREFIX}{DIGEST_CLIENT}"
DIGESTS_PATH = "digests"
RETRY_AFTER_HEADER = "Retry-After"
# The id log_request gives a request (core/api_request_log.py): uuid4, in lowercase.
REQUEST_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# A named state of K-B (docs/fiches-veille.md, "États nommés") or a stage of a digest: lowercase
# letters and _, nothing Markdown would read. Written in a log, never in a sheet.
LOWERCASE_NAME = re.compile(r"[a-z_]{1,64}")

type AiApiState = Literal[
    "ai_api_unavailable",
    "ai_api_timeout",
    "ai_api_unauthorized",
    "ai_api_forbidden",
    "ai_api_rate_limited",
    "ai_api_failed",
    "ai_api_invalid_response",
]


class AiApiError(Exception):
    """A request to the AI API stopped: its state, the HTTP status, and what the answer says,
    checked or quoted; never the URL nor the key."""

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


@dataclass(frozen=True)
class Answer:
    """An answer of the AI API, its body read within its bounds."""

    status_code: int
    headers: httpx2.Headers
    content: bytes


def match_fully(pattern: re.Pattern[str]) -> Callable[[str], str]:
    """A validator of the whole text by pattern; its message never quotes the text."""

    def check(text: str) -> str:
        if not pattern.fullmatch(text):
            raise ValueError(f"not {pattern.pattern}")
        return text

    return check


class AiApiModel(BaseModel):
    """A part of a response of the AI API: the fields read are typed, the others ignored."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class Window(AiApiModel):
    days: int
    since: UtcDatetime
    until: UtcDatetime
    # The kind cut by the cap of the reading, and the date of its first item left out; null when
    # nothing is cut (docs/fiches-veille.md, "Lecture plafonnée"). A kind of the closed list:
    # written in the front matter, a word YAML reads as null or a boolean would make a window
    # cut look uncut.
    capped_kind: ItemKind | None
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
    # The start applied to each subject: the since of its sheet.
    since_by_subject: dict[str, UtcDatetime]
    digests: list[Digest]
    failed_subjects: list[FailedSubject]
    # The subjects no item fell in: each gets its sheet, which moves its next start on.
    subjects_without_items: list[str]
    # The items of the window read by the AI API, shown in the summary of kb digest.
    items_in: int
    items_capped: bool


class ErrorBody(AiApiModel):
    error: str


def read_ai_api_client_settings_or_refusal(
    environ: Mapping[str, str], key_variable: str
) -> AiApiClientSettings | str:
    """The settings of the AI API for the client of key_variable, or why a variable is refused:
    never the key nor the URL."""
    # Empty is not set, as for the settings of the AI API.
    base_url = environ.get(AI_API_URL_VARIABLE) or AI_API_URL
    api_key = environ.get(key_variable)
    if not api_key:
        return f"{key_variable}: not set"
    refusal = find_internal_api_url_refusal(
        AI_API_URL_VARIABLE, base_url, environ
    ) or find_api_key_refusal(AI_API_KEY_VARIABLE_PREFIX, key_variable, api_key, {})
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
    http_client: httpx2.Client,
    subject_names: Sequence[str],
    since_by_subject: Mapping[str, datetime],
) -> DigestsResponse:
    """The digests of each subject from its start, the default window of the AI API for a
    subject without one, checked against subject_names and the starts sent."""
    body = {
        "since_by_subject": {
            subject: start.astimezone(UTC).strftime(DATABASE_DATE_FORMAT)
            for subject, start in since_by_subject.items()
        }
    }
    response = read_response(
        send_request(http_client, DIGESTS_PATH, body), DigestsResponse
    )
    refuse_out_of_lists(response, subject_names)
    refuse_moved_starts(response, since_by_subject)
    return response


def send_request(
    http_client: httpx2.Client,
    path: str,
    body: Mapping[str, object],
    *,
    clock: Callable[[], float] = time.monotonic,
) -> Answer:
    """POST body to path, its answer read within its size and its deadline; raised from None, as
    the error of httpx2 names the URL."""
    deadline = clock() + AI_API_REQUEST_DEADLINE_SECONDS

    def is_late() -> bool:
        return clock() >= deadline

    try:
        with http_client.stream("POST", path, json=body) as response:
            status = response.status_code
            try:
                content = read_bounded_body(response, MAX_AI_API_ANSWER_BYTES, is_late)
            except BodyTooLargeError:
                # Any status keeps its state; a 200 beyond the bound is an invalid answer.
                raise AiApiError(
                    find_failure_state(status) or "ai_api_invalid_response",
                    status,
                    (
                        f"response larger than {MAX_AI_API_ANSWER_BYTES} bytes",
                        *describe_headers(response.headers),
                    ),
                ) from None
            except BodyTooLateError:
                raise AiApiError(
                    "ai_api_timeout", status, describe_headers(response.headers)
                ) from None
            return Answer(status, response.headers, content)
    except httpx2.TimeoutException:
        raise AiApiError("ai_api_timeout") from None
    except httpx2.TransportError:
        raise AiApiError("ai_api_unavailable") from None
    except httpx2.RequestError:
        # An answer that cannot be read (a body badly encoded).
        raise AiApiError("ai_api_invalid_response") from None


def read_response[Response: AiApiModel](
    answer: Answer, schema: type[Response]
) -> Response:
    """The body of a 200 in its schema; any other answer is a named state. Raised from None, as a
    ValidationError quotes the value."""
    status = answer.status_code
    state = find_failure_state(status)
    if state is not None:
        raise AiApiError(state, status, describe_answer(answer))
    try:
        return schema.model_validate_json(answer.content)
    except ValidationError as error:
        raise AiApiError(
            "ai_api_invalid_response",
            status,
            (locate_first_error(error), *describe_answer(answer)),
        ) from None


def find_failure_state(status: int) -> AiApiState | None:
    """The state of an answer that is not a 200; None for a 200."""
    if status == httpx2.codes.OK:
        return None
    if status == httpx2.codes.UNAUTHORIZED:
        return "ai_api_unauthorized"
    if status == httpx2.codes.FORBIDDEN:
        return "ai_api_forbidden"
    if status == httpx2.codes.TOO_MANY_REQUESTS:
        return "ai_api_rate_limited"
    if status >= httpx2.codes.INTERNAL_SERVER_ERROR:
        return "ai_api_failed"
    # A redirection not followed, a 404 of a route, a 422.
    return "ai_api_invalid_response"


def describe_answer(answer: Answer) -> list[str]:
    """What a failed answer says: the state of its body, the id of its request and its
    Retry-After."""
    details = []
    error = read_error_state(answer.content)
    if error is not None:
        details.append(f"error {describe_value(error, LOWERCASE_NAME)}")
    return details + describe_headers(answer.headers)


def describe_headers(headers: httpx2.Headers) -> list[str]:
    """The id of the request and the Retry-After of an answer, each as it is or quoted."""
    details = []
    for header, pattern in (
        (REQUEST_ID_HEADER, REQUEST_ID),
        # A Retry-After in seconds as it is; a date is quoted.
        (RETRY_AFTER_HEADER, RETRY_AFTER_SECONDS),
    ):
        value = headers.get(header)
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
    """Refuse a response whose subjects or sources break their closed lists."""
    refuse_subjects_out_of_list(response, subject_names)
    refuse_sources_out_of_digests(response)


def refuse_subjects_out_of_list(
    response: DigestsResponse, subject_names: Sequence[str]
) -> None:
    """Refuse a subject out of the closed list, given twice or missing, as its name makes the path
    of its sheet; and starts that are not those of the list."""
    seen_subjects: set[str] = set()
    subjects = (
        [
            (f"digests.{number}.subject", digest.subject)
            for number, digest in enumerate(response.digests)
        ]
        + [
            (f"failed_subjects.{number}.subject", failed.subject)
            for number, failed in enumerate(response.failed_subjects)
        ]
        + [
            (f"subjects_without_items.{number}", subject)
            for number, subject in enumerate(response.subjects_without_items)
        ]
    )
    if set(response.since_by_subject) != set(subject_names):
        raise_invalid(response.request_id, "since_by_subject", "subjects_not_the_list")
    for place, subject in subjects:
        if subject not in subject_names:
            raise_invalid(response.request_id, place, "subject_not_listed")
        if subject in seen_subjects:
            raise_invalid(response.request_id, place, "subject_twice")
        seen_subjects.add(subject)
    if seen_subjects != set(subject_names):
        raise_invalid(response.request_id, "subjects", "subject_missing")


def refuse_sources_out_of_digests(response: DigestsResponse) -> None:
    """Refuse a source given twice in its digest, and a claim citing a source not listed once in
    its digest."""
    for number, digest in enumerate(response.digests):
        source_ids = [source.item_id for source in digest.sources]
        if len(set(source_ids)) != len(source_ids):
            raise_invalid(
                response.request_id, f"digests.{number}.sources", "item_twice"
            )
        for claim_number, claim in enumerate(digest.claims):
            place = f"digests.{number}.claims.{claim_number}.item_ids"
            if not set(claim.item_ids) <= set(source_ids):
                raise_invalid(response.request_id, place, "item_not_in_sources")
            if len(set(claim.item_ids)) != len(claim.item_ids):
                raise_invalid(response.request_id, place, "item_twice")


def refuse_moved_starts(
    response: DigestsResponse, since_by_subject: Mapping[str, datetime]
) -> None:
    """Refuse a subject started before the start sent, as its sheet would give again items of its
    previous sheet; one started later, unless at the bound of the AI API; and a subject without a
    start sent that does not start at the window of the response, window.days before its until."""
    window_start = response.window.until - timedelta(days=response.window.days)
    bound = response.window.until - timedelta(days=MAX_DIGEST_WINDOW_DAYS)
    for subject, applied in response.since_by_subject.items():
        place = f"since_by_subject.{subject}"
        start = since_by_subject.get(subject)
        if start is None:
            if applied != window_start:
                raise_invalid(response.request_id, place, "start_not_the_window")
            continue
        if applied < start:
            raise_invalid(response.request_id, place, "start_before_the_one_sent")
        if applied > start and applied != bound:
            raise_invalid(response.request_id, place, "start_after_the_one_sent")


def raise_invalid(request_id: str, place: str, check: str) -> NoReturn:
    """A response refused by a check, named by its place and the request_id, never a value."""
    raise AiApiError(
        "ai_api_invalid_response",
        httpx2.codes.OK,
        (f"{place} ({check})", f"request_id {request_id}"),
    )


def describe_remedy(error: AiApiError, key_variable: str) -> str:
    """The variable to check after a 401 or a 403: named, never its key."""
    if error.state == "ai_api_unauthorized":
        return f"; the AI API refused the key of {key_variable}"
    if error.state == "ai_api_forbidden":
        return f"; the AI API does not open this route to the client of {key_variable}"
    return ""
