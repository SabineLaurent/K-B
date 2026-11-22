"""The page of the trends without input nor output: the day read from the address, the start of a
window, the rows of its table and the state of each page."""

import json
from datetime import date

import pytest
from starlette.datastructures import QueryParams
from trends_fixture import TRENDS, make_trends

from k_b.web.data_api_client import TREND_WINDOW, DataApiError
from k_b.web.feed import FieldError
from k_b.web.trends import (
    TRENDS_PATH,
    WINDOW_END_ID,
    WINDOW_END_REFUSED_BY_API,
    TrendsForm,
    build_missing_window_page,
    build_refused_page,
    build_trends_page,
    find_api_window_end_error,
    find_window_start,
    read_trends_form,
    write_count,
)

NARROW_NO_BREAK_SPACE = chr(0x202F)
NOT_A_DAY = "Date invalide: choisissez un jour dans le champ."
REFUSED = FieldError(WINDOW_END_ID, NOT_A_DAY)


def read(query):
    return read_trends_form(QueryParams(query))


def read_window(body):
    return TREND_WINDOW.validate_json(json.dumps(body))


@pytest.mark.parametrize("query", ["", "window_end=", "page=2"])
def test_without_a_day_the_form_asks_the_latest_window(query):
    assert read(query) == TrendsForm(window_end=None, error=None)


def test_a_day_is_read_as_the_last_day_of_its_window():
    assert read("window_end=2026-10-10") == TrendsForm(date(2026, 10, 10), None)


@pytest.mark.parametrize(
    "value",
    [
        "20261010",
        "2026-1-7",
        "10/10/2026",
        "2026-10-10T00:00",
        "x" * 3000,
        "2026-10-10%01",
        # A digit of full width, which Python reads as a digit.
        "%EF%BC%92026-10-10",
        # 7 digits, which no field sends: HTML stops at the year 275760.
        "2026666-01-01",
    ],
    ids=[
        "without-dashes",
        "short",
        "french-form",
        "with-time",
        "long",
        "control",
        "full-width-digit",
        "seven-digit-year",
    ],
)
def test_a_value_that_is_not_a_day_is_refused_on_its_field(value):
    """The rule of the route of the data API, WrittenDay: YYYY-MM-DD, a day that exists. The
    message gives no format, which the field shows as its browser does (Opquast 2025, rule 80;
    #617)."""
    assert read(f"window_end={value}") == TrendsForm(None, REFUSED)


@pytest.mark.parametrize("value", ["2026-02-30", "2026-13-01", "0000-01-01"])
def test_a_value_of_the_form_of_a_day_that_does_not_exist_is_named_in_its_message(
    value,
):
    """Opquast 2025, rule 81: an input type=date holds a valid day or nothing, so its field cannot
    show the value refused again; its message names it. Digits and dashes only: no other text
    received reaches the page."""
    assert read(f"window_end={value}") == TrendsForm(
        None,
        FieldError(
            WINDOW_END_ID,
            f"Date invalide: {value} n’existe pas. Choisissez un jour qui existe.",
        ),
    )


@pytest.mark.parametrize("value", ["20266-01-01", "202666-12-31", "20266-02-30"])
def test_a_year_of_5_or_6_digits_is_said_in_its_message(value):
    """The one refusal a browser sends: Chrome lets type a year of 5 or 6 digits in an input
    type=date. The message says the nature of the error (Opquast 2025, rule 80), without the
    value."""
    assert read(f"window_end={value}") == TrendsForm(
        None,
        FieldError(WINDOW_END_ID, "Date invalide: l’année a plus de 4 chiffres."),
    )


def test_a_window_end_repeated_keeps_its_last_value():
    """As q on the feed: the last value of the address."""
    assert read("window_end=2026-02-30&window_end=2026-10-10") == TrendsForm(
        date(2026, 10, 10), None
    )


@pytest.mark.parametrize(
    ("end", "start"),
    [
        (date(2026, 10, 10), date(2026, 10, 8)),
        (date(2026, 11, 1), date(2026, 10, 30)),
        (date(2027, 1, 1), date(2026, 12, 30)),
        (date(2028, 3, 1), date(2028, 2, 28)),
        (date(2026, 3, 1), date(2026, 2, 27)),
    ],
    ids=["within-a-month", "over-a-month", "over-a-year", "leap-year", "common-year"],
)
def test_a_window_of_three_days_starts_two_days_before_its_last_day(end, start):
    assert find_window_start(end) == start


@pytest.mark.parametrize(
    ("count", "text"),
    [(0, "0"), (999, "999"), (1500, "1 500"), (1_234_567, "1 234 567")],
)
def test_a_count_is_grouped_by_thousands_with_a_narrow_no_break_space(count, text):
    assert write_count(count) == text.replace(" ", NARROW_NO_BREAK_SPACE)


def test_the_rows_give_the_rank_of_the_order_of_the_data_api_and_a_link_to_github():
    rows = build_trends_page(read_window(TRENDS)).table.rows

    assert [row.rank for row in rows] == [1, 2, 3, 4, 5]
    assert rows[0].repository_name == "morluto/rea"
    assert rows[0].link == "https://github.com/morluto/rea"
    assert (rows[0].stars, rows[0].forks) == (f"1{NARROW_NO_BREAK_SPACE}087", "215")
    assert (rows[3].stars, rows[3].forks) == ("0", "70")


def test_the_table_gives_the_first_and_the_last_day_of_its_window():
    table = build_trends_page(read_window(TRENDS)).table

    assert (table.start_day, table.start_text) == ("2026-10-08", "8 octobre 2026")
    assert (table.end_day, table.end_text) == ("2026-10-10", "10 octobre 2026")


def test_the_field_shows_the_last_day_of_the_window_shown():
    page = build_trends_page(read_window(make_trends(window_end="2026-10-09")))

    assert (page.value, page.error) == ("2026-10-09", None)


def test_a_day_refused_is_never_shown_again():
    """A value of an input type=date is a valid day or nothing (WHATWG; RGAA 8.2)."""
    page = build_refused_page(REFUSED)

    assert (page.value, page.table) == ("", None)
    assert page.error == REFUSED


def test_a_window_absent_says_its_day_and_leads_to_the_latest():
    """C8: the day is valid, the result is missing; the form stays."""
    page = build_missing_window_page(date(2026, 10, 11))

    assert page.empty_text == (
        "Aucune tendance pour la fenêtre qui se termine le 11 octobre 2026."
    )
    assert (page.value, page.latest_link, page.table) == (
        "2026-10-11",
        TRENDS_PATH,
        None,
    )


def test_a_base_without_trends_says_so_without_a_link_to_itself():
    page = build_missing_window_page(None)

    assert page.empty_text == "Aucune tendance en base."
    assert (page.value, page.latest_link, page.table) == ("", None, None)


def test_each_state_has_a_title_of_its_own():
    """RGAA 8.6; WCAG 2.4.2."""
    assert [
        build_trends_page(read_window(TRENDS)).title,
        build_refused_page(REFUSED).title,
        build_missing_window_page(date(2026, 10, 11)).title,
        build_missing_window_page(None).title,
    ] == [
        "Tendances du 8 octobre 2026 au 10 octobre 2026",
        "Tendances, date à corriger",
        "Tendances, aucune tendance le 11 octobre 2026",
        "Tendances, aucune tendance en base",
    ]


def test_a_window_end_refused_by_the_data_api_is_said_on_its_field():
    error = DataApiError("data_api_invalid_parameter", 422, ("window_end",))

    assert find_api_window_end_error(error) == FieldError(
        WINDOW_END_ID, WINDOW_END_REFUSED_BY_API
    )


@pytest.mark.parametrize(
    "error",
    [
        DataApiError("data_api_invalid_parameter", 422, ("limit",)),
        DataApiError("data_api_invalid_parameter", 422, ("window_end", "limit")),
        DataApiError("data_api_unavailable", 503),
    ],
    ids=["another-parameter", "two-parameters", "unavailable"],
)
def test_any_other_failure_is_an_error_of_the_site(error):
    """The site sends window_end alone: another refusal is no field to correct."""
    assert find_api_window_end_error(error) is None


@pytest.mark.parametrize("name", ["owner/..", "./repo", "owner/foo..bar"])
def test_a_name_is_repository_name_refuses_keeps_its_row_and_its_rank_without_a_link(
    name,
):
    """A browser resolves https://github.com/owner/.. to another page of GitHub: no link, as a URL
    out of https on the feed; the row and the rank of the others stay."""
    trends = make_trends()
    trends["trends"][1]["repository_name"] = name

    rows = build_trends_page(read_window(trends)).table.rows

    assert (rows[1].rank, rows[1].repository_name, rows[1].link) == (2, name, None)
    assert rows[2].rank == 3
