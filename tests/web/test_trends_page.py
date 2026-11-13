"""The page of the trends, /tendances, served by the site on its simulated data API: the latest window
or the one asked, a day refused on its field, a window absent, the errors and the budget of the
screen."""

import logging
import re

import httpx2
from screen_weight import SCREEN_BUDGET_BYTES, SCREEN_RESOURCES, weigh_screen
from site_client import OPERATOR_HEADERS, make_client, serve
from trends_fixture import TRENDS, make_trends

TRENDS_PATH = "/tendances"
NOT_FOUND = {"error": "trend_window_not_found"}
FIELD = re.compile(r'<input id="window-end"[^>]*>')


def record(body, status_code=200):
    """A data API that answers body, and keeps each request it receives."""
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(status_code, json=body)

    return handler, requests


def get(path, handler):
    return make_client(handler=handler).get(path, headers=OPERATOR_HEADERS)


def read_field(response):
    field = FIELD.search(response.text)
    assert field is not None
    return field.group(0)


def test_the_latest_window_is_a_table_of_its_rows():
    handler, requests = record(TRENDS)

    response = get(TRENDS_PATH, handler)

    assert response.status_code == 200
    assert (
        "<title>Tendances du 8 octobre 2026 au 10 octobre 2026 · K-B</title>"
        in response.text
    )
    assert "<h1>Dépôts qui ont le vent en poupe</h1>" in response.text
    assert response.text.count('<td class="rank">') == 5
    [request] = requests
    assert request.url.path == "/trends"
    assert "window_end" not in request.url.params
    assert 'value="2026-10-10"' in read_field(response)


def test_the_window_asked_sends_its_day():
    handler, requests = record(make_trends(window_end="2026-10-09"))

    response = get(f"{TRENDS_PATH}?window_end=2026-10-09", handler)

    assert response.status_code == 200
    assert requests[0].url.params["window_end"] == "2026-10-09"
    assert 'value="2026-10-09"' in read_field(response)


def test_sixty_rows_are_shown_in_the_order_of_the_data_api():
    response = get(TRENDS_PATH, serve(make_trends(count=60)))

    ranks = re.findall(r'<td class="rank">([0-9]+)</td>', response.text)
    assert ranks == [str(rank) for rank in range(1, 61)]


def test_each_repository_links_to_github_in_a_new_tab_it_announces():
    """C13: in English, to another site, in a new tab (the macro external_link, #587)."""
    response = get(TRENDS_PATH, serve(TRENDS))

    assert (
        '<a href="https://github.com/morluto/rea" hreflang="en" target="_blank"'
        ' rel="noopener noreferrer">morluto/rea<span aria-hidden="true">&nbsp;↗</span>'
        ' <span class="link-note">(en anglais, site externe, nouvel onglet)</span></a>'
        in response.text
    )


def test_the_counts_are_numbers_grouped_by_thousands():
    response = get(TRENDS_PATH, serve(TRENDS))

    assert f'<td class="number">1{chr(0x202F)}087</td>' in response.text
    assert '<td class="number">215</td>' in response.text


def test_a_day_refused_gives_the_page_in_422_without_asking_the_data_api():
    handler, requests = record(TRENDS)

    response = get(f"{TRENDS_PATH}?window_end=2026-02-30", handler)

    assert response.status_code == 422
    assert requests == []
    assert "<title>Tendances, date à corriger · K-B</title>" in response.text
    assert (
        '<p id="window-end-error" class="field-error">Date invalide: un jour attendu,'
        " sous la forme AAAA-MM-JJ.</p>" in response.text
    )
    field = read_field(response)
    assert 'aria-invalid="true"' in field
    assert 'aria-describedby="window-end-error window-end-help"' in field
    assert 'value=""' in field
    assert "<table" not in response.text


def test_a_window_end_refused_by_the_data_api_is_said_under_its_field():
    body = {"error": "invalid_parameter", "parameters": ["window_end"]}

    response = get(f"{TRENDS_PATH}?window_end=2026-10-10", serve(body, 422))

    assert response.status_code == 422
    assert (
        '<p id="window-end-error" class="field-error">La base de K-B refuse cette date:'
        " choisissez-en une autre.</p>" in response.text
    )
    assert 'value=""' in read_field(response)


def test_another_parameter_refused_by_the_data_api_gives_the_page_500():
    body = {"error": "invalid_parameter", "parameters": ["limit"]}

    response = get(TRENDS_PATH, serve(body, 422))

    assert response.status_code == 500


def test_a_window_absent_is_said_in_200_with_a_link_to_the_latest():
    response = get(f"{TRENDS_PATH}?window_end=2026-10-11", serve(NOT_FOUND, 404))

    assert response.status_code == 200
    assert (
        "Aucune tendance pour la fenêtre qui se termine le 11 octobre 2026."
        in response.text
    )
    assert (
        '<a class="button-secondary" href="/tendances">Voir la fenêtre la plus récente</a>'
        in response.text
    )
    assert 'value="2026-10-11"' in read_field(response)
    assert "<table" not in response.text


def test_a_base_without_trends_is_said_in_200():
    response = get(TRENDS_PATH, serve(NOT_FOUND, 404))

    assert response.status_code == 200
    assert "Aucune tendance en base." in response.text
    assert "Voir la fenêtre la plus récente" not in response.text
    assert 'value=""' in read_field(response)


def test_a_failure_of_the_data_api_gives_the_page_500_logged_without_the_day(caplog):
    with caplog.at_level(logging.INFO, logger="k_b"):
        response = get(
            f"{TRENDS_PATH}?window_end=2026-10-09",
            serve({"error": "query_timeout"}, 503),
        )

    assert response.status_code == 500
    [line] = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("data_api_failed")
    ]
    assert line.startswith(
        "data_api_failed: data_api_unavailable http_status=503 request_id="
    )
    assert "2026-10-09" not in caplog.text


def test_an_answer_out_of_the_contract_gives_the_page_500():
    response = get(TRENDS_PATH, serve(make_trends(trends=[])))

    assert response.status_code == 500


def test_the_log_of_a_request_names_its_route_never_the_day_asked(caplog):
    with caplog.at_level(logging.INFO, logger="k_b"):
        get(
            f"{TRENDS_PATH}?window_end=2026-10-09",
            serve(make_trends(window_end="2026-10-09")),
        )

    assert "route=/tendances" in caplog.text
    assert "2026-10-09" not in caplog.text


def test_the_screen_of_the_trends_holds_three_requests_and_30_kb_at_most():
    """D4 (Sabine, 2026-11-11; RGESN 6.1): 60 rows, each name at the lengths GitHub allows, 39
    characters for the owner and 100 for the repository."""
    rows = [
        {
            **TRENDS["trends"][0],
            "repository_name": f"{'o' * 36}{index:03d}/{'r' * 97}{index:03d}",
            "stars_gained": 1_000_000 + index,
            "forks_gained": 100_000 + index,
        }
        for index in range(60)
    ]
    client = make_client(handler=serve(make_trends(trends=rows)))

    screen = weigh_screen(client, TRENDS_PATH)

    assert screen.status_code == 200
    assert screen.resources == SCREEN_RESOURCES
    assert screen.weight <= SCREEN_BUDGET_BYTES
