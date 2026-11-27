"""The site on the real data API of its test base, in memory, without network: a filter of the feed
refused, a filter kept, then the detail of an item by the title of its card (C17.3 of the
certification: an input validated and a second screen); the trends of the base, by their window;
a digest of watch, then the item of one of its sources. Not marked e2e: it runs in the CI."""

import re

import pytest
from data_api.test_watch_digest_router import make_twin, put_twin
from fastapi.testclient import TestClient
from site_client import NOW, OPERATOR_HEADERS, OPERATOR_ID, TEST_VERSION

from k_b.post.ai_api_client import Source
from k_b.post.digest_sheets import build_twin_source
from k_b.web.app import create_app

CARD_TITLE = re.compile(
    r'<h2 class="card-title"[^>]*><a href="(/items/[0-9]+)">([^<]+)</a></h2>'
)


@pytest.fixture
def site(data_api):
    """The site, its client of the data API the data API of the test base."""
    return TestClient(
        create_app(
            operator_id=OPERATOR_ID,
            data_api_client=data_api,
            clock=lambda: NOW,
            version=TEST_VERSION,
        ),
        base_url="http://localhost",
        headers=OPERATOR_HEADERS,
        raise_server_exceptions=False,
    )


def test_a_start_date_that_does_not_exist_is_refused_on_its_field_without_asking_the_api(
    site, data_api
):
    response = site.get("/?period=date&start=2026-02-30")

    assert response.status_code == 422
    assert (
        '<p id="start-error" class="field-error">Erreur. Date de début invalide:'
        " 2026-02-30 n’existe pas. Choisissez un jour qui existe.</p>" in response.text
    )
    start = re.search(r'<input id="start"[^>]*>', response.text)
    assert start is not None
    assert 'aria-invalid="true"' in start.group(0)
    assert 'aria-describedby="start-error start-help"' in start.group(0)
    assert 'value=""' in start.group(0)
    assert '<li class="card">' not in response.text
    assert data_api.requests == []


def test_a_filter_kept_lists_its_items_then_the_title_of_a_card_leads_to_its_detail(
    site, data_api
):
    feed = site.get("/?kind=advisory&period=date&start=2026-01-01")

    assert feed.status_code == 200
    assert feed.text.count('<li class="card">') == 3
    assert "3 items depuis le 1er janvier 2026" in feed.text
    link, title = CARD_TITLE.findall(feed.text)[0]

    detail = site.get(link)

    assert detail.status_code == 200
    h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", detail.text)
    assert h1 is not None
    assert h1.group(1) == title
    assert "Entrée au catalogue KEV" in detail.text
    assert [request.url.path for request in data_api.requests] == ["/items", link]


def test_the_trends_show_the_latest_window_then_the_window_asked_then_one_absent(
    site, data_api
):
    latest = site.get("/tendances")
    older = site.get("/tendances?window_end=2026-10-09")
    absent = site.get("/tendances?window_end=2026-10-11")

    assert [latest.status_code, older.status_code, absent.status_code] == [200] * 3
    assert latest.text.count('<td class="rank">') == 5
    assert older.text.count('<td class="rank">') == 2
    assert (
        "Aucune tendance pour la fenêtre qui se termine le 11 octobre 2026."
        in absent.text
    )
    assert [
        (request.url.path, request.url.params.get("window_end"))
        for request in data_api.requests
    ] == [("/trends", None), ("/trends", "2026-10-09"), ("/trends", "2026-10-11")]


def test_a_digest_of_watch_shows_its_claims_then_a_source_leads_to_the_item_of_its_url(
    site, data_api
):
    """The twin holds its source as kb digest writes it, from the detail the AI API reads
    (post/digest_sheets.py, build_twin_source): the site finds the item again by its URL."""
    paper = data_api.get("/items/1").json()
    source = build_twin_source(
        Source(item_id=1, title=paper["title"], url=paper["url"])
    )
    claim = {
        "text": "Un cadre d’agents ancré sur une chaîne de blocs.",
        "item_ids": [1],
    }
    put_twin(
        data_api.watch,
        "2026-11-10",
        "agent_frameworks",
        make_twin("2026-11-10", "agent_frameworks", claims=[claim], sources=[source]),
    )
    data_api.requests.clear()

    digest = site.get("/comptes-rendus/agent_frameworks")
    [link] = re.findall(r'<a href="(/comptes-rendus/[^"]+/sources/1)"', digest.text)
    item = site.get(link)

    assert digest.status_code == 200
    assert claim["text"] in digest.text
    assert link == "/comptes-rendus/agent_frameworks/2026-11-10/sources/1"
    assert item.status_code == 200
    assert "Retour au compte rendu" in item.text
    assert "Source introuvable" not in item.text
    assert [request.url.path for request in data_api.requests] == [
        "/digests/agent_frameworks",
        "/digests/agent_frameworks/days",
        "/digests/agent_frameworks",
        "/items/1",
    ]
