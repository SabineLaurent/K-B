"""The reading of a digest and of its days by the site, on a simulated data API: the contract of
GET /digests/{subject} and GET /digests/{subject}/days (docs/specs-api.md), each answer out of it
refused."""

from datetime import date

import httpx2
import pytest
from digest_fixture import DAY, DAYS, DIGEST, NOT_FOUND, SUBJECT, make_digest
from pydantic import SecretStr

from k_b.core.config import ITEMS_PER_CLAIM, MAX_CLAIMS, TEXT_CHARS
from k_b.items import MAX_DIGEST_SOURCE_TITLE_CHARS, MAX_DIGEST_SOURCE_URL_CHARS
from k_b.web.data_api_client import (
    DataApiError,
    build_data_api_client,
    list_digest_days,
    read_digest,
)
from k_b.web.settings import DataApiAccess

ASKED_DAY = date.fromisoformat(DAY)


def make_client(body, status_code=200):
    """The client of the site, answered body by a data API that keeps each request."""
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(status_code, json=body)

    access = DataApiAccess(base_url="http://127.0.0.1:8000", api_key=SecretStr("k"))
    client = build_data_api_client(access, transport=httpx2.MockTransport(handler))
    return client, requests


def read_state(body, status_code=200, day=None):
    client, _ = make_client(body, status_code)
    with pytest.raises(DataApiError) as raised:
        read_digest(client, SUBJECT, day)
    return raised.value.state


def test_the_latest_digest_is_asked_without_a_day_and_read_whole():
    client, requests = make_client(DIGEST)

    digest = read_digest(client, SUBJECT, None)

    [request] = requests
    assert request.url.path == f"/digests/{SUBJECT}"
    assert "day" not in request.url.params
    assert digest.day == ASKED_DAY
    assert digest.model == "gpt-6.1-sol"
    assert [claim.item_ids for claim in digest.claims] == [[9], [10, 17]]
    assert [source.item_id for source in digest.sources] == [9, 10, 17]


def test_the_day_asked_is_sent_in_the_format_of_the_route():
    client, requests = make_client(DIGEST)

    read_digest(client, SUBJECT, ASKED_DAY)

    assert requests[0].url.params["day"] == DAY


def test_a_digest_not_found_is_named():
    assert read_state(NOT_FOUND, 404) == "data_api_digest_not_found"


def test_another_404_is_an_answer_out_of_the_contract():
    assert read_state({"error": "route_not_found"}, 404) == "data_api_invalid_response"


def test_a_failure_of_watch_is_the_data_api_unavailable():
    """503 watch_unconfigured: kb serve-data without the settings of the storage."""
    assert read_state({"error": "watch_unconfigured"}, 503) == "data_api_unavailable"


@pytest.mark.parametrize(
    ("changes", "day"),
    [
        # Another subject, or another day than the one asked: never shown as its answer.
        ({"subject": "models"}, None),
        ({"day": "2026-11-19"}, ASKED_DAY),
        # A claim that cites a source the digest does not list (OWASP LLM07).
        (
            {"claims": [{"text": "Une affirmation.", "item_ids": [9, 99]}]},
            None,
        ),
        # written without a claim, a claim without written.
        ({"outcome": "written", "claims": [], "sources": []}, None),
        ({"outcome": "no_claim"}, None),
        # A reading cut that names neither its kind nor its date.
        ({"items_capped": True}, None),
        ({"capped_kind": "paper"}, None),
        # A kind the watch never reads.
        (
            {
                "items_capped": True,
                "capped_kind": "clip",
                "covered_after": "2026-11-21T09:05:00Z",
            },
            None,
        ),
        # The bounds of items.py and core/config.py.
        ({"claims": [DIGEST["claims"][0]] * (MAX_CLAIMS + 1)}, None),
        (
            {"claims": [{"text": "a" * (TEXT_CHARS[1] + 1), "item_ids": [9]}]},
            None,
        ),
        ({"claims": [{"text": "", "item_ids": [9]}]}, None),
        (
            {
                "claims": [
                    {
                        "text": "Une affirmation.",
                        "item_ids": [9] * (ITEMS_PER_CLAIM[1] + 1),
                    }
                ]
            },
            None,
        ),
        ({"claims": [{"text": "Une affirmation.", "item_ids": []}]}, None),
        (
            {
                "sources": [
                    {
                        "item_id": source_id,
                        "title": "t" * (MAX_DIGEST_SOURCE_TITLE_CHARS + 1),
                        "url": None,
                    }
                    for source_id in (9, 10, 17)
                ]
            },
            None,
        ),
        (
            {
                "sources": [
                    {
                        "item_id": source_id,
                        "title": "Un titre",
                        "url": "https://" + "a" * MAX_DIGEST_SOURCE_URL_CHARS,
                    }
                    for source_id in (9, 10, 17)
                ]
            },
            None,
        ),
        # A model out of the form kb writes: shown as code on the page.
        ({"model": "gpt 6 <b>"}, None),
    ],
)
def test_an_answer_out_of_the_contract_is_refused(changes, day):
    assert read_state(make_digest(**changes), day=day) == "data_api_invalid_response"


def test_a_digest_cut_names_its_kind_and_its_date():
    client, _ = make_client(
        make_digest(
            items_capped=True,
            capped_kind="newsletter_article",
            covered_after="2026-11-21T09:05:00Z",
        )
    )

    digest = read_digest(client, SUBJECT, None)

    assert digest.capped_kind == "newsletter_article"
    assert digest.covered_after is not None


def test_the_days_of_a_subject_are_asked_thirty_at_most():
    client, requests = make_client(DAYS)

    days = list_digest_days(client, SUBJECT)

    [request] = requests
    assert request.url.path == f"/digests/{SUBJECT}/days"
    assert request.url.params["limit"] == "30"
    assert days.days[0] == ASKED_DAY
    assert days.total == 4


@pytest.mark.parametrize(
    "body",
    [
        {"days": [DAY] * 31, "total": 31},
        {"days": [DAY, "2026-11-19"], "total": 1},
        {"days": ["23/11/2026"], "total": 1},
    ],
)
def test_days_out_of_the_contract_are_refused(body):
    client, _ = make_client(body)

    with pytest.raises(DataApiError) as raised:
        list_digest_days(client, SUBJECT)

    assert raised.value.state == "data_api_invalid_response"
