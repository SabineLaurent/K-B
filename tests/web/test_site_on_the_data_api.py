"""The site on the real data API of its test base, in memory, without network: a filter of the feed
refused, a filter kept, then the detail of an item by the title of its card (C17.3 of the
certification: an input validated and a second screen). Not marked e2e: it runs in the CI."""

import re

import pytest
from fastapi.testclient import TestClient
from site_client import NOW, OPERATOR_HEADERS, OPERATOR_ID

from k_b.web.app import create_app

CARD_TITLE = re.compile(
    r'<h2 class="card-title"[^>]*><a href="(/items/[0-9]+)">([^<]+)</a></h2>'
)


@pytest.fixture
def site(data_api):
    """The site, its client of the data API the data API of the test base."""
    return TestClient(
        create_app(
            operator_id=OPERATOR_ID, data_api_client=data_api, clock=lambda: NOW
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
        '<p id="start-error" class="field-error">Date de début invalide: un jour attendu,'
        " sous la forme AAAA-MM-JJ.</p>" in response.text
    )
    start = re.search(r'<input id="start"[^>]*>', response.text)
    assert start is not None
    assert 'aria-invalid="true"' in start.group(0)
    assert 'aria-describedby="start-error start-help"' in start.group(0)
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
