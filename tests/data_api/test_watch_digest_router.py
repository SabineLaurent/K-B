"""GET /digests/{subject} and GET /digests/{subject}/days: the twins of the sheets of the digests,
read in watch (#560; docs/specs-api.md, "GET /digests/{subject}"). The storage, its errors and the
listing of a folder are those of the tops (test_top_router.py): one reader for both kinds."""

import dataclasses
import json
import logging
import secrets
from datetime import date, timedelta
from typing import get_args

import pytest
from data_api.test_top_router import (
    SENT_ON,
    SPOTTED_TEXT,
    TODAY,
    MonotonicClock,
    authorize,
    make_reader,
)
from data_api.test_top_router import put_twin as put_top_twin
from exchange.storage_fakes import FakeBlob, FakeContainer
from fastapi.testclient import TestClient
from post.test_ai_api_client import AGENT_DIGEST, SINCE, make_response, to_body
from pydantic import SecretStr

from k_b.core.api_settings import OPENAPI_PATH
from k_b.core.config import (
    DIGEST_SUBJECTS,
    ITEMS_PER_CLAIM,
    MAX_CLAIMS,
    MAX_DAYS_LIMIT,
    MAX_DAYS_OFFSET,
    MAX_DIGEST_TWIN_BYTES,
    MAX_ITEMS_PER_DIGEST,
    MAX_WEB_DATA_API_BODY_BYTES,
    TEXT_CHARS,
    WATCH_CACHE_SECONDS,
    WATCH_CACHED_DIGESTS,
    WATCH_CONTAINER,
    WEB_CLIENT,
)
from k_b.data_api.app import create_app
from k_b.data_api.schemas.watch_digest_schema import DigestSubjectName
from k_b.data_api.watch_reading import DIGEST_TWINS
from k_b.items import (
    MAX_DIGEST_SOURCE_TITLE_CHARS,
    MAX_DIGEST_SOURCE_URL_CHARS,
    MAX_INT64,
    DigestProduction,
)
from k_b.post.ai_api_client import DigestsResponse
from k_b.post.digest_sheets import build_digest_twin, write_digest_twin

SUBJECT = "agent_frameworks"
CLAIM = {"text": "Claude Code publie la version v2.1.287.", "item_ids": [6]}
SOURCE = {
    "item_id": 6,
    "title": "Claude Code 2.1.287",
    "url": "https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
}


def name_twin(day, subject=SUBJECT):
    return f"{subject}/{day}.json"


def make_twin(day="2026-11-10", subject=SUBJECT, **changes):
    """The twin kb digest writes for the subject of a day, as JSON bytes."""
    return json.dumps(
        {
            "subject": subject,
            "since": f"{day}T00:00:00Z",
            "until": f"{day}T08:00:00Z",
            "model": "gpt-6-luna",
            "items_capped": False,
            "capped_kind": None,
            "covered_after": None,
            "outcome": "written",
            "claims": [CLAIM],
            "sources": [SOURCE],
        }
        | changes
    ).encode()


def put_twin(container, day="2026-11-10", subject=SUBJECT, content=None):
    container.blobs[name_twin(day, subject)] = FakeBlob(
        make_twin(day, subject) if content is None else content, SENT_ON
    )


def make_largest_twin():
    """The largest twin DigestProduction lets kb write: each bound at its maximum, each character
    of a text 4 bytes in UTF-8, the most a visible character takes once served."""
    emoji = chr(0x1F600)
    item_ids = [MAX_INT64 - number for number in range(MAX_ITEMS_PER_DIGEST)]
    per_claim = ITEMS_PER_CLAIM[1]
    url = "https://" + "a" * (MAX_DIGEST_SOURCE_URL_CHARS - len("https://"))
    production = DigestProduction.model_validate_json(
        make_twin(
            model="m" * 100,
            items_capped=True,
            capped_kind="newsletter_article",
            covered_after="2026-11-09T00:00:00Z",
            claims=[
                {
                    "text": emoji * TEXT_CHARS[1],
                    "item_ids": item_ids[number * per_claim : (number + 1) * per_claim],
                }
                for number in range(MAX_CLAIMS)
            ],
            sources=[
                {
                    "item_id": item_id,
                    "title": emoji * MAX_DIGEST_SOURCE_TITLE_CHARS,
                    "url": url,
                }
                for item_id in item_ids
            ],
        )
    )
    return production.model_dump_json().encode()


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


@pytest.fixture
def web_headers(web_keys):
    return authorize(web_keys)


@pytest.fixture
def digest_client(items_database, web_keys, clock, watch):
    """A client of the data API, on the test base of the readers, reading the fake watch."""
    return TestClient(
        create_app(
            items_database,
            web_keys,
            openapi_url=OPENAPI_PATH,
            watch=make_reader(watch.handle, clock),
        ),
        base_url="http://localhost",
        raise_server_exceptions=False,
    )


# --- What a twin serves.


def test_the_twin_kb_digest_writes_is_served_by_the_route(
    tmp_path, digest_client, watch, web_headers
):
    digest = AGENT_DIGEST.model_copy(update={"subject": SUBJECT})
    response = DigestsResponse.model_validate_json(
        to_body(
            make_response(
                [digest],
                since_by_subject={SUBJECT: SINCE},
                subjects_without_items=[],
            )
        )
    )
    twin_path = tmp_path / write_digest_twin(
        tmp_path, build_digest_twin(response, SUBJECT, response.digests[0])
    )
    put_twin(watch, "2026-10-21", content=twin_path.read_bytes())

    served = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

    assert served.status_code == 200
    assert served.json() == {
        "day": "2026-10-21",
        **json.loads(twin_path.read_bytes()),
    }


def test_a_digest_without_item_is_served_with_its_outcome(
    digest_client, watch, web_headers
):
    put_twin(watch, content=make_twin(outcome="no_item", claims=[], sources=[]))

    served = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers).json()

    assert (served["outcome"], served["claims"], served["sources"]) == (
        "no_item",
        [],
        [],
    )


def test_without_day_the_most_recent_digest_is_served(
    digest_client, watch, web_headers
):
    for day in ("2026-11-08", "2026-11-10", "2026-11-09"):
        put_twin(watch, day)

    served = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

    assert served.json()["day"] == "2026-11-10"


def test_a_day_given_serves_the_digest_of_that_day(digest_client, watch, web_headers):
    for day in ("2026-11-08", "2026-11-10"):
        put_twin(watch, day)

    served = digest_client.get(
        f"/digests/{SUBJECT}?day=2026-11-08", headers=web_headers
    )

    assert served.json()["day"] == "2026-11-08"
    assert served.json()["until"] == "2026-11-08T08:00:00Z"


def test_each_subject_reads_its_own_folder(digest_client, watch, web_headers):
    put_twin(watch, "2026-11-10", "models")
    put_twin(watch, "2026-11-09", SUBJECT)
    put_top_twin(watch, "2026-11-10")

    served = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)
    days = digest_client.get(f"/digests/{SUBJECT}/days", headers=web_headers)

    assert (served.json()["subject"], served.json()["day"]) == (SUBJECT, "2026-11-09")
    assert days.json() == {"days": ["2026-11-09"], "total": 1}


def test_a_day_without_its_digest_is_not_found(digest_client, watch, web_headers):
    put_twin(watch, "2026-11-09", "models")
    put_twin(watch, "2026-11-10")

    response = digest_client.get(
        f"/digests/{SUBJECT}?day=2026-11-09", headers=web_headers
    )

    assert (response.status_code, response.json()) == (
        404,
        {"error": "digest_not_found"},
    )


def test_an_empty_folder_is_not_found_and_has_no_day(digest_client, watch, web_headers):
    put_twin(watch, "2026-11-10", "models")

    digest = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)
    days = digest_client.get(f"/digests/{SUBJECT}/days", headers=web_headers)

    assert (digest.status_code, digest.json()) == (404, {"error": "digest_not_found"})
    assert (days.status_code, days.json()) == (200, {"days": [], "total": 0})


def test_the_days_are_served_most_recent_first_with_their_total(
    digest_client, watch, web_headers
):
    for day in range(1, 6):
        put_twin(watch, f"2026-11-0{day}")
        watch.blobs[f"{SUBJECT}/2026-11-0{day}.md"] = FakeBlob(b"# Veille", SENT_ON)

    page = digest_client.get(
        f"/digests/{SUBJECT}/days?limit=2&offset=1", headers=web_headers
    )

    assert page.json() == {"days": ["2026-11-04", "2026-11-03"], "total": 5}


def test_a_day_after_today_is_left_aside(digest_client, watch, web_headers):
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    put_twin(watch, TODAY.isoformat())
    put_twin(watch, tomorrow)

    latest = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)
    asked = digest_client.get(f"/digests/{SUBJECT}?day={tomorrow}", headers=web_headers)

    assert latest.json()["day"] == TODAY.isoformat()
    assert asked.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/digests/tops",
        "/digests/tendances/days",
        "/digests/agent_tools",
        "/digests/Models",
        f"/digests/{SUBJECT}?day=2026-11-10T00:00:00Z",
        f"/digests/{SUBJECT}?day=20261110",
        f"/digests/{SUBJECT}/days?limit=0",
        f"/digests/{SUBJECT}/days?limit={MAX_DAYS_LIMIT + 1}",
        f"/digests/{SUBJECT}/days?offset=-1",
        f"/digests/{SUBJECT}/days?offset={MAX_DAYS_OFFSET + 1}",
    ],
)
def test_a_parameter_out_of_its_bounds_is_refused(
    digest_client, watch, web_headers, path
):
    response = digest_client.get(path, headers=web_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_parameter"
    assert watch.requests == []


def test_the_subjects_of_the_route_are_those_of_the_digests():
    assert get_args(DigestSubjectName) == tuple(
        subject.name for subject in DIGEST_SUBJECTS
    )


def test_the_largest_twin_kb_can_write_is_read_and_served_under_the_bound_of_the_site(
    digest_client, watch, web_headers
):
    largest = make_largest_twin()
    put_twin(watch, content=largest)

    response = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

    assert len(largest) <= MAX_DIGEST_TWIN_BYTES
    assert response.status_code == 200
    assert len(response.json()["sources"]) == MAX_ITEMS_PER_DIGEST
    assert len(response.content) < MAX_WEB_DATA_API_BODY_BYTES


# --- Who may read the digests.


@pytest.mark.parametrize("path", [f"/digests/{SUBJECT}", f"/digests/{SUBJECT}/days"])
def test_another_client_is_refused_and_the_items_stay_open_to_it(
    digest_client, watch, web_keys, path
):
    put_twin(watch)
    terminal = authorize(web_keys, "TERMINAL")

    refused = digest_client.get(path, headers=terminal)
    items = digest_client.get("/items", headers=terminal)

    assert (refused.status_code, refused.json()) == (
        403,
        {"error": "client_not_allowed"},
    )
    assert items.status_code == 200
    assert watch.requests == []


def test_without_the_settings_of_the_storage_the_digests_answer_503(
    items_database, web_keys, web_headers
):
    client = TestClient(
        create_app(items_database, web_keys), base_url="http://localhost"
    )

    digest = client.get(f"/digests/{SUBJECT}", headers=web_headers)
    days = client.get(f"/digests/{SUBJECT}/days", headers=web_headers)

    assert (digest.status_code, digest.json()) == (503, {"error": "watch_unconfigured"})
    assert (days.status_code, days.json()) == (503, {"error": "watch_unconfigured"})


# --- The twins refused, never served.


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"{not JSON " + SPOTTED_TEXT.encode(), "json_invalid"),
        (make_twin(request_id=SPOTTED_TEXT), "extra_forbidden"),
        (
            make_twin(claims=[{**CLAIM, "text": f"a{chr(0x202E)}{SPOTTED_TEXT}"}]),
            "value_error",
        ),
        (
            make_twin(
                sources=[{**SOURCE, "url": f"javascript:alert('{SPOTTED_TEXT}')"}]
            ),
            "value_error",
        ),
        (make_twin(claims=[{**CLAIM, "item_ids": [7]}]), "value_error"),
        (make_twin(subject="models"), "subject_not_its_folder"),
        (
            make_twin(since="2026-11-09T00:00:00Z", until="2026-11-09T23:59:59Z"),
            "until_not_its_day",
        ),
        (
            make_twin(since="2026-11-09T00:00:00Z", until="2026-11-10T01:00:00+02:00"),
            "until_not_its_day",
        ),
    ],
    ids=[
        "not_json",
        "extra_field",
        "hidden_character",
        "url_out_of_the_rule",
        "source_not_listed",
        "other_subject",
        "until_the_day_before",
        "until_the_day_before_in_utc",
    ],
)
def test_a_twin_out_of_its_schema_is_refused_and_its_text_never_logged(
    digest_client, watch, web_headers, caplog, content, reason
):
    put_twin(watch, content=content)

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

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
    assert f"{SUBJECT} of 2026-11-10" in refusals[0]
    assert reason in refusals[0]
    assert SPOTTED_TEXT not in caplog.text
    assert SPOTTED_TEXT not in response.text


def test_a_twin_larger_than_the_largest_digest_is_refused_without_its_download(
    digest_client, watch, web_headers, caplog
):
    put_twin(watch, content=b" " * (MAX_DIGEST_TWIN_BYTES + 1))

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

    assert (response.status_code, response.json()) == (
        502,
        {"error": "watch_production_refused"},
    )
    assert f"twin_too_large, {MAX_DIGEST_TWIN_BYTES + 1} bytes" in caplog.text
    assert watch.downloaded_names() == []


def test_a_twin_refused_stays_refused_without_a_new_download(
    digest_client, watch, web_headers
):
    put_twin(watch, content=make_twin(subject="models"))

    first = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)
    second = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

    assert (first.status_code, second.status_code) == (502, 502)
    assert watch.downloaded_names() == [name_twin("2026-11-10")]


def test_a_twin_changed_since_the_listing_is_503_and_its_folder_listed_again(
    digest_client, watch, web_headers
):
    put_twin(watch)
    digest_client.get(f"/digests/{SUBJECT}/days", headers=web_headers)
    watch.status_of_next_get[name_twin("2026-11-10")] = 412

    changed = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)
    again = digest_client.get(f"/digests/{SUBJECT}", headers=web_headers)

    assert (changed.status_code, changed.json()) == (
        503,
        {"error": "watch_production_changed"},
    )
    assert again.status_code == 200
    assert len(watch.listings()) == 2


# --- What the reader keeps.


def test_the_listing_asks_the_folder_of_the_subject_only(
    digest_client, watch, web_headers
):
    put_twin(watch)

    digest_client.get(f"/digests/{SUBJECT}/days", headers=web_headers)

    [listing] = watch.listings()
    assert f"prefix={SUBJECT}%2F" in listing.url


def test_the_listing_of_each_folder_is_kept_apart(
    digest_client, watch, web_headers, clock
):
    put_twin(watch, "2026-11-10", SUBJECT)
    put_twin(watch, "2026-11-09", "models")

    for subject in (SUBJECT, "models", SUBJECT, "models"):
        digest_client.get(f"/digests/{subject}/days", headers=web_headers)
    clock.seconds += WATCH_CACHE_SECONDS
    digest_client.get(f"/digests/{SUBJECT}/days", headers=web_headers)

    assert [
        listing.url.count(f"prefix={SUBJECT}%2F") for listing in watch.listings()
    ] == [
        1,
        0,
        1,
    ]


def test_the_oldest_digest_read_is_forgotten_beyond_the_digests_kept(
    digest_client, watch, web_headers
):
    days = [
        (date(2026, 10, 1) + timedelta(days=offset)).isoformat()
        for offset in range(WATCH_CACHED_DIGESTS + 1)
    ]
    for day in days:
        put_twin(watch, day)

    for day in days:
        digest_client.get(f"/digests/{SUBJECT}?day={day}", headers=web_headers)
    digest_client.get(f"/digests/{SUBJECT}?day={days[1]}", headers=web_headers)
    digest_client.get(f"/digests/{SUBJECT}?day={days[0]}", headers=web_headers)

    assert watch.downloaded_names() == [name_twin(day) for day in [*days, days[0]]]


def test_the_digests_read_never_push_a_top_out_of_the_reader(
    digest_client, watch, web_headers
):
    put_top_twin(watch, "2026-11-10")
    days = [
        (date(2026, 10, 1) + timedelta(days=offset)).isoformat()
        for offset in range(WATCH_CACHED_DIGESTS + 1)
    ]
    for day in days:
        put_twin(watch, day)

    digest_client.get("/tops/most_starred", headers=web_headers)
    for day in days:
        digest_client.get(f"/digests/{SUBJECT}?day={day}", headers=web_headers)
    digest_client.get("/tops/most_starred", headers=web_headers)

    assert watch.downloaded_names().count("tops/most_starred/2026-11-10.json") == 1


def test_a_kind_the_reader_was_not_built_with_is_read_and_kept(watch, clock):
    # A kind added later (#561) needs no list of kinds in the reader.
    kind = dataclasses.replace(DIGEST_TWINS, kept_count=1)
    put_twin(watch)
    reader = make_reader(watch.handle, clock)

    first = reader.read_production(kind, SUBJECT, None)
    again = reader.read_production(kind, SUBJECT, None)

    assert (first.day, again.day) == (date(2026, 11, 10), date(2026, 11, 10))
    assert watch.downloaded_names() == [name_twin("2026-11-10")]
