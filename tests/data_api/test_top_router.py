"""GET /tops/{top} and GET /tops/{top}/days: the twins of the sheets of the tops, read in watch
(#559; docs/specs-api.md, "GET /tops/{top}")."""

import json
import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path

import pytest
import requests
from exchange.storage_fakes import (
    FORGED_LOG_LINE,
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    TEST_IDENTITY_ENDPOINT,
    FakeBlob,
    FakeContainer,
    FakeCredential,
    FakeTransport,
    answer_error,
    answer_identity_refusal,
    answer_identity_with,
    answer_token,
    names_the_spotted_blob,
    remove_online_variables,
    set_identity_endpoint,
)
from fastapi.testclient import TestClient
from pydantic import SecretStr

from k_b.core.api_keys import API_KEY_VARIABLE_PREFIX
from k_b.core.api_settings import OPENAPI_PATH
from k_b.core.config import (
    DATA_API_STORAGE_CONNECT_TIMEOUT_SECONDS,
    DATA_API_STORAGE_READ_TIMEOUT_SECONDS,
    DAYS_LIMIT,
    MAX_DAYS_LIMIT,
    MAX_DAYS_OFFSET,
    MAX_TOP_LIMIT,
    MAX_WATCH_FOLDER_NAMES,
    MAX_WATCH_FOLDER_PAGES,
    MAX_WATCH_SHEET_BYTES,
    MAX_WEB_DATA_API_BODY_BYTES,
    TOP_LIMIT,
    WATCH_CACHE_SECONDS,
    WATCH_CACHED_TOPS,
    WATCH_CONTAINER,
    WEB_CLIENT,
)
from k_b.data_api import watch_reading
from k_b.data_api.app import create_app
from k_b.data_api.watch_reading import TOP_TWINS, WatchReader, open_watch_reader
from k_b.etl.raw_store import RawStore
from k_b.etl.sources.github import most_starred as github_most_starred
from k_b.etl.tops import Top
from k_b.exchange.storage import (
    ExchangeStorageError,
    ExchangeStorageSettings,
    open_container_client,
)
from k_b.items import MAX_INT64, MAX_TOP_DESCRIPTION_CHARS
from k_b.post.top_sheets import write_top_sheets
from k_b.web import settings as web_settings

# Today for the reader: a twin of a later day is left aside.
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
SENT_ON = datetime(2026, 11, 10, 8, 5, tzinfo=UTC)
# A text of a twin that a log must never quote.
SPOTTED_TEXT = "A text of a twin spotted in the log 9W2KD"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
STARRED_TOP = Top(
    "most_starred",
    "raw/automated_watch/github_most_starred",
    partial(github_most_starred.read_top_entries, expected_size=3),
    "Étoiles",
    "dépôts GitHub les plus étoilés",
)


def name_twin(day, top="most_starred"):
    return f"tops/{top}/{day}.json"


def make_repository(rank, description="A description", count=10):
    name = f"owner{rank}/repository{rank}"
    return {
        "rank": rank,
        "repository_name": name,
        "url": f"https://github.com/{name}",
        "description": description,
        "description_truncated": False,
        "count": count,
    }


def make_twin(day="2026-11-10", top="most_starred", repositories=None, ranked_at=None):
    """The twin kb write-tops writes for the top of a day, as JSON bytes."""
    return json.dumps(
        {
            "top": top,
            "ranked_at": ranked_at or f"{day}T08:00:00Z",
            "repositories": [make_repository(1)]
            if repositories is None
            else repositories,
        }
    ).encode()


def put_twin(container, day="2026-11-10", top="most_starred", content=None):
    container.blobs[name_twin(day, top)] = FakeBlob(
        make_twin(day, top) if content is None else content, SENT_ON
    )


class MonotonicClock:
    """The monotonic clock of the reader, moved by the test."""

    def __init__(self):
        self.seconds = 1000.0

    def __call__(self):
        return self.seconds


@pytest.fixture
def watch():
    return FakeContainer(WATCH_CONTAINER)


@pytest.fixture
def clock():
    return MonotonicClock()


@pytest.fixture
def web_keys():
    """The key of the site and of another client, made for the test."""
    return {
        WEB_CLIENT: SecretStr(secrets.token_urlsafe(32)),
        "TERMINAL": SecretStr(secrets.token_urlsafe(32)),
    }


def authorize(keys, client=WEB_CLIENT):
    return {"Authorization": f"Bearer {keys[client].get_secret_value()}"}


@pytest.fixture
def web_headers(web_keys):
    return authorize(web_keys)


def make_reader(handle, clock):
    """The reader of watch on a fake storage answered by handle, today being TODAY."""
    return WatchReader(
        open_container_client(
            TEST_ACCOUNT_URL,
            WATCH_CONTAINER,
            FakeCredential(),
            FakeTransport(handle),
            retry_total=0,
        ),
        now=lambda: NOW,
        monotonic=clock,
    )


@pytest.fixture
def make_top_client(items_database, web_keys, clock):
    """A client of the data API, on the test base of the readers, whose watch handle answers."""

    def make(handle):
        return TestClient(
            create_app(
                items_database,
                web_keys,
                openapi_url=OPENAPI_PATH,
                watch=make_reader(handle, clock),
            ),
            base_url="http://localhost",
            raise_server_exceptions=False,
        )

    return make


@pytest.fixture
def top_client(make_top_client, watch):
    return make_top_client(watch.handle)


# --- What a twin serves.


def test_the_twin_kb_write_tops_writes_is_served_by_the_route(
    tmp_path, top_client, watch, web_headers
):
    data_dir, vault_dir = tmp_path / "data", tmp_path / "vault"
    ranking = data_dir / STARRED_TOP.folder_key / "2026-11-10T093000Z.json"
    ranking.parent.mkdir(parents=True)
    ranking.write_bytes(
        (FIXTURES_DIR / "github_most_starred_extract.json").read_bytes()
    )
    vault_dir.mkdir()
    write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)
    twin = vault_dir / "veille" / name_twin("2026-11-10")
    put_twin(watch, content=twin.read_bytes())

    response = top_client.get("/tops/most_starred", headers=web_headers)

    assert response.status_code == 200
    served = response.json()
    written = json.loads(twin.read_bytes())
    assert served == {
        "top": "most_starred",
        "day": "2026-11-10",
        "ranked_at": "2026-11-10T09:30:00Z",
        "repositories": written["repositories"],
    }


def test_without_day_the_most_recent_twin_is_served(top_client, watch, web_headers):
    for day in ("2026-11-08", "2026-11-10", "2026-11-09"):
        put_twin(watch, day)

    response = top_client.get("/tops/most_starred", headers=web_headers)

    assert response.json()["day"] == "2026-11-10"


def test_a_day_given_serves_the_twin_of_that_day(top_client, watch, web_headers):
    for day in ("2026-11-08", "2026-11-10"):
        put_twin(watch, day)

    response = top_client.get("/tops/most_starred?day=2026-11-08", headers=web_headers)

    assert response.json()["day"] == "2026-11-08"
    assert response.json()["ranked_at"] == "2026-11-08T08:00:00Z"


def test_each_top_reads_its_own_folder(top_client, watch, web_headers):
    put_twin(watch, "2026-11-10", "most_starred")
    put_twin(watch, "2026-11-09", "most_forked")

    response = top_client.get("/tops/most_forked", headers=web_headers)

    assert (response.json()["top"], response.json()["day"]) == (
        "most_forked",
        "2026-11-09",
    )


def test_a_day_without_its_twin_is_not_found(top_client, watch, web_headers):
    put_twin(watch, "2026-11-09", "most_forked")
    put_twin(watch, "2026-11-10", "most_starred")

    response = top_client.get("/tops/most_starred?day=2026-11-09", headers=web_headers)

    assert (response.status_code, response.json()) == (404, {"error": "top_not_found"})


def test_an_empty_folder_is_not_found(top_client, watch, web_headers):
    put_twin(watch, "2026-11-10", "most_forked")

    response = top_client.get("/tops/most_starred", headers=web_headers)

    assert (response.status_code, response.json()) == (404, {"error": "top_not_found"})


def test_an_empty_folder_has_no_day(top_client, watch, web_headers):
    put_twin(watch, "2026-11-10", "most_forked")

    response = top_client.get("/tops/most_starred/days", headers=web_headers)

    assert response.json() == {"days": [], "total": 0}


def test_the_first_repositories_are_served_up_to_the_limit(
    top_client, watch, web_headers
):
    repositories = [make_repository(rank) for rank in range(1, TOP_LIMIT + 3)]
    put_twin(watch, content=make_twin(repositories=repositories))

    by_default = top_client.get("/tops/most_starred", headers=web_headers).json()
    two = top_client.get("/tops/most_starred?limit=2", headers=web_headers).json()

    assert [repository["rank"] for repository in by_default["repositories"]] == list(
        range(1, TOP_LIMIT + 1)
    )
    assert [repository["rank"] for repository in two["repositories"]] == [1, 2]


def test_the_days_are_served_most_recent_first_with_their_total(
    top_client, watch, web_headers
):
    for day in range(1, 6):
        put_twin(watch, f"2026-11-0{day}")
        watch.blobs[f"tops/most_starred/2026-11-0{day}.md"] = FakeBlob(
            b"# top", SENT_ON
        )

    page = top_client.get(
        "/tops/most_starred/days?limit=2&offset=1", headers=web_headers
    )

    assert page.json() == {"days": ["2026-11-04", "2026-11-03"], "total": 5}


def test_the_days_are_served_up_to_their_limit_by_default(
    top_client, watch, web_headers
):
    first = date(2026, 9, 1)
    for offset in range(DAYS_LIMIT + 1):
        put_twin(watch, (first + timedelta(days=offset)).isoformat())

    page = top_client.get("/tops/most_starred/days", headers=web_headers).json()

    assert (len(page["days"]), page["total"]) == (DAYS_LIMIT, DAYS_LIMIT + 1)


def test_a_day_after_today_is_left_aside(top_client, watch, web_headers):
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    put_twin(watch, TODAY.isoformat())
    put_twin(watch, tomorrow)

    latest = top_client.get("/tops/most_starred", headers=web_headers)
    days = top_client.get("/tops/most_starred/days", headers=web_headers)
    asked = top_client.get(f"/tops/most_starred?day={tomorrow}", headers=web_headers)

    assert latest.json()["day"] == TODAY.isoformat()
    assert days.json() == {"days": [TODAY.isoformat()], "total": 1}
    assert asked.status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "tops/most_starred/2026-11-10.md",
        "tops/most_starred/2026-02-30.json",
        "tops/most_starred/2026-11-9.json",
        "tops/most_starred/sub/2026-11-10.json",
        "tops/most_starred/2026-11-10.json.tmp",
        "tops/most_starred/.2026-11-10.json.k3j9x2qa.tmp",
        "tops/most_starred/2026-11-10.json\n",
    ],
)
def test_a_name_that_is_not_a_twin_is_left_aside(top_client, watch, web_headers, name):
    put_twin(watch, "2026-11-08")
    watch.blobs[name] = FakeBlob(make_twin("2026-11-10"), SENT_ON)

    days = top_client.get("/tops/most_starred/days", headers=web_headers)

    assert days.json() == {"days": ["2026-11-08"], "total": 1}
    assert watch.downloaded_names() == []


@pytest.mark.parametrize(
    "path",
    [
        "/tops/most_starred?limit=0",
        f"/tops/most_starred?limit={MAX_TOP_LIMIT + 1}",
        "/tops/most_starred?day=2026-11-10T00:00:00Z",
        "/tops/most_starred?day=20261110",
        "/tops/most_starred/days?limit=0",
        f"/tops/most_starred/days?limit={MAX_DAYS_LIMIT + 1}",
        "/tops/most_starred/days?offset=-1",
        f"/tops/most_starred/days?offset={MAX_DAYS_OFFSET + 1}",
        "/tops/github_most_starred",
        "/tops/github_most_starred/days",
    ],
)
def test_a_parameter_out_of_its_bounds_is_refused(top_client, web_headers, path):
    response = top_client.get(path, headers=web_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_parameter"


def test_a_top_of_100_with_the_longest_descriptions_stays_under_the_bound_of_the_site(
    top_client, watch, web_headers
):
    # 4 bytes in UTF-8 each, the most a character of a visible text takes once served.
    description = "\U0001f600" * MAX_TOP_DESCRIPTION_CHARS
    name = "o" * 100 + "/" + "r" * 154
    repositories = [
        {
            "rank": rank,
            "repository_name": name,
            "url": f"https://github.com/{name}",
            "description": description,
            "description_truncated": True,
            "count": MAX_INT64,
        }
        for rank in range(1, MAX_TOP_LIMIT + 1)
    ]
    put_twin(watch, content=make_twin(repositories=repositories))

    response = top_client.get(
        f"/tops/most_starred?limit={MAX_TOP_LIMIT}", headers=web_headers
    )

    assert len(response.json()["repositories"]) == MAX_TOP_LIMIT
    assert len(response.content) < MAX_WEB_DATA_API_BODY_BYTES


# --- Who may read the tops.


@pytest.mark.parametrize("path", ["/tops/most_starred", "/tops/most_starred/days"])
def test_another_client_is_refused_and_the_items_stay_open_to_it(
    top_client, watch, web_keys, path
):
    put_twin(watch)
    terminal = authorize(web_keys, "TERMINAL")

    refused = top_client.get(path, headers=terminal)
    items = top_client.get("/items", headers=terminal)

    assert (refused.status_code, refused.json()) == (
        403,
        {"error": "client_not_allowed"},
    )
    assert items.status_code == 200
    assert watch.requests == []


def test_the_client_of_the_tops_is_the_one_whose_key_the_site_sends():
    assert web_settings.DATA_API_KEY_VARIABLE == API_KEY_VARIABLE_PREFIX + WEB_CLIENT


def test_without_the_settings_of_the_storage_the_tops_answer_503_and_the_items_stay_served(
    items_database, web_keys, web_headers
):
    client = TestClient(
        create_app(items_database, web_keys), base_url="http://localhost"
    )

    tops = client.get("/tops/most_starred", headers=web_headers)
    days = client.get("/tops/most_starred/days", headers=web_headers)
    refused = client.get("/tops/most_starred", headers=authorize(web_keys, "TERMINAL"))
    items = client.get("/items", headers=web_headers)

    assert (tops.status_code, tops.json()) == (503, {"error": "watch_unconfigured"})
    assert (days.status_code, days.json()) == (503, {"error": "watch_unconfigured"})
    assert refused.status_code == 403
    assert items.status_code == 200


# --- The twins refused, never served.


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"{not JSON " + SPOTTED_TEXT.encode(), "json_invalid"),
        (
            make_twin(repositories=[{**make_repository(1), "html_url": SPOTTED_TEXT}]),
            "extra_forbidden",
        ),
        (
            make_twin(
                repositories=[make_repository(1, f"a{chr(0x202E)}{SPOTTED_TEXT}")]
            ),
            "value_error",
        ),
        (
            make_twin(
                repositories=[
                    {**make_repository(1), "url": f"javascript:alert('{SPOTTED_TEXT}')"}
                ]
            ),
            "value_error",
        ),
        (make_twin(repositories=[make_repository(2)]), "value_error"),
        (make_twin(top="most_forked"), "top_not_its_folder"),
        (
            make_twin(ranked_at="2026-11-09T23:59:59Z"),
            "ranked_at_not_its_day",
        ),
        (
            make_twin(ranked_at="2026-11-10T01:00:00+02:00"),
            "ranked_at_not_its_day",
        ),
    ],
)
def test_a_twin_out_of_its_schema_is_refused_and_its_text_never_logged(
    top_client, watch, web_headers, caplog, content, reason
):
    put_twin(watch, content=content)

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = top_client.get("/tops/most_starred", headers=web_headers)

    assert (response.status_code, response.json()) == (
        502,
        {"error": "watch_production_refused"},
    )
    refusals = [
        record.getMessage()
        for record in caplog.records
        if "watch_production_refused" in record.getMessage()
    ]
    assert len(refusals) == 1
    assert "most_starred of 2026-11-10" in refusals[0]
    assert reason in refusals[0]
    assert SPOTTED_TEXT not in caplog.text
    assert SPOTTED_TEXT not in response.text


def test_a_twin_larger_than_a_sheet_is_refused_without_its_download(
    top_client, watch, web_headers
):
    put_twin(watch, content=b" " * (MAX_WATCH_SHEET_BYTES + 1))

    response = top_client.get("/tops/most_starred", headers=web_headers)

    assert (response.status_code, response.json()) == (
        502,
        {"error": "watch_production_refused"},
    )
    assert watch.downloaded_names() == []


def test_a_twin_refused_stays_refused_without_a_new_download(
    top_client, watch, web_headers
):
    put_twin(watch, content=make_twin(top="most_forked"))

    first = top_client.get("/tops/most_starred", headers=web_headers)
    second = top_client.get("/tops/most_starred", headers=web_headers)

    assert (first.status_code, second.status_code) == (502, 502)
    assert watch.downloaded_names() == [name_twin("2026-11-10")]


# --- The storage.


def test_a_twin_changed_since_the_listing_is_503_and_the_listing_read_again(
    top_client, watch, web_headers
):
    put_twin(watch)
    top_client.get("/tops/most_starred/days", headers=web_headers)
    watch.status_of_next_get[name_twin("2026-11-10")] = 412

    changed = top_client.get("/tops/most_starred", headers=web_headers)
    again = top_client.get("/tops/most_starred", headers=web_headers)

    assert (changed.status_code, changed.json()) == (
        503,
        {"error": "watch_production_changed"},
    )
    assert again.status_code == 200
    assert len(watch.listings()) == 2


@pytest.mark.parametrize(
    ("status", "code", "answered", "state"),
    [
        (404, "ContainerNotFound", 503, "exchange_storage_not_found"),
        (403, "AuthorizationPermissionMismatch", 502, "exchange_storage_forbidden"),
        (500, "InternalError", 502, "exchange_storage_failed"),
    ],
)
def test_a_listing_refused_by_the_storage_answers_its_state(
    make_top_client, web_headers, status, code, answered, state
):
    client = make_top_client(answer_error(status, code, f"Refused {SPOTTED_BLOB_NAME}"))

    response = client.get("/tops/most_starred", headers=web_headers)

    assert (response.status_code, response.json()) == (answered, {"error": state})


def test_a_container_removed_before_the_download_answers_503(
    top_client, watch, web_headers
):
    put_twin(watch)
    watch.status_of_next_get[name_twin("2026-11-10")] = (404, "ContainerNotFound")

    response = top_client.get("/tops/most_starred", headers=web_headers)

    assert (response.status_code, response.json()) == (
        503,
        {"error": "exchange_storage_not_found"},
    )


def test_a_download_past_its_wait_is_504_without_the_name_of_the_blob(
    make_top_client, watch, web_headers, caplog
):
    put_twin(watch)

    def answer(request):
        if request.method == "GET" and "comp=list" not in request.url:
            raise requests.ReadTimeout(f"read timed out on {SPOTTED_BLOB_NAME}")
        return watch.handle(request)

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = make_top_client(answer).get(
            "/tops/most_starred", headers=web_headers
        )

    assert (response.status_code, response.json()) == (
        504,
        {"error": "exchange_storage_timeout"},
    )
    assert "exchange_storage_timeout" in caplog.text
    assert not names_the_spotted_blob(caplog.text)
    assert not names_the_spotted_blob(response.text)


# --- The listing of a folder (List Blobs, "Remarks": a page may be cut short, with a marker).


def test_a_page_cut_short_with_a_marker_is_followed_to_the_end(
    top_client, watch, web_headers
):
    for day in ("2026-11-08", "2026-11-09", "2026-11-10"):
        put_twin(watch, day)
    watch.listing_page_size = 2

    response = top_client.get("/tops/most_starred/days", headers=web_headers)

    assert response.json()["total"] == 3
    assert len(watch.listings()) == 2


def test_a_folder_of_more_names_than_its_bound_is_refused(
    top_client, watch, web_headers
):
    first = date(2010, 1, 1)
    for offset in range(MAX_WATCH_FOLDER_NAMES + 1):
        put_twin(watch, (first + timedelta(days=offset)).isoformat(), content=b"{}")

    response = top_client.get("/tops/most_starred/days", headers=web_headers)

    assert (response.status_code, response.json()) == (
        502,
        {"error": "watch_listing_too_long"},
    )


def test_a_listing_of_more_pages_than_its_bound_is_refused(
    top_client, watch, web_headers
):
    put_twin(watch)
    # Pages without a name, each with a marker.
    watch.listing_page_size = 0

    response = top_client.get("/tops/most_starred/days", headers=web_headers)

    assert (response.status_code, response.json()) == (
        502,
        {"error": "watch_listing_too_long"},
    )
    assert len(watch.listings()) == MAX_WATCH_FOLDER_PAGES


def test_the_listing_asks_the_folder_of_the_top_only(top_client, watch, web_headers):
    put_twin(watch)

    top_client.get("/tops/most_starred/days", headers=web_headers)

    [listing] = watch.listings()
    assert "prefix=tops%2Fmost_starred%2F" in listing.url
    assert f"maxresults={MAX_WATCH_FOLDER_NAMES}" in listing.url


# --- What the reader keeps.


def test_a_listing_is_kept_until_its_seconds_have_passed(
    top_client, watch, web_headers, clock
):
    put_twin(watch, "2026-11-09")
    top_client.get("/tops/most_starred/days", headers=web_headers)
    put_twin(watch, "2026-11-10")

    clock.seconds += WATCH_CACHE_SECONDS - 1
    kept = top_client.get("/tops/most_starred/days", headers=web_headers)
    clock.seconds += 1
    read_again = top_client.get("/tops/most_starred/days", headers=web_headers)

    assert kept.json()["total"] == 1
    assert read_again.json()["total"] == 2
    assert len(watch.listings()) == 2


def test_a_twin_read_is_kept_by_its_name_and_its_etag(
    top_client, watch, web_headers, clock
):
    put_twin(watch)
    top_client.get("/tops/most_starred", headers=web_headers)
    top_client.get("/tops/most_starred", headers=web_headers)
    put_twin(watch, content=make_twin(repositories=[make_repository(1, count=99)]))
    clock.seconds += WATCH_CACHE_SECONDS

    changed = top_client.get("/tops/most_starred", headers=web_headers)

    assert changed.json()["repositories"][0]["count"] == 99
    assert watch.downloaded_names() == [name_twin("2026-11-10")] * 2


def test_the_oldest_twin_read_is_forgotten_beyond_the_productions_kept(
    top_client, watch, web_headers
):
    days = [
        (date(2026, 11, 1) + timedelta(days=offset)).isoformat()
        for offset in range(WATCH_CACHED_TOPS + 1)
    ]
    for day in days:
        put_twin(watch, day)

    for day in days:
        top_client.get(f"/tops/most_starred?day={day}", headers=web_headers)
    top_client.get(f"/tops/most_starred?day={days[1]}", headers=web_headers)
    top_client.get(f"/tops/most_starred?day={days[0]}", headers=web_headers)

    assert watch.downloaded_names() == [name_twin(day) for day in [*days, days[0]]]


# --- The reader of kb serve-data.


def test_the_reader_of_kb_serve_data_waits_its_timeouts_and_sends_a_request_once(
    monkeypatch, clock
):
    remove_online_variables(monkeypatch)
    set_identity_endpoint(monkeypatch)
    storage_requests = []

    def answer(request):
        if request.url.startswith(TEST_IDENTITY_ENDPOINT):
            return answer_token(request)
        storage_requests.append(request)
        return answer_error(503, "ServerBusy", "busy")(request)

    waits = []

    def build_transport(connect_timeout_seconds, read_timeout_seconds):
        waits.append((connect_timeout_seconds, read_timeout_seconds))
        return FakeTransport(answer)

    monkeypatch.setattr(watch_reading, "build_transport", build_transport)

    with (
        open_watch_reader(
            ExchangeStorageSettings(TEST_ACCOUNT_URL, TEST_CLIENT_ID)
        ) as reader,
        pytest.raises(ExchangeStorageError) as raised,
    ):
        reader.list_days(TOP_TWINS, "most_starred")

    assert raised.value.state == "exchange_storage_failed"
    assert (
        waits
        == [
            (
                DATA_API_STORAGE_CONNECT_TIMEOUT_SECONDS,
                DATA_API_STORAGE_READ_TIMEOUT_SECONDS,
            )
        ]
        * 2
    )
    assert len(storage_requests) == 1


@pytest.mark.parametrize(
    "answer_identity",
    [
        answer_identity_with(500, "text/html", b"<html>Internal Server Error</html>"),
        answer_identity_with(200, "application/json", b"[]"),
        answer_identity_with(500, "application/json", b'{"error": "unavailable"}'),
        answer_identity_refusal,
    ],
    ids=["html_500", "json_list", "json_500", "refusal_400"],
)
def test_a_token_refused_during_a_request_answers_502_no_token(
    monkeypatch, items_database, web_keys, web_headers, caplog, answer_identity
):
    # The data API asks its token in the middle of a request, never by check_identity: the
    # failure of the identity keeps its rule there, never a 500, nor a state of the storage.
    remove_online_variables(monkeypatch)
    set_identity_endpoint(monkeypatch)

    def answer(request):
        if request.url.startswith(TEST_IDENTITY_ENDPOINT):
            return answer_identity(request)
        return answer_error(404, "BlobNotFound", f"Not found {SPOTTED_BLOB_NAME}")(
            request
        )

    monkeypatch.setattr(
        watch_reading, "build_transport", lambda **waits: FakeTransport(answer)
    )

    with (
        open_watch_reader(
            ExchangeStorageSettings(TEST_ACCOUNT_URL, TEST_CLIENT_ID)
        ) as reader,
        caplog.at_level(logging.INFO, logger="k_b"),
    ):
        client = TestClient(
            create_app(
                items_database, web_keys, openapi_url=OPENAPI_PATH, watch=reader
            ),
            base_url="http://localhost",
            raise_server_exceptions=False,
        )
        response = client.get("/tops/most_starred", headers=web_headers)

    assert (response.status_code, response.json()) == (
        502,
        {"error": "exchange_storage_no_token"},
    )
    assert "exchange_storage_no_token" in caplog.text
    assert FORGED_LOG_LINE not in caplog.text
    assert not names_the_spotted_blob(caplog.text)
