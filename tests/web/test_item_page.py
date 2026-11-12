"""The page of the detail of an item, its data API simulated: each kind, its banner, the page not
found, the page 500, the log without the id, a value received always escaped, and the title of a
card of the feed made a link to it (docs/site-web.md, "Détail")."""

import gzip
import logging
import random
import re

import httpx2
import pytest
from feed_fixture import ITEMS_PAGE, make_page
from item_fixture import (
    ADVISORY_ABSENT_FROM_CATALOG,
    ADVISORY_IN_CATALOG,
    ADVISORY_WITHOUT_CVE,
    ITEM_DETAILS,
    NEWSLETTER_ARTICLE,
    PAPER,
    RELEASE,
    VULNERABILITY,
    WITHDRAWN_VULNERABILITY,
    make_detail,
)
from site_client import OPERATOR_HEADERS, make_client, serve

MARK = "<b>mark</b>"
ESCAPED_MARK = "&lt;b&gt;mark&lt;/b&gt;"


class RecordingApi:
    """A data API that answers each request with the body given, and keeps the requests."""

    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx2.Response(self.status_code, json=self.body)


def get_item(path, body=None, handler=None):
    """The page at path, the data API answering body, or by handler."""
    client = make_client(handler=handler or serve(body))
    return client.get(path, headers=OPERATOR_HEADERS)


def show(item_id, **changes):
    return get_item(f"/items/{item_id}", make_detail(item_id, **changes))


@pytest.mark.parametrize(
    ("item_id", "title"),
    [
        (PAPER, "Papier arXiv 2609.31282"),
        (VULNERABILITY, "Faille CVE-2026-86950"),
        (ADVISORY_IN_CATALOG, "Alerte GHSA-fjqc-hq36-qh5p"),
        (RELEASE, "Version v2.1.287 de anthropics/claude-code"),
        (NEWSLETTER_ARTICLE, "Article TLDR AI du 7 octobre 2026, n° 3"),
    ],
)
def test_each_kind_has_its_page_its_title_and_its_h1(item_id, title):
    response = show(item_id)

    assert response.status_code == 200
    assert f"<title>{title} · K-B</title>" in response.text
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", response.text, flags=re.DOTALL)
    assert h1 is not None
    assert h1.group(1) == ITEM_DETAILS[item_id]["title"].replace("'", "&#39;")


def test_the_detail_asks_the_data_api_its_item_by_its_id():
    api = RecordingApi(ITEM_DETAILS[PAPER])

    get_item(f"/items/{PAPER}", handler=api)

    [request] = api.requests
    assert request.url.path == f"/items/{PAPER}"
    assert request.url.query == b""


def test_the_detail_leads_back_to_the_feed_and_marks_no_link_of_the_navigation():
    text = show(PAPER).text

    assert (
        '<a class="back-link" href="/"><span aria-hidden="true">←</span> Retour au fil</a>'
        in text
    )
    assert "aria-current" not in text


def test_the_link_to_the_source_is_a_button_that_opens_a_new_tab_it_announces():
    text = show(PAPER).text

    assert (
        '<a class="button" href="https://arxiv.org/abs/2609.31282" hreflang="en"'
        ' target="_blank" rel="noopener noreferrer">Lire sur arxiv.org' in text
    )
    assert "(en anglais, site externe, nouvel onglet)" in text


def test_a_paper_shows_its_authors_and_its_summary():
    text = show(PAPER, authors=["Ada May Fenwick", "Lena Marsh"]).text

    assert '<p class="item-authors">Auteurs: Ada May Fenwick, Lena Marsh</p>' in text
    assert '<h2 id="resume">Résumé</h2>' in text
    assert '<section class="item-text" aria-labelledby="resume">' in text


def test_the_dates_are_time_elements_with_their_month_in_letters():
    text = show(PAPER).text

    assert 'Publié le <time datetime="2026-09-25">25 septembre 2026</time>' in text


@pytest.mark.parametrize(
    ("item_id", "changes", "title", "style"),
    [
        (VULNERABILITY, {}, "Exploitée activement: oui", "banner-alert"),
        (
            WITHDRAWN_VULNERABILITY,
            {},
            'Retirée du catalogue le <time datetime="2026-10-06">6 octobre 2026</time>',
            "banner-neutral",
        ),
        (ADVISORY_IN_CATALOG, {}, "Entrée au catalogue KEV", "banner-alert"),
        (
            ADVISORY_ABSENT_FROM_CATALOG,
            {},
            "Absente du catalogue KEV",
            "banner-neutral",
        ),
        (ADVISORY_WITHOUT_CVE, {}, "Sans CVE", "banner-neutral"),
    ],
)
def test_the_banner_says_its_state_in_words_its_colour_following(
    item_id, changes, title, style
):
    """RGAA 3.1: the word carries the state; only an item in the catalog has the style of alert."""
    text = show(item_id, **changes).text

    banner = re.search(
        r'<div class="banner ([a-z-]+)">\s*<p class="banner-title">(.*?)</p>',
        text,
        flags=re.DOTALL,
    )
    assert banner is not None
    assert banner.group(1) == style
    assert banner.group(2).startswith(title)


def test_a_vulnerability_withdrawn_never_says_exploited():
    text = show(WITHDRAWN_VULNERABILITY).text

    assert "Exploitée" not in text


def test_the_banner_of_an_advisory_in_the_catalog_says_its_limit():
    text = show(ADVISORY_IN_CATALOG).text

    assert "Un retrait du catalogue depuis ne se voit pas sur cette page." in text


def test_the_facts_are_a_list_of_terms_the_packages_a_list():
    text = show(ADVISORY_ABSENT_FROM_CATALOG).text

    assert '<dl class="item-facts">' in text
    assert "<dt>Paquets touchés</dt>" in text
    assert '<ul class="packages" role="list">' in text
    assert text.count('<li class="package">') == 3


def test_the_vendor_and_the_product_are_in_english():
    text = show(VULNERABILITY).text

    assert '<dd lang="en">Apple</dd>' in text
    assert '<dd lang="en">Multiple Products</dd>' in text


def test_the_notes_of_a_release_are_plain_text_never_a_link_nor_a_tag():
    body = (
        "## Notes\n\n[a link](https://example.org) <img src=x>\n\nhttps://example.org"
    )
    text = show(RELEASE, body=body).text

    assert '<h2 id="notes">Notes de version, texte brut</h2>' in text
    assert "## Notes" in text
    assert "[a link](https://example.org) &lt;img src=x&gt;" in text
    assert 'href="https://example.org"' not in text


def test_a_release_without_notes_says_so():
    text = show(RELEASE, body=None).text

    assert "Aucune note de version." in text
    assert "Notes de version, texte brut" not in text


@pytest.mark.parametrize(
    ("item_id", "fields"),
    [
        (PAPER, ("title", "summary")),
        (VULNERABILITY, ("title", "description", "vendor", "product")),
        # ghsa_id is GhsaId: a mark out of its form is an invalid answer, the page 500.
        (ADVISORY_IN_CATALOG, ("title",)),
        (RELEASE, ("title", "tag_name", "body")),
        (NEWSLETTER_ARTICLE, ("title", "summary")),
    ],
)
def test_every_value_received_is_escaped_never_a_tag(item_id, fields):
    changes = {field: MARK for field in fields}
    if item_id == PAPER:
        changes["authors"] = [MARK]
    if item_id == ADVISORY_IN_CATALOG:
        changes["packages"] = [MARK]

    text = show(item_id, **changes).text

    assert MARK not in text
    assert ESCAPED_MARK in text


def test_a_control_character_received_never_reaches_the_page():
    text = show(PAPER, title="A" + chr(0x1B) + "B", summary="C" + chr(0x07) + "D").text

    assert chr(0x1B) not in text
    assert chr(0x07) not in text
    assert "AB" in text


def test_a_link_out_of_https_is_never_a_link():
    text = show(PAPER, url="javascript:alert(1)").text

    assert "javascript:" not in text
    assert 'class="button"' not in text


@pytest.mark.parametrize(
    "path",
    [
        "/items/0",
        "/items/01",
        "/items/-1",
        "/items/abc",
        f"/items/{2**63}",
        "/items/1.0",
    ],
)
def test_an_id_out_of_its_form_is_the_page_not_found_without_asking_the_api(path):
    api = RecordingApi(ITEM_DETAILS[PAPER])

    response = get_item(path, handler=api)

    assert response.status_code == 404
    assert "Page introuvable" in response.text
    assert api.requests == []


def test_an_item_the_base_does_not_hold_is_the_page_not_found():
    api = RecordingApi({"error": "item_not_found"}, status_code=404)

    response = get_item("/items/999", handler=api)

    assert response.status_code == 404
    assert "Page introuvable" in response.text


@pytest.mark.parametrize("kind", ["zotero_entry", "clip"])
def test_a_zotero_entry_or_a_clip_is_the_page_not_found_its_text_never_shown(
    kind, caplog
):
    body = {
        "id": 18,
        "kind": kind,
        "title": "A private page kept",
        "source_date": "2026-10-07T00:00:00Z",
        "url": None,
        "withdrawn_at": None,
        "body": "secret-clip-text",
    }

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = get_item("/items/18", body)

    assert response.status_code == 404
    assert "secret-clip-text" not in response.text
    assert "A private page kept" not in response.text
    assert not any(
        "secret-clip-text" in record.getMessage() for record in caplog.records
    )


@pytest.mark.parametrize(
    ("status_code", "body", "state"),
    [
        (503, {"error": "query_timeout"}, "data_api_unavailable"),
        (404, {"error": "route_not_found"}, "data_api_invalid_response"),
        (200, {"kind": "paper"}, "data_api_invalid_response"),
    ],
    ids=["unavailable", "route-not-found", "out-of-schema"],
)
def test_a_failure_of_the_data_api_is_the_page_500_logged_without_the_id(
    caplog, status_code, body, state
):
    with caplog.at_level(logging.INFO, logger="k_b"):
        response = get_item(
            "/items/424242", handler=RecordingApi(body, status_code=status_code)
        )

    request_id = response.headers["X-Request-ID"]
    lines = [record.getMessage() for record in caplog.records]
    assert response.status_code == 500
    assert request_id in response.text
    assert (
        f"data_api_failed: {state} http_status={status_code} request_id={request_id}"
        in lines
    )
    assert not any("424242" in line for line in lines)


def test_the_log_of_a_request_names_the_route_never_the_id(caplog):
    with caplog.at_level(logging.INFO, logger="k_b"):
        get_item("/items/424242", make_detail(PAPER, id=424242))

    lines = [record.getMessage() for record in caplog.records]
    assert any("route=/items/{item_id} status=200" in line for line in lines)
    assert not any("424242" in line for line in lines)


def test_the_title_of_a_card_of_the_feed_is_a_link_to_its_detail():
    client = make_client(handler=serve(ITEMS_PAGE))

    text = client.get("/", headers=OPERATOR_HEADERS).text

    assert (
        '<h2 class="card-title" lang="en"><a href="/items/12">Notes on machine progress'
        in text
    )
    assert text.count('<a href="/items/') == len(ITEMS_PAGE["items"])


def test_the_title_of_a_card_of_the_feed_loses_its_control_characters():
    page = make_page(1)
    page["items"][0]["title"] = "A" + chr(0x1B) + "B"
    client = make_client(handler=serve(page))

    text = client.get("/", headers=OPERATOR_HEADERS).text

    assert chr(0x1B) not in text
    assert ">AB</a></h2>" in text


def write_text_of(length, seed):
    """A text of length characters, letters and spaces drawn by a fixed seed: it compresses as a
    text, not as one letter repeated."""
    draw = random.Random(seed)  # noqa: S311 — a text for a test, no secret
    letters = "abcdefghijklmnopqrstuvwxyz      "
    return "".join(draw.choice(letters) for _ in range(length)).strip() or "a"


@pytest.mark.parametrize(
    ("item_id", "changes"),
    [
        (PAPER, {"title": 500, "summary": 5_000}),
        (VULNERABILITY, {"title": 500, "description": 5_000}),
        (ADVISORY_IN_CATALOG, {"title": 1_024}),
        (RELEASE, {"title": 255}),
        (NEWSLETTER_ARTICLE, {"title": 500, "summary": 5_000}),
    ],
)
def test_the_screen_of_a_detail_holds_three_requests_and_30_kb_at_most(
    item_id, changes
):
    """D4 (Sabine, 2026-11-11; RGESN 6.1): the page, the stylesheet and the icon, cache empty,
    compressed, each text at its bound in the base (items.py, MAX_LENGTH_BY_KIND); the notes of a
    release and the authors of a paper are out of the budget, served whole by the data API."""
    body = make_detail(
        item_id,
        **{field: write_text_of(length, field) for field, length in changes.items()},
    )
    client = make_client(handler=serve(body))
    headers = {**OPERATOR_HEADERS, "Accept-Encoding": "gzip"}
    page = client.get(f"/items/{item_id}", headers=headers)
    resources = re.findall(r"<(?:link|img|script|iframe|source)\b[^>]*>", page.text)
    paths = [re.search(r'(?:href|src)="([^"]+)"', tag).group(1) for tag in resources]

    assert page.status_code == 200
    assert paths == ["/static/site.css", "/static/favicon.svg"]
    weights = [len(gzip.compress(page.content))] + [
        client.get(path, headers=headers).num_bytes_downloaded for path in paths
    ]
    assert sum(weights) <= 30_000


def test_a_detail_whose_summary_is_empty_is_served():
    response = show(PAPER, summary="")

    assert response.status_code == 200
    assert "Aucun résumé." in response.text
    assert '<h2 id="resume">' not in response.text


def test_a_card_whose_title_is_left_empty_by_the_cleaning_is_said_without_title():
    page = make_page(1)
    page["items"][0]["title"] = chr(0x85)
    client = make_client(handler=serve(page))

    text = client.get("/", headers=OPERATOR_HEADERS).text

    assert re.search(
        r'<h2 class="card-title"><a href="/items/[0-9]+">Sans titre</a></h2>', text
    )


def test_a_bidirectional_override_received_never_reaches_the_page():
    override = chr(0x202E)

    text = show(RELEASE, tag_name="v1.0" + override, title="T" + override).text

    assert override not in text
