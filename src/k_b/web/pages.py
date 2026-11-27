"""The pages of the site: the watch feed, the detail of an item, the digests, the trends, the sources
and the accessibility (docs/site-web.md, "Pages")."""

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import date

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from k_b.core.api_request_log import read_request_id
from k_b.core.config import DATA_API_MAX_SEARCH_LENGTH
from k_b.web.data_api_client import (
    FEED_KINDS,
    DataApiError,
    ExcludedItem,
    WatchDigest,
    list_digest_days,
    list_feed_items,
    read_digest,
    read_item,
    read_trends,
)
from k_b.web.digests import (
    DAY_PATH,
    DIGESTS_PATH,
    SOURCE_PATH,
    SUBJECT_PATH,
    SUBJECTS,
    build_absent_digest_page,
    build_digest_back_link,
    build_digest_page,
    build_missing_source_page,
    build_subject_links,
    find_source,
    is_item_of_source,
    write_source_title,
)
from k_b.web.errors import render_error_page, render_server_error_page
from k_b.web.feed import (
    ERRORS_TITLE,
    FEED_PATH,
    ITEM_PATH,
    LABELS_BY_KIND,
    PERIOD_LABELS,
    PERIODS,
    RESULTS_ID,
    FeedForm,
    FeedListing,
    FieldError,
    build_listing,
    build_query,
    count_pages,
    find_api_field_error,
    fits_in_search_field,
    read_feed_form,
    read_page_number,
    read_written_day,
)
from k_b.web.item_detail import FEED_BACK_LINK, build_item_page, read_item_id
from k_b.web.rendering import render_page
from k_b.web.trends import (
    GITHUB_LINK_NOTE,
    TRENDS_PATH,
    TrendsPage,
    build_missing_window_page,
    build_refused_page,
    build_trends_page,
    find_api_window_end_error,
    read_trends_form,
)

logger = logging.getLogger(__name__)

SOURCES_PATH = "/sources"
ACCESSIBILITY_PATH = "/accessibilite"

router = APIRouter(default_response_class=HTMLResponse)


# The query is read raw, never by parameters FastAPI types: a page=abc would get its 422 in JSON,
# which quotes the value received.
@router.get(FEED_PATH)
def show_feed(request: Request) -> Response:
    """The watch feed: a page of 20 items of the filters of its form, the most recent first."""
    page = read_page_number(request.query_params)
    if page is None:
        return render_error_page(request, 404)
    form = read_feed_form(request.query_params)
    if form.errors:
        return render_feed(request, form, form.errors, None)
    query = build_query(form, request.app.state.clock(), page)
    try:
        item_page = list_feed_items(request.app.state.data_api_client, query)
    except DataApiError as error:
        field_error = find_api_field_error(error)
        if field_error is None:
            log_data_api_failure(request, error)
            return render_server_error_page(request)
        return render_feed(request, form, (field_error,), None)
    if page > count_pages(item_page.total):
        return render_error_page(request, 404)
    listing = build_listing(form, query, page, item_page.items, item_page.total)
    return render_feed(request, form, (), listing)


def render_feed(
    request: Request,
    form: FeedForm,
    errors: Sequence[FieldError],
    listing: FeedListing | None,
) -> Response:
    """The feed with its form; with errors, in 422, without list."""
    return render_page(
        request,
        "feed.html",
        {
            "page_title": listing.title if listing else ERRORS_TITLE,
            "form": form,
            "errors": errors,
            "error_by_field": {error.field: error.message for error in errors},
            # None: the value received is longer than the field allows, which it shows again.
            "search_maxlength": DATA_API_MAX_SEARCH_LENGTH
            if fits_in_search_field(form.q)
            else None,
            "feed_kinds": FEED_KINDS,
            "labels_by_kind": LABELS_BY_KIND,
            "periods": PERIODS,
            "period_labels": PERIOD_LABELS,
            "listing": listing,
            "results_id": RESULTS_ID,
        },
        current_path=FEED_PATH,
        status_code=422 if errors else 200,
    )


# item_id is read as a string, never typed by FastAPI: an id out of its form would get its 422 in
# JSON. The log of the request names the template of the route, never the id (#564).
@router.get(ITEM_PATH)
def show_item(request: Request, item_id: str) -> Response:
    """The detail of an item of the feed; the page not found for an id out of its form, an item
    the base does not hold, a Zotero entry or a clip."""
    read_id = read_item_id(item_id)
    if read_id is None:
        return render_error_page(request, 404)
    try:
        detail = read_item(request.app.state.data_api_client, read_id)
    except DataApiError as error:
        if error.state == "data_api_item_not_found":
            return render_error_page(request, 404)
        log_data_api_failure(request, error)
        return render_server_error_page(request)
    if isinstance(detail, ExcludedItem):
        return render_error_page(request, 404)
    # No link of the navigation is the current page: Veille is the feed, not its detail.
    return render_page(
        request,
        "item.html",
        {"detail": build_item_page(detail), "back_link": FEED_BACK_LINK},
    )


@router.get(DIGESTS_PATH)
def show_digests(request: Request) -> Response:
    """The subjects of the digests, without a call to the data API."""
    return render_page(
        request,
        "digests.html",
        {"subjects": build_subject_links()},
        current_path=DIGESTS_PATH,
    )


# The subject, the day and the id are read as strings, never typed by FastAPI, as the id of the
# detail: each is checked by the site, and refused by the page not found without a call.
@router.get(SUBJECT_PATH)
def show_latest_digest(request: Request, subject: str) -> Response:
    """The most recent digest of a subject; a subject without digest says so."""
    if subject not in SUBJECTS:
        return render_error_page(request, 404)
    return show_digest(request, subject, None)


@router.get(DAY_PATH)
def show_digest_of_day(request: Request, subject: str, day: str) -> Response:
    """The digest of a subject of a day; the page not found for a day without digest."""
    read_day = read_written_day(day)
    if subject not in SUBJECTS or read_day is None:
        return render_error_page(request, 404)
    return show_digest(request, subject, read_day)


def show_digest(request: Request, subject: str, day: date | None) -> Response:
    """A digest and the days of its subject: two calls to the data API."""
    found = fetch_digest(request, subject, day)
    if isinstance(found, Response):
        return found
    try:
        days = list_digest_days(request.app.state.data_api_client, subject)
    except DataApiError as error:
        log_data_api_failure(request, error)
        return render_server_error_page(request)
    return render_page(
        request, "digest.html", {"digest": build_digest_page(found, days)}
    )


@router.get(SOURCE_PATH)
def show_digest_source(
    request: Request, subject: str, day: str, item_id: str
) -> Response:
    """A source of a digest: the page of its item if the base holds it under the URL when the source
    has one, else the title, otherwise what is observed; the digest is read again, never the title
    of the address."""
    read_day = read_written_day(day)
    read_id = read_item_id(item_id)
    if subject not in SUBJECTS or read_day is None or read_id is None:
        return render_error_page(request, 404)
    digest = fetch_digest(request, subject, read_day)
    if isinstance(digest, Response):
        return digest
    source = find_source(digest, read_id)
    if source is None:
        return render_error_page(request, 404)
    try:
        detail = read_item(request.app.state.data_api_client, read_id)
    except DataApiError as error:
        if error.state != "data_api_item_not_found":
            log_data_api_failure(request, error)
            return render_server_error_page(request)
        detail = None
    # A Zotero entry or a clip is never shown: its id says nothing of the source.
    if (
        detail is None
        or isinstance(detail, ExcludedItem)
        or not is_item_of_source(detail, source)
    ):
        return render_page(
            request,
            "digest_source.html",
            {"page": build_missing_source_page(digest, source)},
        )
    item_page = build_item_page(detail)
    return render_page(
        request,
        "item.html",
        {
            "detail": replace(
                item_page, page_title=write_source_title(digest, item_page.page_title)
            ),
            "back_link": build_digest_back_link(digest),
        },
    )


def fetch_digest(
    request: Request, subject: str, day: date | None
) -> WatchDigest | Response:
    """The digest asked, or the page that answers for it: without a day, a subject without digest
    says so in 200; a day without digest is the page not found (its address comes from a link or
    is typed); any other failure, the page 500."""
    try:
        return read_digest(request.app.state.data_api_client, subject, day)
    except DataApiError as error:
        if error.state != "data_api_digest_not_found":
            log_data_api_failure(request, error)
            return render_server_error_page(request)
    if day is not None:
        return render_error_page(request, 404)
    return render_page(
        request, "digest_absent.html", {"page": build_absent_digest_page(subject)}
    )


# window_end is read raw, as the query of the feed: a 422 of FastAPI would quote the value received.
@router.get(TRENDS_PATH)
def show_trends(request: Request) -> Response:
    """The trends of the latest window, or of the window that ends on the day of its form."""
    form = read_trends_form(request.query_params)
    if form.error:
        return render_trends(request, build_refused_page(form.error))
    try:
        window = read_trends(request.app.state.data_api_client, form.window_end)
    except DataApiError as error:
        if error.state == "data_api_trend_window_not_found":
            return render_trends(request, build_missing_window_page(form.window_end))
        field_error = find_api_window_end_error(error)
        if field_error is None:
            log_data_api_failure(request, error)
            return render_server_error_page(request)
        return render_trends(request, build_refused_page(field_error))
    return render_trends(request, build_trends_page(window))


def render_trends(request: Request, trends: TrendsPage) -> Response:
    """The trends with their form; a day refused, in 422, without table."""
    return render_page(
        request,
        "trends.html",
        {"trends": trends, "link_note": GITHUB_LINK_NOTE},
        current_path=TRENDS_PATH,
        status_code=422 if trends.error else 200,
    )


def log_data_api_failure(request: Request, error: DataApiError) -> None:
    """The state and the HTTP status, never the search nor a value received."""
    logger.warning(
        "data_api_failed: %s http_status=%s request_id=%s",
        error.state,
        "-" if error.http_status is None else error.http_status,
        read_request_id(request),
    )


@router.get(SOURCES_PATH)
def show_sources(request: Request) -> Response:
    return render_page(request, "sources.html", current_path=SOURCES_PATH)


@router.get(ACCESSIBILITY_PATH)
def show_accessibility(request: Request) -> Response:
    return render_page(request, "accessibilite.html", current_path=ACCESSIBILITY_PATH)
