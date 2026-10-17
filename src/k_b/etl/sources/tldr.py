"""The TLDR source: its download (E), then its reader (T).

Download the raw TLDR edition pages, one per day, as tldr.tech serves them.

Read the articles of a raw edition page, and convert each one into an item.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import sleep

from bs4 import BeautifulSoup, Tag
from bs4.exceptions import ParserRejectedMarkup

from k_b.core.quoting import quote_value
from k_b.etl.http_download import RedirectedOutsideError, download
from k_b.etl.raw_store import AUTOMATED_WATCH_DIR_NAME, find_stream
from k_b.etl.source_contract import EntryReading, SourceReader
from k_b.items import EDITION_SLUG, Item, SourceCode, at_midnight_utc

SOURCE_CODE: SourceCode = "tldr"
# Adding an edition is adding its slug, as in https://tldr.tech/<slug>/<YYYY-MM-DD>.
TRACKED_EDITIONS = ("ai", "infosec", "dev")
SITE_URL = "https://tldr.tech/"
# An edition page weighs about 80 KB in 2026.
MAX_PAGE_BYTES = 1024 * 1024
# One page at a time, with a pause: tldr.tech publishes no rate limit (decided in #6).
PAUSE_BETWEEN_PAGES_SECONDS = 2
# For testing the collection; to widen when K-B is put into service.
FIRST_COLLECTION_DAYS = 7

logger = logging.getLogger(__name__)


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "tldr"


class TldrSource:
    extension = "html"
    acquisition_dir_name = AUTOMATED_WATCH_DIR_NAME

    def __init__(self, edition: str):
        if not EDITION_SLUG.fullmatch(edition):
            raise ValueError(f"not a TLDR edition slug: {edition!r}")
        self.edition = edition
        self.name = f"{FOLDER_PREFIX}_{edition}"

    def fetch(self, last_collected_at: datetime | None) -> dict[str, bytes] | None:
        """Return the edition page of each day to collect, by day; None if there is none.

        A day redirected to the landing page of the edition (observed for 2026-10-03 and
        2026-10-04) has no edition page: it is logged and skipped. Any other redirection or
        HTTP error is raised.
        """
        days = list_days_to_collect(last_collected_at, current_day())
        pages = {}
        for position, day in enumerate(days):
            if position > 0:
                sleep(PAUSE_BETWEEN_PAGES_SECONDS)
            page_url = f"{SITE_URL}{self.edition}/{day.isoformat()}"
            try:
                # The page url itself is the trusted prefix: any redirection is noticed.
                page = download(page_url, page_url, MAX_PAGE_BYTES)
            except Exception as error:
                if (
                    isinstance(error, RedirectedOutsideError)
                    and error.redirect_url.rstrip("/") == f"{SITE_URL}{self.edition}"
                ):
                    logger.info(
                        "%s %s: no edition page, redirected to %s",
                        self.name,
                        day,
                        error.redirect_url,
                    )
                    continue
                # The error alone does not always say which day and url it is about. Logged
                # where the collection handles it (etl/extract.py), with this note.
                error.add_note(f"{self.name} {day}, from {page_url}")
                raise
            logger.info("%s %s: edition page, %d bytes", self.name, day, len(page))
            pages[day.isoformat()] = page
        if not pages:
            logger.info(
                "%s: no edition page from %s to %s", self.name, days[0], days[-1]
            )
        return pages or None


def current_day() -> date:
    return datetime.now(UTC).date()


def list_days_to_collect(last_collected_at: datetime | None, today: date) -> list[date]:
    """Every day from the day of the last collection, or 7 days ago, to today.

    The day of the last collection is read again: its edition may have come out after it. The
    articles of a page collected twice are left out at the import, as already seen.
    """
    if last_collected_at is None:
        first_day = today - timedelta(days=FIRST_COLLECTION_DAYS)
    else:
        first_day = last_collected_at.astimezone(UTC).date()
    if first_day > today:
        raise ValueError(f"last collection day {first_day} is after today {today}")
    return [
        first_day + timedelta(days=offset)
        for offset in range((today - first_day).days + 1)
    ]


# The first h1 of an edition page: "TLDR AI 2026-10-08"; the landing page has no date.
EDITION_PAGE_TITLE = re.compile(r"TLDR .+ (\d{4}-\d{2}-\d{2})")
SPONSOR_MARK = "(Sponsor)"
# The job board of TLDR itself: its offers are published among the articles, without a mark.
TLDR_JOB_OFFER_URL_PREFIX = "https://jobs.ashbyhq.com/tldr.tech/"


@dataclass(frozen=True)
class TldrArticle:
    """An entry of an edition page, as read: the item refuses an invalid one."""

    edition_date: date
    # Its position among the article elements of the page, from 1, sponsored entries and job
    # offers counted: a change of what is left out renumbers nothing.
    rank: int
    title: str
    # The href as written, "" if there is none.
    link: str
    # Plain text; "" if there is none.
    summary: str


def read_articles(page: bytes) -> EntryReading[TldrArticle]:
    """One article per entry of an edition page, sponsored entries and job offers of TLDR left
    out.

    An entry is returned as read, even without a title, a link or a summary: the item refuses
    it, and the others are still read; the reader itself rejects none. A page that is not UTF-8, whose first h1 is not the
    title of an edition, with an article inside another, or without any complete article (a
    selector no longer matches) is refused whole.
    """
    try:
        # Decoded here: BeautifulSoup would guess the encoding of bytes.
        soup = BeautifulSoup(page.decode("utf-8"), "html.parser")
    except ParserRejectedMarkup:
        # Its message may quote the page (#212).
        raise ValueError("page rejected by html.parser") from None
    edition_date = read_edition_date(soup)
    # Refused before its entries are read: each article is searched whole, and a page of
    # articles inside one another would be searched as many times as it has articles.
    if soup.select_one("article article") is not None:
        raise ValueError("article element inside an article element")
    entries = soup.select("article")
    articles = [
        article
        for rank, entry in enumerate(entries, start=1)
        if not is_left_out(article := read_article(entry, edition_date, rank))
    ]
    if not any(
        article.title and article.link and article.summary for article in articles
    ):
        raise ValueError(
            "no article with a title, a link and a summary among "
            f"{len(entries)} article elements"
        )
    return EntryReading(articles, [])


def read_edition_date(soup: BeautifulSoup) -> date:
    heading = soup.select_one("h1")
    if heading is None:
        raise ValueError("no h1 in the page")
    title = read_text(heading)
    refusal = ValueError(
        "first h1 is not an edition title with its date: " + quote_value(title)
    )
    match = EDITION_PAGE_TITLE.fullmatch(title)
    if match is None:
        raise refusal
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        # The form of a date, but no such day (2026-13-45).
        raise refusal from None


def read_article(entry: Tag, edition_date: date, rank: int) -> TldrArticle:
    link = entry.select_one("a.font-bold")
    href = link.get("href") if link else None
    return TldrArticle(
        edition_date=edition_date,
        rank=rank,
        title=read_text(link),
        # A str for one href; BeautifulSoup types every attribute as a str or a list.
        link=href if isinstance(href, str) else "",
        summary=read_text(entry.select_one("div.newsletter-html")),
    )


def read_text(element: Tag | None) -> str:
    """The text of an element, its pieces (paragraphs, links) a space apart and each run of
    white space as one space; "" without the element."""
    return " ".join(element.get_text(" ").split()) if element else ""


def is_left_out(article: TldrArticle) -> bool:
    return SPONSOR_MARK in article.title or article.link.startswith(
        TLDR_JOB_OFFER_URL_PREFIX
    )


def convert_article(
    article: TldrArticle, collected_at: datetime, raw_file_path: str
) -> Item:
    # The edition is the end of the name of its raw folder (tldr_ai). find_stream cannot
    # raise here: the path of a page read holds its source folder.
    edition = find_stream(raw_file_path).removeprefix(FOLDER_PREFIX).removeprefix("_")
    return Item(
        source_code=SOURCE_CODE,
        source_item_id=f"{edition}/{article.edition_date.isoformat()}#{article.rank}",
        kind="newsletter_article",
        title=article.title,
        # Some links are escaped twice in the page: "&amp;" is still there once the HTML is
        # parsed. The utm_* parameters are removed with those of every item (etl/normalize.py).
        url=article.link.replace("&amp;", "&"),
        published_at=at_midnight_utc(article.edition_date),
        summary=article.summary or None,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
        edition=edition,
        rank=article.rank,
    )


READER: SourceReader[TldrArticle] = SourceReader(
    SOURCE_CODE, read_articles, convert_article
)
