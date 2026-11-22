"""The feed on the home page, its data API simulated: the cards, the filters kept, the pages, the
errors, the empty feed, and a value received always escaped (docs/site-web.md, "Fil")."""

import logging
import re

import httpx2
import pytest
from feed_fixture import ITEMS_PAGE, make_page
from screen_weight import SCREEN_BUDGET_BYTES, SCREEN_RESOURCES, weigh_screen
from site_client import OPERATOR_HEADERS, make_client, serve

from k_b.web.feed import FEED_PATH

ALL_KINDS = (
    "kind=paper&kind=vulnerability&kind=advisory&kind=release&kind=newsletter_article"
)


class RecordingApi:
    """A data API that answers each request with the body given, and keeps the requests."""

    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx2.Response(self.status_code, json=self.body)


def get_feed(query="", handler=None):
    client = make_client(handler=handler)
    return client.get(f"{FEED_PATH}?{query}", headers=OPERATOR_HEADERS)


def find_input(text, input_id):
    match = re.search(rf'<input id="{input_id}"[^>]*>', text)
    assert match is not None, input_id
    return match.group(0)


def test_the_feed_shows_twenty_cards_the_results_and_the_page():
    api = RecordingApi(make_page(20, total=45))

    response = get_feed(handler=api)

    assert response.status_code == 200
    assert response.text.count('<li class="card">') == 20
    assert (
        "45 items depuis le 10 novembre 2026, du plus récent au plus ancien."
        " Page 1 sur 3, 20 items par page." in response.text
    )
    assert "<title>Quoi de neuf, page 1 sur 3 · K-B</title>" in response.text


def test_the_feed_asks_the_data_api_the_five_kinds_since_yesterday_without_search():
    api = RecordingApi(ITEMS_PAGE)

    get_feed(handler=api)

    [request] = api.requests
    assert request.url.params.get_list("kind") == [
        "paper",
        "vulnerability",
        "advisory",
        "release",
        "newsletter_article",
    ]
    assert request.url.params["since"] == "2026-11-10T00:00:00Z"
    assert request.url.params["offset"] == "0"
    assert "q" not in request.url.params


def test_the_filters_are_sent_and_shown_again():
    api = RecordingApi(ITEMS_PAGE)

    response = get_feed("q=langchain&kind=paper&kind=release&period=3", handler=api)

    [request] = api.requests
    assert request.url.params["q"] == "langchain"
    assert request.url.params.get_list("kind") == ["paper", "release"]
    assert request.url.params["since"] == "2026-11-08T00:00:00Z"
    assert 'value="langchain"' in find_input(response.text, "q")
    assert "checked" in find_input(response.text, "kind-paper")
    assert "checked" not in find_input(response.text, "kind-advisory")
    assert "checked" in find_input(response.text, "period-3")
    assert "checked" not in find_input(response.text, "period-1")


def test_the_links_of_the_pages_keep_the_filters():
    response = get_feed(
        "q=lang&kind=paper&page=2", handler=serve(make_page(20, total=45))
    )

    assert "Page 2 sur 3" in response.text
    assert (
        'href="/?q=lang&amp;kind=paper&amp;period=1#resultats" rel="prev"'
        in response.text
    )
    assert (
        'href="/?q=lang&amp;kind=paper&amp;period=1&amp;page=3#resultats" rel="next"'
        in response.text
    )


def test_a_link_of_a_page_is_a_button_that_lands_on_the_line_of_the_results():
    """Sabine, 2026-11-11: another page starts at its results, not at the top; the button of the
    mockups, a target of 44 px. The form, sent again, starts at the top of the page."""
    response = get_feed("page=2", handler=serve(make_page(20, total=45)))

    # tabindex -1: following the anchor, the browser focuses the line ("Scrolling to a fragment",
    # WHATWG), so the keyboard and a screen reader start from the results too.
    assert '<p id="resultats" class="results-line" tabindex="-1">' in response.text
    links = re.findall(r'<a ([^>]*)rel="(?:prev|next)"', response.text)
    assert len(links) == 2
    assert all(
        'class="button-secondary"' in link and '#resultats"' in link for link in links
    )
    assert '<form class="feed-filters" method="get" action="/"' in response.text


def test_the_first_line_of_a_card_gives_its_kind_its_date_its_identifiers_then_its_mark():
    """Maquettes-fil.dc.html (2026-11-09): one line, which wraps on a phone."""
    response = get_feed(handler=serve(ITEMS_PAGE))

    lines = re.findall(r'<p class="card-meta">(.*?)</p>', response.text)
    assert len(lines) == len(ITEMS_PAGE["items"])
    assert all(
        line.index('class="card-kind"')
        < line.index("<time")
        < line.index('class="card-identifiers"')
        for line in lines
    )
    exploited = [line for line in lines if 'class="badge"' in line]
    assert exploited
    assert all(
        line.index('class="card-identifiers"') < line.index('class="badge"')
        for line in exploited
    )
    assert response.text.count('class="card-identifiers"') == len(lines)


def test_the_link_of_a_card_is_short_its_announcement_in_it_smaller():
    """Maquettes-fil.dc.html: « Lire sur arxiv.org ↗ »; the announcement of the new tab kept in
    the link (Opquast 2025, rule 146), in a span of its own."""
    response = get_feed(handler=serve(ITEMS_PAGE))

    assert (
        '<a class="card-link" href="https://arxiv.org/abs/2609.33401" hreflang="en"'
        ' target="_blank" rel="noopener noreferrer"><span>Lire sur arxiv.org<span'
        ' class="external-arrow" aria-hidden="true">&nbsp;↗</span></span> <span'
        ' class="link-note">(en anglais, site externe, nouvel onglet)</span></a>'
    ) in response.text


def test_a_single_page_has_no_link_to_another():
    response = get_feed(handler=serve(ITEMS_PAGE))

    assert 'rel="prev"' not in response.text
    assert 'rel="next"' not in response.text


def test_a_page_beyond_the_last_is_the_page_not_found():
    api = RecordingApi(make_page(5, total=45))

    response = get_feed("page=4", handler=api)

    assert response.status_code == 404
    assert "Page introuvable" in response.text
    assert len(api.requests) == 1


@pytest.mark.parametrize("page", ["502", "abc", "01", "0"])
def test_a_page_out_of_its_form_is_the_page_not_found_without_asking_the_api(page):
    api = RecordingApi(ITEMS_PAGE)

    response = get_feed(f"page={page}", handler=api)

    assert response.status_code == 404
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert api.requests == []


def test_a_kind_out_of_the_five_is_refused_in_html_without_asking_the_api():
    """Never a Zotero entry nor a clip, even asked by the address."""
    api = RecordingApi(ITEMS_PAGE)

    response = get_feed("kind=clip", handler=api)

    assert response.status_code == 422
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert api.requests == []
    assert (
        '<fieldset id="kinds" aria-describedby="kinds-error kinds-help">'
        in response.text
    )
    assert (
        '<p id="kinds-error" class="field-error">Erreur. Sorte inconnue'
        in response.text
    )
    assert '<li class="card">' not in response.text


def test_a_search_too_long_is_refused_on_its_field_its_value_kept():
    api = RecordingApi(ITEMS_PAGE)
    search = "a" * 201

    response = get_feed(f"q={search}", handler=api)

    assert response.status_code == 422
    assert api.requests == []
    field = find_input(response.text, "q")
    assert f'value="{search}"' in field
    assert 'aria-invalid="true"' in field
    assert 'aria-describedby="q-error q-help"' in field
    # A value longer than maxlength is no valid HTML (WHATWG, RGAA 8.2).
    assert "maxlength" not in field
    assert (
        '<p id="q-error" class="field-error">Erreur. La recherche fait 201 caractères'
        in response.text
    )
    assert '<a href="#q">La recherche fait 201 caractères' in response.text
    assert "<title>Quoi de neuf, filtre à corriger · K-B</title>" in response.text


def test_the_search_field_keeps_its_maxlength_when_its_value_holds_in_it():
    assert 'maxlength="200"' in find_input(get_feed().text, "q")
    assert 'maxlength="200"' in find_input(get_feed("q=" + "a" * 200).text, "q")


def test_a_search_of_200_characters_beyond_200_units_of_the_browser_drops_maxlength():
    """maxlength counts the units of UTF-16, the site the characters: 150 emoji make 300 units."""
    response = get_feed("q=" + chr(0x1F600) * 150)

    assert response.status_code == 200
    assert "maxlength" not in find_input(response.text, "q")


def test_a_start_of_a_year_of_5_digits_is_refused_without_a_format_the_field_does_not_show():
    """Chrome lets type 20266 in an input type=date, which shows the day in its own way: the
    message says the nature of the error, without a format (Opquast 2025, rule 80; #617)."""
    api = RecordingApi(ITEMS_PAGE)

    response = get_feed("period=date&start=20266-01-01", handler=api)

    assert response.status_code == 422
    assert api.requests == []
    assert (
        '<p id="start-error" class="field-error">Erreur. Date de début invalide:'
        " l’année a plus de 4 chiffres.</p>" in response.text
    )
    assert "AAAA-MM-JJ" not in response.text
    assert "20266" not in response.text


def test_neither_a_control_character_nor_a_long_start_comes_back_in_the_page():
    api = RecordingApi(ITEMS_PAGE)

    refused = get_feed("q=a%01b", handler=api)
    ignored = get_feed("period=1&start=" + "x" * 3000 + "%01", handler=api)

    assert refused.status_code == 422
    assert ignored.status_code == 200
    assert chr(1) not in refused.text + ignored.text
    assert "x" * 3000 not in ignored.text
    assert len(api.requests) == 1


def test_date_checked_without_date_is_refused_on_the_start_field():
    response = get_feed("period=date&start=", handler=serve(ITEMS_PAGE))

    assert response.status_code == 422
    assert 'aria-invalid="true"' in find_input(response.text, "start")
    assert "checked" in find_input(response.text, "period-date")


def test_a_search_the_data_api_refuses_lands_on_its_field():
    api = RecordingApi({"error": "invalid_parameter", "parameters": ["q"]}, 422)

    response = get_feed("q=langchain", handler=api)

    assert response.status_code == 422
    assert 'aria-invalid="true"' in find_input(response.text, "q")
    assert "La base de K-B refuse cette recherche" in response.text


@pytest.mark.parametrize(
    ("handler", "state", "http_status"),
    [
        (serve({"error": "query_timeout"}, 503), "data_api_unavailable", "503"),
        (serve({"error": "invalid_api_key"}, 401), "data_api_unauthorized", "401"),
        (serve({"error": "rate_limit_exceeded"}, 429), "data_api_rate_limited", "429"),
        (
            serve({"error": "invalid_parameter", "parameters": ["kind"]}, 422),
            "data_api_invalid_parameter",
            "422",
        ),
        (serve({"items": "none"}), "data_api_invalid_response", "200"),
    ],
    ids=[
        "unavailable",
        "unauthorized",
        "rate-limited",
        "kind-refused",
        "out-of-schema",
    ],
)
def test_a_failure_of_the_data_api_is_the_page_500_logged_without_the_search(
    caplog, handler, state, http_status
):
    with caplog.at_level(logging.INFO, logger="k_b"):
        response = get_feed("q=secret-search", handler=handler)

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 500
    assert "Erreur du serveur" in response.text
    assert request_id in response.text
    lines = [record.getMessage() for record in caplog.records]
    assert (
        f"data_api_failed: {state} http_status={http_status} request_id={request_id}"
        in lines
    )
    assert not any("secret-search" in line for line in lines)


def test_a_timeout_of_the_data_api_is_logged_without_status(caplog):
    def handler(request):
        raise httpx2.ReadTimeout("read")

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = get_feed(handler=handler)

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 500
    assert (
        f"data_api_failed: data_api_timeout http_status=- request_id={request_id}"
        in [record.getMessage() for record in caplog.records]
    )


def test_the_empty_feed_says_so_and_proposes_seven_days():
    response = get_feed("q=nothing", handler=serve(make_page(0)))

    assert response.status_code == 200
    assert "Aucun item depuis le 10 novembre 2026." in response.text
    assert (
        f'href="/?q=nothing&amp;{ALL_KINDS.replace("&", "&amp;")}&amp;period=7"'
        in response.text
    )
    assert "Élargir à 7 jours" in response.text
    assert "<title>Quoi de neuf, aucun item · K-B</title>" in response.text


def test_the_feed_groups_the_thousands_of_its_total():
    response = get_feed(handler=serve(make_page(20, total=12_345)))

    assert f"12{chr(0x202F)}345 items depuis le" in response.text


def test_the_feed_beyond_the_last_page_served_says_to_refine():
    response = get_feed(handler=serve(make_page(20, total=10_021)))

    assert "Page 1 sur 501" in response.text
    assert "affinez" in response.text


def test_a_title_received_is_escaped_never_a_tag():
    page = make_page(1)
    page["items"][0]["title"] = '<script>alert("x")</script>'

    response = get_feed(handler=serve(page))

    assert "<script" not in response.text
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;" in response.text


def test_a_card_whose_url_is_not_https_has_no_link():
    page = make_page(1)
    page["items"][0]["url"] = "javascript:alert(1)"

    response = get_feed(handler=serve(page))

    assert "javascript:" not in response.text
    assert 'class="card-link"' not in response.text


def test_the_screen_of_the_feed_holds_three_requests_and_30_kb_at_most():
    """D2 (Sabine, 2026-11-11; RGESN 6.1): the page, the stylesheet and the icon, cache empty,
    compressed, on 20 items of the fixture."""
    client = make_client(handler=serve(make_page(20, total=45)))

    screen = weigh_screen(client, FEED_PATH)

    assert screen.resources == SCREEN_RESOURCES
    assert screen.weight <= SCREEN_BUDGET_BYTES
