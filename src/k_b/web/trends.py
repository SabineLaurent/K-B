"""The page of the trends, without input nor output: the day read from the address, the start of a
window, the rows of its table and the page of each state (docs/site-web.md, "Tendances")."""

from dataclasses import dataclass
from datetime import date, timedelta

from starlette.datastructures import QueryParams

from k_b.core.config import GH_ARCHIVE_WINDOW_DAYS
from k_b.items import is_repository_name
from k_b.web.data_api_client import DataApiError, TrendWindow
from k_b.web.feed import (
    NEW_TAB_NOTE,
    FieldError,
    read_written_day,
    write_day_refusal,
)
from k_b.web.french_dates import write_day

TRENDS_PATH = "/tendances"
# The name of the field in the address, as GET /trends of the data API names it.
WINDOW_END_FIELD = "window_end"
WINDOW_END_ID = "window-end"
GITHUB_URL = "https://github.com"
# The announcement of each link to GitHub (C13 of #564; Opquast 2025, rules 131, 142 and 146).
GITHUB_LINK_NOTE = f"en anglais, {NEW_TAB_NOTE}"
# Groups the thousands of a count, as French writes them: 1 500 (chr, never an escape in the
# source, which a tool can turn into the character itself).
THOUSANDS_SEPARATOR = chr(0x202F)

# The field of the window, as a message of a day refused names it.
WINDOW_END_IN_MESSAGES = "Date"
WINDOW_END_REFUSED_BY_API = "La base de K-B refuse cette date: choisissez-en une autre."
# The title of the page in each state (RGAA 8.6).
REFUSED_TITLE = "Tendances, date à corriger"
EMPTY_BASE_TITLE = "Tendances, aucune tendance en base"
EMPTY_BASE_TEXT = "Aucune tendance en base."


@dataclass(frozen=True)
class TrendsForm:
    """The day asked, None for the latest window; or the refusal of the value received."""

    window_end: date | None
    error: FieldError | None


@dataclass(frozen=True)
class TrendRow:
    rank: int
    repository_name: str
    # None: a name is_repository_name refuses, never made a link.
    link: str | None
    stars: str
    forks: str


@dataclass(frozen=True)
class TrendsTable:
    """The rows of a window, and its first and last day; a day is the ISO day of its time
    element."""

    start_day: str
    start_text: str
    end_day: str
    end_text: str
    rows: tuple[TrendRow, ...]


@dataclass(frozen=True)
class TrendsPage:
    """The page of the trends in one of its states: a window, a day refused, a window absent."""

    title: str
    # The day the field shows: the last day of the window shown or asked, never a value refused.
    value: str
    error: FieldError | None
    table: TrendsTable | None
    empty_text: str | None
    latest_link: str | None


def read_trends_form(params: QueryParams) -> TrendsForm:
    """The day of the address, its last value if repeated; empty or absent, the latest window."""
    value = params.get(WINDOW_END_FIELD, "")
    if not value:
        return TrendsForm(None, None)
    window_end = read_written_day(value)
    if window_end is None:
        return TrendsForm(
            None,
            FieldError(WINDOW_END_ID, write_day_refusal(WINDOW_END_IN_MESSAGES, value)),
        )
    return TrendsForm(window_end, None)


def find_api_window_end_error(error: DataApiError) -> FieldError | None:
    """The refusal of the day by the data API, on its field; any other refusal is an error of the
    site, which sends window_end alone."""
    if error.state == "data_api_invalid_parameter" and error.parameters == (
        WINDOW_END_FIELD,
    ):
        return FieldError(WINDOW_END_ID, WINDOW_END_REFUSED_BY_API)
    return None


def find_window_start(window_end: date) -> date:
    """The first day of a window of GH_ARCHIVE_WINDOW_DAYS full days, which ends on window_end."""
    return window_end - timedelta(days=GH_ARCHIVE_WINDOW_DAYS - 1)


def write_count(count: int) -> str:
    return f"{count:,}".replace(",", THOUSANDS_SEPARATOR)


def build_trends_page(window: TrendWindow) -> TrendsPage:
    """A window: its rows in the order of the data API, ranked from 1."""
    start = find_window_start(window.window_end)
    table = TrendsTable(
        start_day=start.isoformat(),
        start_text=write_day(start),
        end_day=window.window_end.isoformat(),
        end_text=write_day(window.window_end),
        rows=tuple(
            TrendRow(
                rank=rank,
                repository_name=trend.repository_name,
                link=build_github_link(trend.repository_name),
                stars=write_count(trend.stars_gained),
                forks=write_count(trend.forks_gained),
            )
            for rank, trend in enumerate(window.trends, start=1)
        ),
    )
    return TrendsPage(
        title=f"Tendances du {table.start_text} au {table.end_text}",
        value=table.end_day,
        error=None,
        table=table,
        empty_text=None,
        latest_link=None,
    )


def build_github_link(repository_name: str) -> str | None:
    """The page of a repository on GitHub; None for a name is_repository_name refuses, a segment
    . or .. or a .. in it, which a browser could resolve to another page of GitHub. A
    RepositoryName has no character to encode."""
    if not is_repository_name(repository_name):
        return None
    return f"{GITHUB_URL}/{repository_name}"


def build_refused_page(error: FieldError) -> TrendsPage:
    """A value refused: never shown again, as a value of an input type=date is a valid day or
    nothing (WHATWG; RGAA 8.2)."""
    return TrendsPage(
        title=REFUSED_TITLE,
        value="",
        error=error,
        table=None,
        empty_text=None,
        latest_link=None,
    )


def build_missing_window_page(window_end: date | None) -> TrendsPage:
    """No window ending on window_end, with a link to the latest; without a day, no trend in the
    base (the 404 trend_window_not_found of both)."""
    if window_end is None:
        return TrendsPage(
            title=EMPTY_BASE_TITLE,
            value="",
            error=None,
            table=None,
            empty_text=EMPTY_BASE_TEXT,
            latest_link=None,
        )
    day = write_day(window_end)
    return TrendsPage(
        title=f"Tendances, aucune tendance le {day}",
        value=window_end.isoformat(),
        error=None,
        table=None,
        empty_text=f"Aucune tendance pour la fenêtre qui se termine le {day}.",
        latest_link=TRENDS_PATH,
    )
