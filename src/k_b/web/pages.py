"""The pages of the site: the watch feed, the detail of an item, the trends, the sources and the
accessibility (docs/site-web.md, "Pages")."""

import logging
from collections.abc import Sequence

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from k_b.core.api_request_log import read_request_id
from k_b.core.config import DATA_API_MAX_SEARCH_LENGTH
from k_b.web.data_api_client import (
    FEED_KINDS,
    DataApiError,
    ExcludedItem,
    list_feed_items,
    read_item,
    read_trends,
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
)
from k_b.web.item_detail import build_item_page, read_item_id
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
    return render_page(request, "item.html", {"detail": build_item_page(detail)})


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
