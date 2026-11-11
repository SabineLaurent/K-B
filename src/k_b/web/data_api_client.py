"""The reading of the feed by the data API, with the key of the client WEB (docs/site-web.md,
"Fil"): one GET /items by page, a failure a named state raised as a DataApiError, without retry."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal, get_args

import httpx2
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from k_b.core.config import (
    DATA_API_CONNECT_TIMEOUT_SECONDS,
    DATA_API_POOL_TIMEOUT_SECONDS,
    DATA_API_WRITE_TIMEOUT_SECONDS,
    FEED_PAGE_SIZE,
    MAX_WEB_DATA_API_BODY_BYTES,
    WEB_DATA_API_READ_TIMEOUT_SECONDS,
    WEB_DATA_API_REQUEST_DEADLINE_SECONDS,
)
from k_b.core.dates import format_day
from k_b.core.outbound import (
    BodyTooLargeError,
    BodyTooLateError,
    open_http_client,
    read_bounded_body,
)
from k_b.items import (
    ArxivId,
    CveId,
    Int64,
    NewsletterEdition,
    NonEmptyText,
    RepositoryName,
    UtcDatetime,
)
from k_b.web.settings import DataApiAccess

ITEMS_PATH = "items"
# The kinds of the feed, in the order of the form; never zotero_entry nor clip.
type FeedKind = Literal[
    "paper", "vulnerability", "advisory", "release", "newsletter_article"
]
FEED_KINDS: tuple[FeedKind, ...] = get_args(FeedKind.__value__)

type DataApiState = Literal[
    "data_api_unavailable",
    "data_api_timeout",
    "data_api_unauthorized",
    "data_api_rate_limited",
    "data_api_invalid_parameter",
    "data_api_invalid_response",
]


class DataApiError(Exception):
    """A reading stopped by the data API: its state, the HTTP status, and the names of the
    parameters a 422 refuses; never the body, the URL nor a header, which may quote what was
    sent."""

    def __init__(
        self,
        state: DataApiState,
        http_status: int | None = None,
        parameters: tuple[str, ...] = (),
    ) -> None:
        super().__init__(state)
        self.state: DataApiState = state
        self.http_status = http_status
        self.parameters = parameters


class DataApiModel(BaseModel):
    """An answer of the data API: the fields read are typed, the others ignored, so that a field
    the API adds does not stop the feed."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class FeedItemBase(DataApiModel):
    id: Int64
    title: NonEmptyText
    source_date: UtcDatetime
    url: str | None
    withdrawn_at: UtcDatetime | None


class FeedPaper(FeedItemBase):
    kind: Literal["paper"]
    arxiv_id: ArxivId


class FeedVulnerability(FeedItemBase):
    kind: Literal["vulnerability"]
    cve_id: CveId
    # Always true by the data API: the catalog is CISA KEV; its withdrawal is in withdrawn_at.
    exploited: bool


class FeedAdvisory(FeedItemBase):
    kind: Literal["advisory"]
    ghsa_id: NonEmptyText
    cve_id: CveId | None
    # True: the CVE is in the CISA KEV catalog; false: absent from it; null: no CVE.
    exploited: bool | None
    packages: list[NonEmptyText]
    packages_truncated: bool


class FeedRelease(FeedItemBase):
    kind: Literal["release"]
    repository_name: RepositoryName


class FeedNewsletterArticle(FeedItemBase):
    kind: Literal["newsletter_article"]
    edition: NewsletterEdition


type FeedItem = (
    FeedPaper | FeedVulnerability | FeedAdvisory | FeedRelease | FeedNewsletterArticle
)


class FeedItemPage(DataApiModel):
    # A kind out of the five, zotero_entry or clip, is refused here.
    items: list[Annotated[FeedItem, Field(discriminator="kind")]]
    total: Annotated[int, Field(ge=0)]


class InvalidParameterBody(DataApiModel):
    error: Literal["invalid_parameter"]
    parameters: list[str]


PAGE = TypeAdapter(FeedItemPage)
INVALID_PARAMETER = TypeAdapter(InvalidParameterBody)


@dataclass(frozen=True)
class FeedQuery:
    """What the site asks of GET /items for a page of the feed: the items dated since_day at
    midnight UTC or later."""

    kinds: tuple[FeedKind, ...]
    since_day: date
    q: str | None
    offset: int


def build_data_api_client(
    access: DataApiAccess, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    return open_http_client(
        access.base_url,
        {"Authorization": f"Bearer {access.api_key.get_secret_value()}"},
        httpx2.Timeout(
            connect=DATA_API_CONNECT_TIMEOUT_SECONDS,
            read=WEB_DATA_API_READ_TIMEOUT_SECONDS,
            write=DATA_API_WRITE_TIMEOUT_SECONDS,
            pool=DATA_API_POOL_TIMEOUT_SECONDS,
        ),
        transport,
    )


def list_feed_items(
    http_client: httpx2.Client,
    query: FeedQuery,
    clock: Callable[[], float] = time.monotonic,
) -> FeedItemPage:
    """A page of the feed, the most recent first, and the number of items of its filters. Each wait
    is bounded by its timeout and the body by the deadline, checked between two of its pieces: at
    worst about 70 s (connect and pool, 30 s for the headers, 30 s for a piece of the body)."""
    status, body = send(http_client, build_params(query), clock)
    if status != httpx2.codes.OK:
        raise name_failure(status, body)
    try:
        return PAGE.validate_json(body)
    except ValidationError:
        raise DataApiError("data_api_invalid_response", status) from None


def build_params(query: FeedQuery) -> dict[str, str | int | list[str]]:
    """The parameters of GET /items: kind always, so that the API never serves a Zotero entry nor
    a clip; since at midnight UTC, in the format of the base."""
    params: dict[str, str | int | list[str]] = {
        "kind": list(query.kinds),
        "since": format_day(query.since_day),
        "limit": FEED_PAGE_SIZE,
        "offset": query.offset,
    }
    if query.q is not None:
        params["q"] = query.q
    return params


def send(
    http_client: httpx2.Client,
    params: dict[str, str | int | list[str]],
    clock: Callable[[], float],
) -> tuple[int, bytes]:
    """One GET of the list, its body read within its bounds; raised from None, as the error of
    httpx2 names the URL."""
    deadline = clock() + WEB_DATA_API_REQUEST_DEADLINE_SECONDS
    try:
        with http_client.stream("GET", ITEMS_PATH, params=params) as response:
            status = response.status_code
            try:
                body = read_bounded_body(
                    response, MAX_WEB_DATA_API_BODY_BYTES, lambda: clock() > deadline
                )
            except BodyTooLargeError:
                raise DataApiError("data_api_invalid_response", status) from None
            except BodyTooLateError:
                raise DataApiError("data_api_timeout", status) from None
            return status, body
    except httpx2.TimeoutException:
        raise DataApiError("data_api_timeout") from None
    except httpx2.TransportError:
        raise DataApiError("data_api_unavailable") from None
    except httpx2.RequestError:
        # An answer that cannot be read (a body badly encoded).
        raise DataApiError("data_api_invalid_response") from None


def name_failure(status: int, body: bytes) -> DataApiError:
    """The state of an answer other than 200; a redirection is never followed."""
    if status == httpx2.codes.UNAUTHORIZED:
        return DataApiError("data_api_unauthorized", status)
    if status == httpx2.codes.TOO_MANY_REQUESTS:
        return DataApiError("data_api_rate_limited", status)
    if status >= httpx2.codes.INTERNAL_SERVER_ERROR:
        return DataApiError("data_api_unavailable", status)
    if status == httpx2.codes.UNPROCESSABLE_CONTENT:
        try:
            refused = INVALID_PARAMETER.validate_json(body)
        except ValidationError:
            return DataApiError("data_api_invalid_response", status)
        return DataApiError(
            "data_api_invalid_parameter", status, tuple(refused.parameters)
        )
    return DataApiError("data_api_invalid_response", status)
