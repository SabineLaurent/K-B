"""The reading of the feed, of the detail of an item and of the trends by the data API, with the key
of the client WEB (docs/site-web.md, "Fil", "Détail" and "Tendances"): one GET /items by page, one
GET /items/{item_id} by detail, one GET /trends by window, a failure a named state raised as a
DataApiError, without retry."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Literal, get_args

import httpx2
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
)

from k_b.core.config import (
    DATA_API_CONNECT_TIMEOUT_SECONDS,
    DATA_API_POOL_TIMEOUT_SECONDS,
    DATA_API_WRITE_TIMEOUT_SECONDS,
    FEED_PAGE_SIZE,
    GH_ARCHIVE_TOP_SIZE,
    GH_ARCHIVE_WINDOW_DAYS,
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
    MAX_INT64,
    ArxivId,
    CveId,
    GhsaId,
    NewsletterEdition,
    NonEmptyText,
    RansomwareUse,
    RepositoryName,
    UtcDatetime,
    is_repository_name,
)
from k_b.web.settings import DataApiAccess

ITEMS_PATH = "items"
TREND_WINDOW_PATH = "trends"
# The 30 first repositories by stars and the 30 first by forks, together (docs/specs-api.md).
MAX_TRENDS = 2 * GH_ARCHIVE_TOP_SIZE
# The first day a window can end on: the site writes its start, GH_ARCHIVE_WINDOW_DAYS - 1 days
# before.
FIRST_WINDOW_END = date.min + timedelta(days=GH_ARCHIVE_WINDOW_DAYS - 1)
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
    "data_api_item_not_found",
    "data_api_trend_window_not_found",
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
    # 1 at least: the feed never builds a link to a detail its route would refuse.
    id: Annotated[int, Field(ge=1, le=MAX_INT64)]
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
    ghsa_id: GhsaId
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


# The detail of each kind: the item of the feed, then what its page shows of the detail, never
# more (RGESN 1.6). A text the base bounds by its length only may be empty (schema.sql): str, its
# NUL and lone surrogates dropped by clean_received_text before it is shown.
class PaperDetail(FeedPaper):
    authors: list[str]
    summary: str
    arxiv_updated_at: UtcDatetime


class VulnerabilityDetail(FeedVulnerability):
    description: str
    vendor: str
    product: str
    ransomware_use: RansomwareUse
    revised_at: UtcDatetime | None


class AdvisoryDetail(FeedAdvisory):
    """An advisory has no field beyond those of the feed: every package, in the detail."""


class ReleaseDetail(FeedRelease):
    tag_name: NonEmptyText
    body: str | None


class NewsletterArticleDetail(FeedNewsletterArticle):
    rank: Annotated[int, Field(ge=1)]
    summary: str


class ExcludedItem(DataApiModel):
    """A Zotero entry or a clip: its kind alone is read, for the page not found; its text is
    never modelled, shown nor logged."""

    kind: Literal["zotero_entry", "clip"]


# A plain alias, not a type statement: pydantic reads the discriminator of each of its models.
ItemDetail = (
    PaperDetail
    | VulnerabilityDetail
    | AdvisoryDetail
    | ReleaseDetail
    | NewsletterArticleDetail
)


def check_path_segments(name: str) -> str:
    """Refuse a name with a segment . or .., which a browser resolves to another page of GitHub:
    the link would not lead to the repository its text names."""
    if not is_repository_name(name):
        raise ValueError("a segment . or ..")
    return name


class Trend(DataApiModel):
    """A repository of a window: its name, which the link to GitHub is built from, and its
    counts."""

    repository_name: Annotated[RepositoryName, AfterValidator(check_path_segments)]
    stars_gained: Annotated[int, Field(ge=0, le=MAX_INT64)]
    forks_gained: Annotated[int, Field(ge=0, le=MAX_INT64)]


class TrendWindow(DataApiModel):
    window_end: Annotated[date, Field(ge=FIRST_WINDOW_END)]
    # A window exists by its rows only: GET /trends answers 404 without one.
    trends: Annotated[list[Trend], Field(min_length=1, max_length=MAX_TRENDS)]


class InvalidParameterBody(DataApiModel):
    error: Literal["invalid_parameter"]
    parameters: list[str]


class ItemNotFoundBody(DataApiModel):
    error: Literal["item_not_found"]


class TrendWindowNotFoundBody(DataApiModel):
    error: Literal["trend_window_not_found"]


PAGE = TypeAdapter(FeedItemPage)
DETAIL: TypeAdapter[ItemDetail | ExcludedItem] = TypeAdapter(
    Annotated[ItemDetail | ExcludedItem, Field(discriminator="kind")]
)
INVALID_PARAMETER = TypeAdapter(InvalidParameterBody)
ITEM_NOT_FOUND = TypeAdapter(ItemNotFoundBody)
TREND_WINDOW = TypeAdapter(TrendWindow)
TREND_WINDOW_NOT_FOUND = TypeAdapter(TrendWindowNotFoundBody)


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
    status, body = send(http_client, ITEMS_PATH, build_params(query), clock)
    if status != httpx2.codes.OK:
        raise name_failure(status, body)
    try:
        return PAGE.validate_json(body)
    except ValidationError:
        raise DataApiError("data_api_invalid_response", status) from None


def read_item(
    http_client: httpx2.Client,
    item_id: int,
    clock: Callable[[], float] = time.monotonic,
) -> ItemDetail | ExcludedItem:
    """The detail of an item, or the kind alone of a Zotero entry or a clip; bounded as a page of
    the feed. Only the 404 item_not_found names an item missing: any other 404 is an answer out
    of the contract of the route."""
    status, body = send(http_client, f"{ITEMS_PATH}/{item_id}", {}, clock)
    if status == httpx2.codes.NOT_FOUND and is_item_not_found(body):
        raise DataApiError("data_api_item_not_found", status)
    if status != httpx2.codes.OK:
        raise name_failure(status, body)
    try:
        return DETAIL.validate_json(body)
    except ValidationError:
        raise DataApiError("data_api_invalid_response", status) from None


def is_item_not_found(body: bytes) -> bool:
    try:
        ITEM_NOT_FOUND.validate_json(body)
    except ValidationError:
        return False
    return True


def read_trends(
    http_client: httpx2.Client,
    window_end: date | None,
    clock: Callable[[], float] = time.monotonic,
) -> TrendWindow:
    """The trends of the window that ends on window_end, or of the latest window without it;
    bounded as a page of the feed. Only the 404 trend_window_not_found names a window missing, in
    the base or of this day."""
    params: dict[str, str | int | list[str]] = (
        {} if window_end is None else {"window_end": window_end.isoformat()}
    )
    status, body = send(http_client, TREND_WINDOW_PATH, params, clock)
    if status == httpx2.codes.NOT_FOUND and is_trend_window_not_found(body):
        raise DataApiError("data_api_trend_window_not_found", status)
    if status != httpx2.codes.OK:
        raise name_failure(status, body)
    try:
        window = TREND_WINDOW.validate_json(body)
    except ValidationError:
        raise DataApiError("data_api_invalid_response", status) from None
    # The window of the day asked or 404 (docs/specs-api.md): never another shown as its answer.
    if window_end is not None and window.window_end != window_end:
        raise DataApiError("data_api_invalid_response", status)
    return window


def is_trend_window_not_found(body: bytes) -> bool:
    try:
        TREND_WINDOW_NOT_FOUND.validate_json(body)
    except ValidationError:
        return False
    return True


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
    path: str,
    params: dict[str, str | int | list[str]],
    clock: Callable[[], float],
) -> tuple[int, bytes]:
    """One GET of path, its body read within its bounds; raised from None, as the error of httpx2
    names the URL."""
    deadline = clock() + WEB_DATA_API_REQUEST_DEADLINE_SECONDS
    try:
        with http_client.stream("GET", path, params=params) as response:
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
