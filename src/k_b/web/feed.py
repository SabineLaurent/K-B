"""The feed of the home page, without input nor output: the form read and its refusals, the query
of GET /items, the pages and the cards (docs/site-web.md, "Fil")."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal, assert_never, get_args
from urllib.parse import urlencode, urlsplit

from pydantic import TypeAdapter, ValidationError
from starlette.datastructures import QueryParams

from k_b.core.config import (
    DATA_API_MAX_OFFSET,
    DATA_API_MAX_SEARCH_LENGTH,
    FEED_PAGE_SIZE,
)
from k_b.items import NonEmptyText
from k_b.web.data_api_client import (
    FEED_KINDS,
    DataApiError,
    FeedAdvisory,
    FeedItem,
    FeedKind,
    FeedNewsletterArticle,
    FeedPaper,
    FeedQuery,
    FeedRelease,
    FeedVulnerability,
)
from k_b.web.french_dates import write_day
from k_b.web.received_text import clean_received_text, clean_received_value

FEED_PATH = "/"
# The detail of an item, the target of the title of its card.
ITEM_PATH = "/items/{item_id}"
# The names of the fields in the address of the feed.
SEARCH_FIELD = "q"
KIND_FIELD = "kind"
PERIOD_FIELD = "period"
START_FIELD = "start"
PAGE_FIELD = "page"
# A link to another site opens in a new tab, which its text says (Opquast 2025, rule 146; Sabine,
# 2026-11-11).
NEW_TAB_NOTE = "site externe, nouvel onglet"
# A title the cleaning leaves without a letter: NonEmptyText lets through one of control
# characters alone, which would make a link without a name (RGAA 6.2).
NO_TITLE = "Sans titre"
# The line of the results, where a link to another page lands (Sabine, 2026-11-11): the form, sent
# again, starts at the top of the page.
RESULTS_ID = "resultats"
# The id, in the page, of each field or group an error points to.
SEARCH_ID = "q"
KINDS_ID = "kinds"
PERIOD_ID = "period"
START_ID = "start"

type Period = Literal["1", "3", "7", "date"]
PERIODS: tuple[Period, ...] = get_args(Period.__value__)
# D3 (Sabine, 2026-11-11): 1 day, as in the mockups.
DEFAULT_PERIOD: Period = "1"
# What the feed without item proposes.
WIDER_PERIOD: Period = "7"
DATE_PERIOD = "date"
DAYS_BY_PERIOD = {"1": 1, "3": 3, "7": 7}
PERIOD_LABELS: dict[Period, str] = {
    "1": "1 jour",
    "3": "3 jours",
    "7": "7 jours",
    "date": "Date",
}
# The title of the page in each state (RGAA 8.6).
ERRORS_TITLE = "Quoi de neuf, filtre à corriger"
NO_ITEM_TITLE = "Quoi de neuf, aucun item"

# Neither 01 nor +1 (Opquast 2025, rule 169: one address for each page); page 1 is served at
# page=1 too, which no link writes.
PAGE_NUMBER = re.compile(r"[1-9][0-9]{0,2}")
# The page at the offset 10,000, the last the data API serves.
MAX_PAGE = DATA_API_MAX_OFFSET // FEED_PAGE_SIZE + 1
# The form input type=date sends; another form is refused, never guessed.
START_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# The rule of the data API for q: neither a NUL nor a lone surrogate.
SEARCH_TEXT: TypeAdapter[str] = TypeAdapter(NonEmptyText)

SEARCH_REFUSED_BY_API = "La base de K-B refuse cette recherche: modifiez-la."
KIND_REFUSED = "Sorte inconnue: cochez une ou plusieurs des cinq sortes."
PERIOD_REFUSED = "Période inconnue: choisissez 1, 3 ou 7 jours, ou une date."
START_MISSING = "Indiquez la date de début, ou choisissez 1, 3 ou 7 jours."
START_REFUSED = "Date de début invalide: un jour attendu, sous la forme AAAA-MM-JJ."
SEARCH_CONTROL_REFUSED = "La recherche contient un caractère de contrôle refusé."


@dataclass(frozen=True)
class FieldError:
    """A refusal shown under its field, by the id of the field or of its group."""

    field: str
    message: str


@dataclass(frozen=True)
class FeedForm:
    """The form as received, each value kept to be shown again."""

    q: str
    kinds: tuple[FeedKind, ...]
    period: Period
    start: str
    errors: tuple[FieldError, ...]


@dataclass(frozen=True)
class KindLabels:
    """What a card and the form write of a kind; lang en for a word absent from the dictionaries
    of French, or a text the source writes in English (RGAA 8.7)."""

    card_label: str
    form_label: str
    label_lang: str | None
    title_lang: str | None
    link_label: str
    link_lang: str | None


# The labels of the mockups of 2026-11-09, but the link of a vulnerability: NVD, an abbreviation,
# would need its meaning (Opquast 2025, rule 5).
LABELS_BY_KIND: dict[FeedKind, KindLabels] = {
    "paper": KindLabels("Papier", "Papiers", None, "en", "Lire sur arxiv.org", "en"),
    "vulnerability": KindLabels(
        "Faille", "Failles", None, "en", "Voir la fiche sur nvd.nist.gov", "en"
    ),
    "advisory": KindLabels("Alerte", "Alertes", None, "en", "Voir sur GitHub", "en"),
    "release": KindLabels(
        "Release", "Releases", "en", None, "Notes de version sur GitHub", "en"
    ),
    # The language of the article is not known.
    "newsletter_article": KindLabels(
        "Newsletter",
        "Articles de newsletters",
        None,
        "en",
        "Lire l’article d’origine",
        None,
    ),
}


# The name of each edition tracked, as TLDR writes it in the h1 of its page
# (tests/fixtures/tldr_*_extract.html; docs/specs-collecte.md for tech; tldr.tech/infosec, read on
# 2026-11-11): the mockups write TLDR AI (time-knight, 2026-11-11). An edition without a name here
# shows TLDR and its slug.
NEWSLETTER_NAME_BY_EDITION = {
    "ai": "TLDR AI",
    "infosec": "TLDR InfoSec",
    "dev": "TLDR Dev",
    "tech": "TLDR",
}


@dataclass(frozen=True)
class FeedCard:
    """An item as its card shows it; day is the ISO day of its time element."""

    kind_label: str
    kind_lang: str | None
    day: str
    day_text: str
    is_exploited: bool
    identifiers: str
    withdrawn_text: str | None
    title: str
    title_lang: str | None
    detail_link: str
    # None: a URL out of https, never made a link.
    link: str | None
    link_label: str
    link_note: str
    link_lang: str | None


@dataclass(frozen=True)
class FeedListing:
    """A page of the feed as the page shows it: its line of results, its cards, its links."""

    title: str
    line: str
    cards: tuple[FeedCard, ...]
    page: int
    pages: int
    previous_link: str | None
    next_link: str | None
    # What the feed without item proposes: 7 days, from a shorter period.
    wider_link: str | None
    has_unlisted_items: bool


def read_page_number(params: QueryParams) -> int | None:
    """The page asked, 1 without one; None for a page out of its form or beyond MAX_PAGE."""
    values = params.getlist(PAGE_FIELD)
    if not values:
        return 1
    if len(values) > 1 or not PAGE_NUMBER.fullmatch(values[0]):
        return None
    page = int(values[0])
    return page if page <= MAX_PAGE else None


def read_feed_form(params: QueryParams) -> FeedForm:
    """The form of the feed, each value refused named on its field."""
    received_q = params.get(SEARCH_FIELD, "").strip()
    kinds, kinds_error = read_kinds(params.getlist(KIND_FIELD))
    period, period_error = read_period(params.get(PERIOD_FIELD))
    start = params.get(START_FIELD, "")
    start_error = find_start_error(start) if period == DATE_PERIOD else None
    errors = (find_search_error(received_q), kinds_error, period_error, start_error)
    return FeedForm(
        # Without its control characters: one received is refused, so q is then shown, never sent.
        q=drop_control_characters(received_q),
        kinds=kinds,
        period=period,
        # Shown again only in its form: an input type=date holds a day or nothing, and a value
        # received is never sent back raw, whatever its length (D4: kept when the radio ignores it).
        start=start if START_DAY.fullmatch(start) else "",
        errors=tuple(error for error in errors if error is not None),
    )


def read_kinds(
    values: list[str],
) -> tuple[tuple[FeedKind, ...], FieldError | None]:
    """The kinds checked, in the order of the form; none checked is the five."""
    checked = {value for value in values if value}
    kinds = tuple(kind for kind in FEED_KINDS if kind in checked) or FEED_KINDS
    if checked - set(FEED_KINDS):
        return kinds, FieldError(KINDS_ID, KIND_REFUSED)
    return kinds, None


def read_period(value: str | None) -> tuple[Period, FieldError | None]:
    if value is None:
        return DEFAULT_PERIOD, None
    for period in PERIODS:
        if value == period:
            return period, None
    return DEFAULT_PERIOD, FieldError(PERIOD_ID, PERIOD_REFUSED)


def find_start_error(start: str) -> FieldError | None:
    if not start:
        return FieldError(START_ID, START_MISSING)
    if read_start_day(start) is None:
        return FieldError(START_ID, START_REFUSED)
    return None


def read_start_day(start: str) -> date | None:
    if not START_DAY.fullmatch(start):
        return None
    try:
        return date.fromisoformat(start)
    except ValueError:
        return None


def is_control_character(character: str) -> bool:
    return unicodedata.category(character) == "Cc"


def drop_control_characters(text: str) -> str:
    return "".join(
        character for character in text if not is_control_character(character)
    )


def find_search_error(q: str) -> FieldError | None:
    if len(q) > DATA_API_MAX_SEARCH_LENGTH:
        return FieldError(
            SEARCH_ID,
            f"La recherche fait {len(q)} caractères: {DATA_API_MAX_SEARCH_LENGTH} au plus.",
        )
    if not q:
        return None
    # Sent back raw in value and in the links of the pages, a control character would make the
    # HTML invalid; NonEmptyText refuses a NUL and a lone surrogate only.
    if any(map(is_control_character, q)):
        return FieldError(SEARCH_ID, SEARCH_CONTROL_REFUSED)
    try:
        SEARCH_TEXT.validate_python(q)
    except ValidationError:
        return FieldError(SEARCH_ID, SEARCH_CONTROL_REFUSED)
    return None


def fits_in_search_field(q: str) -> bool:
    """Whether q holds in the maxlength of its field, which counts the units of UTF-16, not the
    characters: a value beyond it is no valid HTML (WHATWG, RGAA 8.2)."""
    units = len(q.encode("utf-16-le", errors="surrogatepass")) // 2
    return units <= DATA_API_MAX_SEARCH_LENGTH


def build_query(form: FeedForm, now: datetime, page: int) -> FeedQuery:
    """The query of a form without error; a search empty is no search, as the form always sends
    q."""
    return FeedQuery(
        kinds=form.kinds,
        since_day=find_since_day(form, now),
        q=form.q or None,
        offset=(page - 1) * FEED_PAGE_SIZE,
    )


def find_since_day(form: FeedForm, now: datetime) -> date:
    """The start date, or the day N days before today in UTC: 1 day takes yesterday and today."""
    if form.period == DATE_PERIOD:
        start_day = read_start_day(form.start)
        if start_day is None:
            raise ValueError("start date refused by the form")
        return start_day
    today = now.astimezone(UTC).date()
    return today - timedelta(days=DAYS_BY_PERIOD[form.period])


def count_pages(total: int) -> int:
    """The pages of total items, one at least, MAX_PAGE at most."""
    return min(max(1, -(-total // FEED_PAGE_SIZE)), MAX_PAGE)


def has_unlisted_items(total: int) -> bool:
    """Whether items lie beyond the last page the data API serves."""
    return total > MAX_PAGE * FEED_PAGE_SIZE


def find_api_field_error(error: DataApiError) -> FieldError | None:
    """The refusal of the search by the data API, on its field; any other refusal is an error of
    the site, which builds kind, since, limit and offset itself."""
    if error.state == "data_api_invalid_parameter" and error.parameters == (
        SEARCH_FIELD,
    ):
        return FieldError(SEARCH_ID, SEARCH_REFUSED_BY_API)
    return None


def build_page_link(form: FeedForm, page: int) -> str:
    """The address of a page of the feed with its filters; page 1 without its number, a start date
    the radio ignores dropped."""
    params = [
        (SEARCH_FIELD, form.q),
        *((KIND_FIELD, kind) for kind in form.kinds),
        (PERIOD_FIELD, form.period),
    ]
    if form.period == DATE_PERIOD:
        params.append((START_FIELD, form.start))
    if page > 1:
        params.append((PAGE_FIELD, str(page)))
    return f"{FEED_PATH}?{urlencode(params)}"


def build_listing(
    form: FeedForm, query: FeedQuery, page: int, items: Sequence[FeedItem], total: int
) -> FeedListing:
    """The page of the feed of a form without error, page at most count_pages(total)."""
    pages = count_pages(total)
    is_shorter = form.period in DAYS_BY_PERIOD and form.period != WIDER_PERIOD
    return FeedListing(
        title=f"Quoi de neuf, page {page} sur {pages}" if total else NO_ITEM_TITLE,
        line=write_results_line(total, query.since_day, page, pages),
        cards=tuple(build_card(item) for item in items),
        page=page,
        pages=pages,
        previous_link=f"{build_page_link(form, page - 1)}#{RESULTS_ID}"
        if page > 1
        else None,
        next_link=f"{build_page_link(form, page + 1)}#{RESULTS_ID}"
        if page < pages
        else None,
        wider_link=build_page_link(replace(form, period=WIDER_PERIOD), 1)
        if not total and is_shorter
        else None,
        has_unlisted_items=has_unlisted_items(total),
    )


def write_results_line(total: int, since_day: date, page: int, pages: int) -> str:
    """The items found, the period applied and the page (Opquast 2025, rule 13)."""
    day = write_day(since_day)
    if total == 0:
        return f"Aucun item depuis le {day}."
    items = "1 item" if total == 1 else f"{total} items"
    return (
        f"{items} depuis le {day}, du plus récent au plus ancien."
        f" Page {page} sur {pages}, {FEED_PAGE_SIZE} items par page."
    )


def build_card(item: FeedItem) -> FeedCard:
    labels = LABELS_BY_KIND[item.kind]
    title = clean_received_value(item.title)
    return FeedCard(
        kind_label=labels.card_label,
        kind_lang=labels.label_lang,
        day=item.source_date.date().isoformat(),
        day_text=write_day(item.source_date),
        is_exploited=is_exploited(item),
        identifiers=clean_received_text(write_identifiers(item)),
        withdrawn_text=None
        if item.withdrawn_at is None
        else f"retirée du catalogue le {write_day(item.withdrawn_at)}",
        title=title or NO_TITLE,
        title_lang=labels.title_lang if title else None,
        detail_link=ITEM_PATH.format(item_id=item.id),
        link=keep_https_link(item.url),
        link_label=labels.link_label,
        link_note=write_link_note(labels),
        link_lang=labels.link_lang,
    )


def write_link_note(labels: KindLabels) -> str:
    """The announcement of the link to the source of a kind, its language first if English."""
    if labels.link_lang is None:
        return NEW_TAB_NOTE
    return f"en anglais, {NEW_TAB_NOTE}"


def is_exploited(item: FeedItem) -> bool:
    """By the field exploited of the data API: a vulnerability, always true, being in the CISA KEV
    catalog; an advisory when its CVE is in it, withdrawn since or not. A vulnerability withdrawn
    drops the mark, which its line of the withdrawal would contradict (Sabine, 2026-11-11); an
    advisory keeps it, the list serving no withdrawal of its CVE (a limit, said by #564)."""
    if isinstance(item, FeedVulnerability | FeedAdvisory):
        return item.exploited is True and item.withdrawn_at is None
    return False


def write_identifiers(item: FeedItem) -> str:
    match item:
        case FeedPaper():
            return f"arXiv {item.arxiv_id}"
        case FeedVulnerability():
            return item.cve_id
        case FeedAdvisory():
            return write_advisory_identifiers(item)
        case FeedRelease():
            return item.repository_name
        case FeedNewsletterArticle():
            return write_newsletter_name(item.edition)
        case _:
            assert_never(item)


def write_newsletter_name(edition: str) -> str:
    return NEWSLETTER_NAME_BY_EDITION.get(edition, f"TLDR {edition}")


def write_advisory_identifiers(advisory: FeedAdvisory) -> str:
    packages = ", ".join(advisory.packages)
    if advisory.packages_truncated:
        packages += " et d’autres"
    parts = (advisory.ghsa_id, advisory.cve_id, packages)
    return " · ".join(part for part in parts if part)


def keep_https_link(url: str | None) -> str | None:
    """The URL if it is https to a host, printable and without space; else None, never a link. An
    answer of the data API is untrusted: a host urlsplit refuses ([oops) gives no link, never an
    error."""
    if (
        url is None
        or not url.startswith("https://")
        or not url.isprintable()
        or " " in url
    ):
        return None
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return url if host else None
