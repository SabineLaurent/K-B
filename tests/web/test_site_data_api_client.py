"""The reading of the feed, of the detail of an item and of the trends by the data API: against the
real data API on the test base, and a simulated transport for the answers the base cannot give."""

import json
import secrets
from datetime import date

import httpx2
import pytest
from feed_fixture import ITEMS_PAGE
from item_fixture import (
    ADVISORY_WITHOUT_CVE,
    CLIP,
    ITEM_DETAILS,
    PAPER,
    ZOTERO_ENTRY,
    make_detail,
)
from pydantic import SecretStr
from trends_fixture import OLDER_WINDOW_END, TRENDS, make_trends

from k_b.core.config import (
    DATA_API_CONNECT_TIMEOUT_SECONDS,
    DATA_API_POOL_TIMEOUT_SECONDS,
    DATA_API_WRITE_TIMEOUT_SECONDS,
    MAX_WEB_DATA_API_BODY_BYTES,
    WEB_DATA_API_READ_TIMEOUT_SECONDS,
    WEB_DATA_API_REQUEST_DEADLINE_SECONDS,
)
from k_b.web.data_api_client import (
    FEED_KINDS,
    DataApiError,
    ExcludedItem,
    FeedQuery,
    build_data_api_client,
    list_feed_items,
    read_item,
    read_trends,
)
from k_b.web.settings import DataApiAccess

# Made for the test: never a real key.
TEST_API_KEY = secrets.token_urlsafe(32)
# Before every date of the test base, the withdrawn vulnerability of 2021 included.
SINCE_ALL = date(2020, 1, 1)
QUERY = FeedQuery(kinds=FEED_KINDS, since_day=SINCE_ALL, q=None, offset=0)


def make_client(handler):
    """The client of the site, its answers given by handler, never by the network."""
    access = DataApiAccess(
        base_url="http://127.0.0.1:8000", api_key=SecretStr(TEST_API_KEY)
    )
    return build_data_api_client(access, transport=httpx2.MockTransport(handler))


def answer(status_code, body=None, **options):
    return lambda request: httpx2.Response(status_code, json=body, **options)


def read_state(http_client, query=QUERY, **options):
    with pytest.raises(DataApiError) as raised:
        list_feed_items(http_client, query, **options)
    return raised.value


def test_the_feed_reads_the_five_kinds_of_the_real_data_api_never_a_zotero_entry_nor_a_clip(
    data_api,
):
    page = list_feed_items(data_api, QUERY)

    assert page.total == 14
    assert len(page.items) == 14
    assert {item.kind for item in page.items} == set(FEED_KINDS)
    assert page.items[0].id == 12


def test_the_query_sends_the_five_kinds_a_page_of_20_its_offset_and_since_in_utc(
    data_api,
):
    query = FeedQuery(
        kinds=FEED_KINDS,
        since_day=date(2026, 10, 7),
        q="langchain",
        offset=40,
    )

    list_feed_items(data_api, query)

    [request] = data_api.requests
    assert request.url.path == "/items"
    assert request.url.params.get_list("kind") == list(FEED_KINDS)
    assert request.url.params["limit"] == "20"
    assert request.url.params["offset"] == "40"
    assert request.url.params["since"] == "2026-10-07T00:00:00Z"
    assert request.url.params["q"] == "langchain"


def test_since_writes_a_year_on_four_digits_whatever_the_c_library():
    """strftime leaves the width of %Y to the C library: 1 on Linux, refused by the data API."""
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=ITEMS_PAGE)

    query = FeedQuery(kinds=FEED_KINDS, since_day=date(1, 1, 1), q=None, offset=0)
    list_feed_items(make_client(handler), query)

    assert requests[0].url.params["since"] == "0001-01-01T00:00:00Z"


def test_no_search_sends_no_q(data_api):
    list_feed_items(data_api, QUERY)

    [request] = data_api.requests
    assert "q" not in request.url.params


def test_the_key_of_the_client_web_goes_in_the_header_authorization():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=ITEMS_PAGE)

    list_feed_items(make_client(handler), QUERY)

    assert requests[0].headers["Authorization"] == f"Bearer {TEST_API_KEY}"


def test_the_client_has_its_timeouts_follows_no_redirection_and_reads_no_environment():
    http_client = make_client(answer(200, ITEMS_PAGE))

    assert http_client.timeout == httpx2.Timeout(
        connect=DATA_API_CONNECT_TIMEOUT_SECONDS,
        read=WEB_DATA_API_READ_TIMEOUT_SECONDS,
        write=DATA_API_WRITE_TIMEOUT_SECONDS,
        pool=DATA_API_POOL_TIMEOUT_SECONDS,
    )
    assert http_client.follow_redirects is False
    assert http_client.trust_env is False


def test_the_read_timeout_covers_the_wake_up_of_the_data_api():
    """The data API at zero replicas wakes in 20 to 26 s (#414)."""
    assert WEB_DATA_API_READ_TIMEOUT_SECONDS >= 26
    assert WEB_DATA_API_REQUEST_DEADLINE_SECONDS > WEB_DATA_API_READ_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("handler", "state", "http_status"),
    [
        (answer(401, {"error": "invalid_api_key"}), "data_api_unauthorized", 401),
        (answer(429, {"error": "rate_limit_exceeded"}), "data_api_rate_limited", 429),
        (answer(500, {"error": "database_error"}), "data_api_unavailable", 500),
        (answer(503, {"error": "query_timeout"}), "data_api_unavailable", 503),
        (answer(404, {"error": "route_not_found"}), "data_api_invalid_response", 404),
        (
            answer(302, headers={"Location": "https://example.org/items"}),
            "data_api_invalid_response",
            302,
        ),
        (answer(200, {"items": []}), "data_api_invalid_response", 200),
        (
            lambda request: httpx2.Response(200, content=b"not json"),
            "data_api_invalid_response",
            200,
        ),
    ],
    ids=[
        "unauthorized",
        "rate-limited",
        "server-error",
        "unavailable",
        "route-not-found",
        "redirection",
        "out-of-schema",
        "not-json",
    ],
)
def test_each_answer_but_a_page_is_a_named_state(handler, state, http_status):
    error = read_state(make_client(handler))

    assert (error.state, error.http_status) == (state, http_status)


@pytest.mark.parametrize("kind", ["zotero_entry", "clip"])
def test_a_kind_out_of_the_five_is_refused(kind):
    page = json.loads(json.dumps(ITEMS_PAGE))
    page["items"].append(
        {
            "id": 99,
            "kind": kind,
            "title": "A page kept",
            "source_date": "2026-10-07T00:00:00Z",
            "url": None,
            "withdrawn_at": None,
        }
    )

    assert read_state(make_client(answer(200, page))).state == (
        "data_api_invalid_response"
    )


def test_a_field_the_data_api_adds_is_ignored():
    page = json.loads(json.dumps(ITEMS_PAGE))
    page["items"][0]["rank"] = 3
    page["generated_at"] = "2026-11-11T00:00:00Z"

    assert len(list_feed_items(make_client(answer(200, page)), QUERY).items) == 14


def test_a_negative_total_is_refused():
    page = {**ITEMS_PAGE, "total": -1}

    assert read_state(make_client(answer(200, page))).state == (
        "data_api_invalid_response"
    )


def test_a_parameter_refused_gives_its_names_never_its_value():
    error = read_state(
        make_client(
            answer(422, {"error": "invalid_parameter", "parameters": ["q", "since"]})
        )
    )

    assert error.state == "data_api_invalid_parameter"
    assert error.http_status == 422
    assert error.parameters == ("q", "since")


def test_a_422_without_its_names_is_an_answer_out_of_schema():
    error = read_state(make_client(answer(422, {"detail": "raw text"})))

    assert error.state == "data_api_invalid_response"


@pytest.mark.parametrize(
    ("raised", "state"),
    [
        (httpx2.ReadTimeout("read"), "data_api_timeout"),
        (httpx2.ConnectTimeout("connect"), "data_api_timeout"),
        (httpx2.ConnectError("refused"), "data_api_unavailable"),
    ],
)
def test_a_failure_of_the_transport_is_a_named_state(raised, state):
    def handler(request):
        raise raised

    error = read_state(make_client(handler))

    assert (error.state, error.http_status) == (state, None)


def test_a_body_beyond_its_bound_is_refused():
    body = b"x" * (MAX_WEB_DATA_API_BODY_BYTES + 1)

    error = read_state(make_client(lambda request: httpx2.Response(200, content=body)))

    assert error.state == "data_api_invalid_response"


def test_a_body_still_read_after_the_deadline_is_a_timeout():
    """The deadline is checked between two pieces: a body sent slowly, piece by piece."""
    moments = iter([0.0, WEB_DATA_API_REQUEST_DEADLINE_SECONDS + 1])
    content = json.dumps(ITEMS_PAGE).encode()

    def handler(request):
        return httpx2.Response(200, stream=httpx2.ByteStream(content))

    error = read_state(make_client(handler), clock=lambda: next(moments))

    assert error.state == "data_api_timeout"


def test_an_error_never_quotes_the_url_nor_the_key():
    def handler(request):
        raise httpx2.ConnectError(f"refused {request.url} {TEST_API_KEY}")

    error = read_state(make_client(handler))

    assert str(error) == "data_api_unavailable"
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


def read_item_state(http_client, item_id=PAPER):
    with pytest.raises(DataApiError) as raised:
        read_item(http_client, item_id)
    return raised.value


@pytest.mark.parametrize("item_id", sorted(ITEM_DETAILS))
def test_the_detail_of_each_kind_is_read_on_the_real_data_api_as_the_fixture_holds_it(
    data_api, item_id
):
    """The fixture is the answer of the data API on its test base: a field it renames or drops
    fails here, not in production."""
    detail = read_item(data_api, item_id)

    [request] = data_api.requests
    assert request.url.path == f"/items/{item_id}"
    assert data_api.get(f"/items/{item_id}").json() == ITEM_DETAILS[item_id]
    assert (detail.id, detail.kind) == (item_id, ITEM_DETAILS[item_id]["kind"])


@pytest.mark.parametrize(
    ("item_id", "kind"), [(ZOTERO_ENTRY, "zotero_entry"), (CLIP, "clip")]
)
def test_a_zotero_entry_or_a_clip_is_read_by_its_kind_alone(data_api, item_id, kind):
    """Its body is parsed, never modelled: only its kind is kept, for the page not found."""
    detail = read_item(data_api, item_id)

    assert detail == ExcludedItem(kind=kind)


def test_an_item_the_base_does_not_hold_is_named(data_api):
    error = read_item_state(data_api, 999)

    assert (error.state, error.http_status) == ("data_api_item_not_found", 404)


def test_the_detail_sends_the_key_of_the_client_web():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=ITEM_DETAILS[PAPER])

    read_item(make_client(handler), PAPER)

    assert requests[0].url.path == f"/items/{PAPER}"
    assert requests[0].headers["Authorization"] == f"Bearer {TEST_API_KEY}"


@pytest.mark.parametrize(
    "body",
    [{"error": "route_not_found"}, {"error": "trend_window_not_found"}, None],
    ids=["route-not-found", "trend-window-not-found", "not-json"],
)
def test_a_404_other_than_item_not_found_is_an_answer_out_of_schema(body):
    """One state by route: the 404 of the ingress of Azure, without JSON, is no item missing."""
    handler = (
        answer(404, body)
        if body is not None
        else (lambda request: httpx2.Response(404, content=b"<html>Not Found</html>"))
    )

    error = read_item_state(make_client(handler))

    assert (error.state, error.http_status) == ("data_api_invalid_response", 404)


@pytest.mark.parametrize(
    ("handler", "state", "http_status"),
    [
        (answer(401, {"error": "invalid_api_key"}), "data_api_unauthorized", 401),
        (answer(429, {"error": "rate_limit_exceeded"}), "data_api_rate_limited", 429),
        (answer(503, {"error": "query_timeout"}), "data_api_unavailable", 503),
        (answer(200, {"kind": "paper"}), "data_api_invalid_response", 200),
    ],
    ids=["unauthorized", "rate-limited", "unavailable", "out-of-schema"],
)
def test_each_answer_but_a_detail_is_a_named_state(handler, state, http_status):
    error = read_item_state(make_client(handler))

    assert (error.state, error.http_status) == (state, http_status)


def test_a_field_the_data_api_adds_to_a_detail_is_ignored():
    body = make_detail(PAPER, doi="10.1000/182")

    assert read_item(make_client(answer(200, body)), PAPER).id == PAPER


def test_an_advisory_without_package_is_read():
    body = make_detail(ADVISORY_WITHOUT_CVE, packages=[])

    assert (
        read_item(make_client(answer(200, body)), ADVISORY_WITHOUT_CVE).packages == []
    )


@pytest.mark.parametrize(
    "ghsa_id",
    [chr(0x01), "GHSA-0000-0000-0000", "ghsa-fjqc-hq36-qh5p", "GHSA-fjqc-hq36"],
)
def test_an_advisory_id_out_of_the_form_the_base_holds_is_an_invalid_answer(ghsa_id):
    """The base holds GHSA_ID by its GLOB (items.py): another form is no answer of the data API."""
    body = make_detail(ADVISORY_WITHOUT_CVE, ghsa_id=ghsa_id)

    error = read_item_state(make_client(answer(200, body)), ADVISORY_WITHOUT_CVE)

    assert error.state == "data_api_invalid_response"


def read_trends_state(http_client, window_end=None):
    with pytest.raises(DataApiError) as raised:
        read_trends(http_client, window_end)
    return raised.value


def test_the_latest_trends_are_read_on_the_real_data_api_as_the_fixture_holds_them(
    data_api,
):
    """Without window_end, the latest window; the fixture is the answer of the test base."""
    window = read_trends(data_api, None)

    [request] = data_api.requests
    assert request.url.path == "/trends"
    assert "window_end" not in request.url.params
    assert data_api.get("/trends").json() == TRENDS
    assert window.window_end == date(2026, 10, 10)
    assert [trend.repository_name for trend in window.trends] == [
        trend["repository_name"] for trend in TRENDS["trends"]
    ]


def test_the_trends_of_a_window_send_its_last_day(data_api):
    window = read_trends(data_api, date.fromisoformat(OLDER_WINDOW_END))

    [request] = data_api.requests
    assert request.url.params["window_end"] == OLDER_WINDOW_END
    assert window.window_end == date(2026, 10, 9)
    assert len(window.trends) == 2


def test_a_window_the_base_does_not_hold_is_named(data_api):
    error = read_trends_state(data_api, date(2026, 10, 11))

    assert (error.state, error.http_status) == ("data_api_trend_window_not_found", 404)


def test_the_trends_send_the_key_of_the_client_web():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=TRENDS)

    read_trends(make_client(handler), None)

    assert requests[0].headers["Authorization"] == f"Bearer {TEST_API_KEY}"


@pytest.mark.parametrize(
    "body",
    [{"error": "item_not_found"}, {"error": "route_not_found"}, None],
    ids=["item-not-found", "route-not-found", "not-json"],
)
def test_a_404_other_than_trend_window_not_found_is_an_answer_out_of_schema(body):
    """One state by route, as for the detail."""
    handler = (
        answer(404, body)
        if body is not None
        else (lambda request: httpx2.Response(404, content=b"<html>Not Found</html>"))
    )

    error = read_trends_state(make_client(handler))

    assert (error.state, error.http_status) == ("data_api_invalid_response", 404)


def test_a_window_end_refused_by_the_data_api_gives_its_name():
    handler = answer(422, {"error": "invalid_parameter", "parameters": ["window_end"]})

    error = read_trends_state(make_client(handler), date(2026, 10, 10))

    assert (error.state, error.parameters) == (
        "data_api_invalid_parameter",
        ("window_end",),
    )


@pytest.mark.parametrize(
    "body",
    [
        make_trends(count=61),
        make_trends(trends=[]),
        make_trends(window_end="2026-10-10T00:00:00Z"),
        # Its window would start before the first day a date holds.
        make_trends(window_end="0001-01-02"),
        make_trends(
            trends=[{**TRENDS["trends"][0], "repository_name": "<b>owner</b>/repo"}]
        ),
        make_trends(trends=[{**TRENDS["trends"][0], "stars_gained": -1}]),
        make_trends(trends=[{**TRENDS["trends"][0], "forks_gained": 2**63}]),
    ],
    ids=[
        "61-rows",
        "no-row",
        "a-moment",
        "before-the-first-window",
        "name-out-of-form",
        "stars-negative",
        "forks-beyond-64-bits",
    ],
)
def test_trends_out_of_the_contract_are_an_invalid_answer(body):
    """60 rows at most; a window exists by its rows only, which its 404 says (docs/specs-api.md)."""
    error = read_trends_state(make_client(answer(200, body)))

    assert error.state == "data_api_invalid_response"


def test_a_field_the_data_api_adds_to_the_trends_is_ignored():
    body = make_trends(window_start="2026-10-08")

    assert read_trends(make_client(answer(200, body)), None).window_end == date(
        2026, 10, 10
    )
