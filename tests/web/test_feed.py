"""The feed without input nor output: the form read, each refusal with its message, the period, the
pages and the cards (docs/site-web.md, "Fil")."""

import json
from datetime import UTC, datetime

import pytest
from feed_fixture import ITEMS_PAGE
from starlette.datastructures import QueryParams

from k_b.core.config import (
    DATA_API_MAX_OFFSET,
    DATA_API_MAX_SEARCH_LENGTH,
    TLDR_TRACKED_EDITIONS,
)
from k_b.data_api.routers import item_router
from k_b.web.data_api_client import FEED_KINDS, PAGE, DataApiError
from k_b.web.feed import (
    MAX_PAGE,
    NEWSLETTER_NAME_BY_EDITION,
    FieldError,
    build_card,
    build_page_link,
    build_query,
    count_pages,
    find_api_field_error,
    read_feed_form,
    read_page_number,
    write_results_line,
)
from k_b.web.french_dates import write_day

NOW = datetime(2026, 11, 11, 17, 40, tzinfo=UTC)
# validate_json: in strict mode, a date is read from the text of JSON only.
ITEMS = {item.id: item for item in PAGE.validate_json(json.dumps(ITEMS_PAGE)).items}


def read(query):
    return read_feed_form(QueryParams(query))


def test_the_bounds_of_the_site_are_those_of_the_data_api():
    assert DATA_API_MAX_OFFSET == item_router.MAX_OFFSET
    assert DATA_API_MAX_SEARCH_LENGTH == item_router.MAX_SEARCH_LENGTH


def test_the_form_empty_asks_the_five_kinds_since_one_day_without_search():
    form = read("")

    assert form.errors == ()
    assert form.q == ""
    assert form.kinds == FEED_KINDS
    assert form.period == "1"
    query = build_query(form, NOW, page=1)
    assert query.kinds == FEED_KINDS
    assert query.q is None
    assert query.offset == 0


def test_no_kind_checked_asks_the_five_shown_checked():
    assert read("kind=").kinds == FEED_KINDS
    assert read("q=x").kinds == FEED_KINDS


def test_the_kinds_checked_are_asked_in_the_order_of_the_form_once_each():
    form = read("kind=release&kind=paper&kind=release")

    assert form.kinds == ("paper", "release")


@pytest.mark.parametrize("kind", ["clip", "zotero_entry", "PAPER", "paper "])
def test_a_kind_out_of_the_five_is_refused_on_its_fieldset(kind):
    form = read(f"kind=paper&kind={kind}")

    assert [error.field for error in form.errors] == ["kinds"]


def test_the_search_is_kept_without_its_spaces_around():
    form = read("q=%20%20langchain%20")

    assert form.q == "langchain"
    assert build_query(form, NOW, page=1).q == "langchain"


def test_a_search_of_spaces_is_no_search():
    """The form always sends q=, and the data API refuses an empty q."""
    form = read("q=%20%20")

    assert form.errors == ()
    assert build_query(form, NOW, page=1).q is None


def test_a_search_of_200_characters_is_kept_201_refused():
    assert read("q=" + "a" * 200).errors == ()

    [error] = read("q=" + "a" * 201).errors

    assert error.field == "q"
    assert "201" in error.message
    assert "200" in error.message


def test_a_search_holding_a_nul_is_refused_on_its_field():
    [error] = read("q=a%00b").errors

    assert error.field == "q"


@pytest.mark.parametrize(
    ("query", "since"),
    [
        ("", datetime(2026, 11, 10, tzinfo=UTC)),
        ("period=1", datetime(2026, 11, 10, tzinfo=UTC)),
        ("period=3", datetime(2026, 11, 8, tzinfo=UTC)),
        ("period=7", datetime(2026, 11, 4, tzinfo=UTC)),
        ("period=date&start=2026-10-07", datetime(2026, 10, 7, tzinfo=UTC)),
    ],
)
def test_the_period_starts_at_midnight_utc(query, since):
    """1 day takes yesterday and today, in days of UTC."""
    assert build_query(read(query), NOW, page=1).since == since


def test_the_period_follows_the_day_of_utc_at_its_edges():
    just_before = datetime(2026, 11, 11, 23, 59, 59, tzinfo=UTC)
    just_after = datetime(2026, 11, 12, 0, 0, 0, tzinfo=UTC)

    assert build_query(read(""), just_before, page=1).since == datetime(
        2026, 11, 10, tzinfo=UTC
    )
    assert build_query(read(""), just_after, page=1).since == datetime(
        2026, 11, 11, tzinfo=UTC
    )


def test_a_start_date_without_date_checked_is_ignored():
    """D4 (Sabine, 2026-11-11): the radio button decides."""
    form = read("period=3&start=2026-10-07")

    assert form.errors == ()
    assert form.start == "2026-10-07"
    assert build_query(form, NOW, page=1).since == datetime(2026, 11, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    "query",
    [
        "period=date",
        "period=date&start=",
        "period=date&start=07/10/2026",
        "period=date&start=2026-02-30",
        "period=date&start=2026-1-7",
    ],
)
def test_date_checked_without_a_valid_day_is_refused_on_the_start_field(query):
    [error] = read(query).errors

    assert error.field == "start"


@pytest.mark.parametrize("period", ["2", "date ", "30", "jour"])
def test_a_period_out_of_the_four_is_refused_on_its_fieldset(period):
    form = read(f"period={period}")

    assert [error.field for error in form.errors] == ["period"]
    assert form.period == "1"


@pytest.mark.parametrize(
    ("query", "page"),
    [("", 1), ("page=1", 1), ("page=2", 2), ("page=501", 501)],
)
def test_a_page_number_is_read(query, page):
    assert read_page_number(QueryParams(query)) == page


@pytest.mark.parametrize(
    "value", ["0", "01", "+1", "1.0", "abc", "", "502", "1000", "%201", "１"]
)
def test_a_page_number_out_of_its_form_or_beyond_501_is_none(value):
    """One address for each page (Opquast 169); 501 is the offset 10,000 of the data API."""
    assert read_page_number(QueryParams(f"page={value}")) is None


def test_a_page_number_given_twice_is_none():
    assert read_page_number(QueryParams("page=2&page=2")) is None


def test_the_page_gives_its_offset():
    assert build_query(read(""), NOW, page=3).offset == 40
    assert build_query(read(""), NOW, page=MAX_PAGE).offset == DATA_API_MAX_OFFSET


@pytest.mark.parametrize(
    ("total", "pages"),
    [(0, 1), (1, 1), (20, 1), (21, 2), (10_020, 501), (10_021, 501), (99_999, 501)],
)
def test_the_pages_count_twenty_items_each_up_to_501(total, pages):
    assert count_pages(total) == pages


def test_a_422_of_the_search_lands_on_its_field():
    error = DataApiError("data_api_invalid_parameter", 422, ("q",))

    assert find_api_field_error(error) == FieldError(
        "q", find_api_field_error(error).message
    )


@pytest.mark.parametrize(
    "error",
    [
        DataApiError("data_api_invalid_parameter", 422, ("kind",)),
        DataApiError("data_api_invalid_parameter", 422, ("q", "since")),
        DataApiError("data_api_invalid_parameter", 422, ("offset",)),
        DataApiError("data_api_unavailable", 503),
    ],
)
def test_any_other_refusal_of_the_data_api_is_an_error_of_the_site(error):
    """The site builds kind, since, limit and offset itself: refused, the fault is its own."""
    assert find_api_field_error(error) is None


def test_the_link_of_a_page_keeps_the_filters_and_drops_page_one():
    form = read("q=lang%26chain&kind=paper&kind=release&period=date&start=2026-10-07")

    assert build_page_link(form, 2) == (
        "/?q=lang%26chain&kind=paper&kind=release&period=date&start=2026-10-07&page=2"
    )
    assert build_page_link(form, 1) == (
        "/?q=lang%26chain&kind=paper&kind=release&period=date&start=2026-10-07"
    )


def test_the_link_of_a_page_drops_a_start_date_the_radio_ignores():
    assert build_page_link(read("period=3&start=2026-10-07"), 2) == (
        "/?q=&kind=paper&kind=vulnerability&kind=advisory&kind=release"
        "&kind=newsletter_article&period=3&page=2"
    )


@pytest.mark.parametrize(
    ("total", "page", "pages", "line"),
    [
        (
            14,
            1,
            1,
            "14 items depuis le 10 novembre 2026, du plus récent au plus ancien."
            " Page 1 sur 1.",
        ),
        (
            1,
            1,
            1,
            "1 item depuis le 10 novembre 2026, du plus récent au plus ancien."
            " Page 1 sur 1.",
        ),
        (
            41,
            3,
            3,
            "41 items depuis le 10 novembre 2026, du plus récent au plus ancien."
            " Page 3 sur 3.",
        ),
    ],
)
def test_the_line_of_the_results_gives_the_items_the_period_and_the_page(
    total, page, pages, line
):
    """Opquast 2025, rule 13; D4: the period applied."""
    since = datetime(2026, 11, 10, tzinfo=UTC)

    assert write_results_line(total, since, page, pages) == line


def test_the_line_of_no_result_gives_the_period():
    since = datetime(2026, 11, 10, tzinfo=UTC)

    assert write_results_line(0, since, 1, 1) == "Aucun item depuis le 10 novembre 2026."


@pytest.mark.parametrize(
    ("day", "text"),
    [
        (datetime(2026, 10, 1, 18, tzinfo=UTC), "1er octobre 2026"),
        (datetime(2026, 9, 27, 9, 30, tzinfo=UTC), "27 septembre 2026"),
    ],
)
def test_a_day_is_written_with_its_month_in_letters(day, text):
    """Opquast 2025, rule 4: 01/10/2026 reads 1 October or 10 January."""
    assert write_day(day) == text


def test_the_card_of_a_paper():
    card = build_card(ITEMS[2])

    assert card.kind_label == "Papier"
    assert card.kind_lang is None
    assert card.day == "2026-09-27"
    assert card.day_text == "27 septembre 2026"
    assert card.is_exploited is False
    assert card.identifiers == "arXiv 2609.33401"
    assert card.withdrawn_text is None
    assert card.title_lang == "en"
    assert card.link == "https://arxiv.org/abs/2609.33401"
    assert card.link_label == "Lire sur arxiv.org"
    assert card.link_note == "en anglais, site externe"
    assert card.link_lang == "en"


def test_the_card_of_a_vulnerability_is_always_exploited_and_says_its_withdrawal():
    current, withdrawn = build_card(ITEMS[3]), build_card(ITEMS[5])

    assert current.kind_label == "Faille"
    assert current.is_exploited is True
    assert current.identifiers == "CVE-2026-86950"
    assert current.withdrawn_text is None
    assert current.link_label == "Voir la fiche sur nvd.nist.gov"
    assert withdrawn.is_exploited is True
    assert withdrawn.withdrawn_text == "retirée du catalogue le 6 octobre 2026"


@pytest.mark.parametrize(
    ("item_id", "is_exploited", "identifiers"),
    [
        (9, True, "GHSA-fjqc-hq36-qh5p · CVE-2020-29583 · langgraph-checkpoint"),
        (17, False, "GHSA-3644-q5cj-c5c7 · CVE-2026-45134 · langsmith, langchain-classic, langchain"),
        (10, False, "GHSA-gr75-jv2w-4656 · langchain, langchain-anthropic"),
    ],
    ids=["in-kev", "not-in-kev", "without-cve"],
)
def test_the_card_of_an_advisory_is_exploited_only_when_in_the_catalog(
    item_id, is_exploited, identifiers
):
    card = build_card(ITEMS[item_id])

    assert card.kind_label == "Alerte"
    assert card.is_exploited is is_exploited
    assert card.identifiers == identifiers
    assert card.link_label == "Voir sur GitHub"


def test_the_card_of_an_advisory_says_its_packages_are_cut():
    advisory = ITEMS[10].model_copy(
        update={"packages": ["a", "b"], "packages_truncated": True}
    )

    assert build_card(advisory).identifiers == "GHSA-gr75-jv2w-4656 · a, b et d’autres"


def test_the_card_of_a_release_names_its_repository_its_kind_in_english():
    card = build_card(ITEMS[6])

    assert card.kind_label == "Release"
    assert card.kind_lang == "en"
    assert card.identifiers == "anthropics/claude-code"
    assert card.title_lang is None
    assert card.link_label == "Notes de version sur GitHub"
    assert card.day_text == "1er octobre 2026"


def test_the_card_of_a_newsletter_article_does_not_say_the_language_of_its_link():
    card = build_card(ITEMS[12])

    assert card.kind_label == "Newsletter"
    assert card.identifiers == "TLDR AI"
    assert card.title_lang == "en"
    assert card.link_label == "Lire l’article d’origine"
    assert card.link_note == "site externe"
    assert card.link_lang is None


def test_each_edition_tracked_has_the_name_tldr_gives_it():
    """As in the mockups (time-knight, 2026-11-11); the slug of the data API is unchanged."""
    assert set(NEWSLETTER_NAME_BY_EDITION) == set(TLDR_TRACKED_EDITIONS)


def test_an_edition_without_name_shows_its_slug():
    article = ITEMS[12].model_copy(update={"edition": "design"})

    assert build_card(article).identifiers == "TLDR design"


@pytest.mark.parametrize(
    "url",
    [
        "http://arxiv.org/abs/2609.33401",
        "javascript:alert(1)",
        "https:javascript:alert(1)",
        " https://arxiv.org/abs/2609.33401",
        "//arxiv.org/abs/2609.33401",
        None,
    ],
)
def test_a_url_out_of_https_gives_no_link(url):
    assert build_card(ITEMS[2].model_copy(update={"url": url})).link is None
