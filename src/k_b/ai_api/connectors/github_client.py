"""The reading of the sheet of a candidate on GitHub, GET /repos/{owner}/{repo}, one request after
the other under the deadline and the budget of the report (docs/tendances.md, "GitHub"): a
candidate gone, moved, replaced or refused is left out by its reason; any other failure is a named
state, raised as a GithubError, and stops the report."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

import httpx2
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.repository_cards import DropReason, RepositoryCard
from k_b.core.config import (
    GITHUB_MAX_FORBIDDEN_PER_REPORT,
    GITHUB_MAX_REQUESTS_PER_REPORT,
    HTTP_TIMEOUT_SECONDS,
    MAX_GITHUB_REPOSITORY_BYTES,
    MAX_GITHUB_RETRY_AFTER_SECONDS,
    MAX_GITHUB_TOPICS,
)
from k_b.core.github_api import API_URL, API_VERSION
from k_b.core.outbound import open_http_client
from k_b.core.rate_limit import (
    MIN_PAUSE_SECONDS,
    RATE_LIMIT_REMAINING_HEADER,
    RATE_LIMIT_RESET_HEADER,
    read_rate_limit_reset_value,
)
from k_b.core.retry_after import is_retry_after_too_long, read_retry_after
from k_b.core.user_agent import USER_AGENT
from k_b.items import Int64, UtcDatetime

type GithubState = Literal[
    "github_unauthorized",
    "github_rate_limited",
    "github_forbidden",
    "github_unavailable",
    "github_timeout",
    "github_invalid_response",
]

# The message of a secondary rate limit, or its former wording (docs: "Rate limits for the REST
# API"; Octokit, error_for_403), read without case.
RATE_LIMIT_MESSAGE = re.compile(r"rate limit|abuse", re.IGNORECASE)
NOT_FOUND_STATUSES = {httpx2.codes.NOT_FOUND, httpx2.codes.GONE}


class GithubError(Exception):
    """A reading stopped by GitHub: its state, the HTTP status and the Retry-After to return;
    never the body nor a header, which may quote the repository."""

    def __init__(
        self,
        state: GithubState,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(
            state if http_status is None else f"{state}, HTTP {http_status}"
        )
        self.state: GithubState = state
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds


class GithubModel(BaseModel):
    """An answer of GitHub: the fields read are typed, the others ignored, the owner among them."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class LicenseBody(GithubModel):
    # NOASSERTION: a license GitHub does not recognize.
    spdx_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9.+-]{1,64}$")] | None


class RepositoryBody(GithubModel):
    id: Annotated[Int64, Field(gt=0)]
    stargazers_count: Annotated[Int64, Field(ge=0)]
    created_at: UtcDatetime
    # Without a control character (Cc).
    language: Annotated[str, Field(pattern=r"^[^\x00-\x1f\x7f-\x9f]{1,100}$")] | None
    topics: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z0-9-]{1,50}$")]],
        Field(max_length=MAX_GITHUB_TOPICS),
    ]
    license: LicenseBody | None


REPOSITORY = TypeAdapter(RepositoryBody)


class ErrorBody(GithubModel):
    message: str


@dataclass(frozen=True)
class Answer:
    """An answer of GitHub, its body read whole within MAX_GITHUB_REPOSITORY_BYTES."""

    status_code: int
    headers: httpx2.Headers
    content: bytes


@dataclass
class GithubReading:
    """The reading of the sheets of one report: its client, its deadline, the time of its request,
    and what it has spent; nothing is kept beyond the report."""

    http_client: httpx2.Client
    deadline: Deadline
    now: datetime
    requests: int = 0
    forbidden: int = 0


def build_github_client(
    settings: GithubSettings, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    return open_http_client(
        API_URL,
        {
            "Authorization": f"Bearer {settings.token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": API_VERSION,
        },
        # A remote service, as for the collection.
        httpx2.Timeout(HTTP_TIMEOUT_SECONDS),
        transport,
    )


def read_repository(
    reading: GithubReading, repository_id: int, repository_name: str
) -> RepositoryCard | DropReason:
    """The sheet of the repository, or why it is left out. The name, checked by
    is_repository_name, makes the path: neither `.` nor `..`, nor a query."""
    answer = send(reading, f"repos/{repository_name}")
    if answer.status_code >= httpx2.codes.INTERNAL_SERVER_ERROR:
        # Once, without a wait: a wait would eat the deadline of the report.
        answer = send(reading, f"repos/{repository_name}")
    status = answer.status_code
    if status == httpx2.codes.OK:
        return to_card(answer, repository_id)
    if httpx2.codes.is_redirect(status):
        # Not followed (core/outbound.py): a repository moved, which its name no longer names.
        return "moved"
    if status in NOT_FOUND_STATUSES:
        return "not_found"
    if status == httpx2.codes.UNAVAILABLE_FOR_LEGAL_REASONS:
        return "unavailable_for_legal_reasons"
    if status == httpx2.codes.FORBIDDEN and not is_rate_limit(answer):
        return count_forbidden(reading, status)
    raise to_error(answer, reading.now)


def send(reading: GithubReading, path: str) -> Answer:
    """One GET within the budget and the deadline, its body read within its bound; raised from
    None, as the error of httpx2 names the URL."""
    if reading.requests >= GITHUB_MAX_REQUESTS_PER_REPORT:
        raise GithubError("github_unavailable")
    if reading.deadline.is_passed():
        raise GithubError("github_timeout")
    reading.requests += 1
    http_client = reading.http_client
    try:
        with http_client.stream(
            "GET", path, timeout=reading.deadline.cap(http_client.timeout)
        ) as response:
            return Answer(
                response.status_code,
                response.headers,
                read_bounded_body(response, reading.deadline),
            )
    except httpx2.TimeoutException:
        raise GithubError("github_timeout") from None
    except httpx2.TransportError:
        raise GithubError("github_unavailable") from None
    except httpx2.RequestError:
        # An answer that cannot be read (a body badly encoded).
        raise GithubError("github_invalid_response") from None


def read_bounded_body(response: httpx2.Response, deadline: Deadline) -> bytes:
    """The body, refused beyond MAX_GITHUB_REPOSITORY_BYTES without quoting it, and stopped as
    soon as the deadline passes between two pieces, as in connectors/data_api_client.py."""
    status = response.status_code
    length = response.headers.get("Content-Length")
    if (
        length is not None
        and length.isascii()
        and length.isdigit()
        and int(length) > MAX_GITHUB_REPOSITORY_BYTES
    ):
        raise GithubError("github_invalid_response", status)
    body = bytearray()
    # Decoded bytes: a compressed body is bounded by what it takes once read.
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > MAX_GITHUB_REPOSITORY_BYTES:
            raise GithubError("github_invalid_response", status)
        if deadline.is_passed():
            raise GithubError("github_timeout", status)
    return bytes(body)


def to_card(answer: Answer, repository_id: int) -> RepositoryCard | DropReason:
    """The sheet of a 200 in its schema; another id is a repository replaced under the name."""
    try:
        body = REPOSITORY.validate_json(answer.content)
    except ValidationError:
        raise GithubError("github_invalid_response", answer.status_code) from None
    if body.id != repository_id:
        return "id_mismatch"
    license = body.license
    return RepositoryCard(
        repository_id=body.id,
        license=(
            None
            if license is None or license.spdx_id in {None, "NOASSERTION"}
            else license.spdx_id
        ),
        created_at=body.created_at,
        language=body.language,
        topics=tuple(body.topics),
        stars_total=body.stargazers_count,
    )


def is_rate_limit(answer: Answer) -> bool:
    """A 403 of a rate limit: no request left, a Retry-After, or a message naming it (docs: "Rate
    limits for the REST API"); any other 403 is a refusal of the repository."""
    if (
        answer.headers.get(RATE_LIMIT_REMAINING_HEADER) == "0"
        or "retry-after" in answer.headers
    ):
        return True
    try:
        message = ErrorBody.model_validate_json(answer.content).message
    except ValidationError:
        return False
    return RATE_LIMIT_MESSAGE.search(message) is not None


def count_forbidden(reading: GithubReading, status: int) -> DropReason:
    """A refusal leaves its candidate out, up to the third of the report, which stops the
    reading: github_forbidden, never named a rate limit."""
    reading.forbidden += 1
    if reading.forbidden >= GITHUB_MAX_FORBIDDEN_PER_REPORT:
        raise GithubError("github_forbidden", status)
    return "forbidden"


def to_error(answer: Answer, now: datetime) -> GithubError:
    status = answer.status_code
    if status == httpx2.codes.UNAUTHORIZED:
        return GithubError("github_unauthorized", status)
    if status in {httpx2.codes.FORBIDDEN, httpx2.codes.TOO_MANY_REQUESTS}:
        return GithubError(
            "github_rate_limited", status, find_retry_after(answer.headers, now)
        )
    if status >= httpx2.codes.INTERNAL_SERVER_ERROR:
        return GithubError("github_unavailable", status)
    return GithubError("github_invalid_response", status)


def find_retry_after(headers: httpx2.Headers, now: datetime) -> int:
    """The seconds to wait: the retry-after of GitHub; else, with no request left, its reset
    after now; else the minute GitHub asks; MAX_GITHUB_RETRY_AFTER_SECONDS at most."""
    retry_after = headers.get("retry-after")
    seconds = read_retry_after(retry_after)
    if seconds is None and is_retry_after_too_long(retry_after):
        seconds = MAX_GITHUB_RETRY_AFTER_SECONDS
    if seconds is None:
        seconds = MIN_PAUSE_SECONDS
        reset = read_rate_limit_reset_value(headers.get(RATE_LIMIT_RESET_HEADER))
        if headers.get(RATE_LIMIT_REMAINING_HEADER) == "0" and reset is not None:
            seconds = max(reset - int(now.timestamp()), MIN_PAUSE_SECONDS)
    return min(seconds, MAX_GITHUB_RETRY_AFTER_SECONDS)
