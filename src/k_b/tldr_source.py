"""Download the TLDR edition pages published since the last collection, as tldr.tech serves them."""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlsplit

from k_b.http_download import RedirectedOutsideError, download
from k_b.tldr_editions import read_articles, read_edition_date, read_page_title

# Adding an edition is adding a line: its slug, as in https://tldr.tech/<slug>/<YYYY-MM-DD>,
# and the title its pages show, as in "TLDR Information Security 2026-10-01" (read 2026-10-04).
TRACKED_EDITIONS = {"ai": "AI", "infosec": "Information Security", "dev": "Dev"}
EDITION_SLUG = re.compile(r"[a-z]+")
SITE_URL = "https://tldr.tech/"
# An edition page weighs about 80 KB in 2026.
MAX_PAGE_BYTES = 1024 * 1024
# One page at a time, with a pause: tldr.tech publishes no rate limit (decided in #6).
PAUSE_BETWEEN_PAGES_SECONDS = 2
# For testing the collection; to widen when K-B is put into service.
FIRST_COLLECTION_DAYS = 7
SATURDAY = 5

# A page gone for good: skipped when a later day is an edition. Any other error status is
# refused, so that a transient one never costs a day.
HTTP_GONE = (404, 410)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DayAnswer:
    """What tldr.tech answered for one day: a page, nothing, or a status saying it is gone."""

    day: date
    page: bytes | None
    is_edition: bool = False
    gone_status: int | None = None


class TldrSource:
    extension = "html"

    def __init__(self, edition: str, edition_title: str):
        if not EDITION_SLUG.fullmatch(edition):
            raise ValueError(f"not a TLDR edition slug: {edition!r}")
        self.edition = edition
        self.edition_title = edition_title
        self.name = f"tldr_{edition}"

    def fetch(self, last_collected_at: datetime | None) -> dict[str, bytes] | None:
        """Return each edition page of the days to collect, by day; None if there is none.

        A past day redirected to the landing page of the edition has no edition. A past day
        gone (HTTP 404 or 410) is skipped, and a past page with another title is kept, only if
        a later day of the window is an edition page; otherwise they are refused, as is any
        other answer. Today's edition may not be out yet: whatever answers instead is logged,
        not refused, and the next collection, which starts from today, asks again.
        """
        today = current_day()
        answers = []
        for position, day in enumerate(list_edition_days(last_collected_at, today)):
            if position > 0:
                sleep(PAUSE_BETWEEN_PAGES_SECONDS)
            if day == today:
                page = self.download_edition_page_of_today(day)
                answers.append(DayAnswer(day, page=page, is_edition=page is not None))
            else:
                answers.append(self.download_past_day(day))
        edition_days = [answer.day for answer in answers if answer.is_edition]
        last_edition_day = max(edition_days, default=None)
        pages = {}
        has_article = False
        for answer in answers:
            if answer.is_edition:
                page_name = f"{self.name} {answer.day}"
                if read_articles(answer.page, page_name):
                    has_article = True
                else:
                    logger.warning("%s: an edition page with no article", page_name)
                pages[answer.day.isoformat()] = answer.page
            elif answer.page is not None or answer.gone_status is not None:
                if last_edition_day is None or answer.day > last_edition_day:
                    raise ValueError(self.describe_anomaly(answer))
                outcome = "page kept" if answer.page is not None else "day skipped"
                logger.warning(
                    "%s, %s, %s is an edition page",
                    self.describe_anomaly(answer),
                    outcome,
                    last_edition_day,
                )
                if answer.page is not None:
                    pages[answer.day.isoformat()] = answer.page
        if edition_days and not has_article:
            raise ValueError(
                f"{self.name}: no article in any of the {len(edition_days)} edition pages"
            )
        return pages or None

    def download_past_day(self, day: date) -> DayAnswer:
        """Download the edition page of a past day and tell whether it is that edition."""
        page_url = self.page_url(day)
        try:
            # The page url itself is the trusted prefix: any redirection is noticed.
            page = download(page_url, page_url, MAX_PAGE_BYTES)
        except RedirectedOutsideError as refusal:
            if not self.is_landing_page(refusal.redirect_url):
                raise
            # A weekday without an edition leaves a trace: a silent one would hide a site that
            # sends every day to its landing page.
            logger.warning(
                "%s %s: no edition page, redirected to %s", self.name, day, refusal.redirect_url
            )
            return DayAnswer(day, page=None)
        except HTTPError as error:
            if error.code in HTTP_GONE:
                return DayAnswer(day, page=None, gone_status=error.code)
            raise ValueError(f"{self.name} {day}: HTTP {error.code} from {page_url}") from error
        return DayAnswer(
            day, page=page, is_edition=read_edition_date(page, self.edition_title) == day
        )

    def describe_anomaly(self, answer: DayAnswer) -> str:
        if answer.gone_status is not None:
            return (
                f"{self.name} {answer.day}: HTTP {answer.gone_status} from "
                f"{self.page_url(answer.day)}"
            )
        return (
            f"{self.name} {answer.day}: page title {read_page_title(answer.page)!r}, "
            f"expected {self.expected_title(answer.day)!r}"
        )

    def download_edition_page_of_today(self, day: date) -> bytes | None:
        """Return today's edition page, or None, logging what answered instead.

        Today's edition may not be out yet: no answer is an error, the next collection asks
        for this day again.
        """
        page_url = self.page_url(day)
        try:
            page = download(page_url, page_url, MAX_PAGE_BYTES)
        except RedirectedOutsideError as refusal:
            self.log_no_edition_page(day, f"redirected to {refusal.redirect_url}")
            return None
        except HTTPError as error:
            self.log_no_edition_page(day, f"HTTP {error.code}")
            return None
        if read_edition_date(page, self.edition_title) != day:
            self.log_no_edition_page(day, f"page title {read_page_title(page)!r}")
            return None
        return page

    def page_url(self, day: date) -> str:
        return f"{SITE_URL}{self.edition}/{day.isoformat()}"

    def log_no_edition_page(self, day: date, answer: str) -> None:
        logger.info("%s %s: no edition page, %s", self.name, day, answer)

    def expected_title(self, day: date) -> str:
        return f"TLDR {self.edition_title} {day.isoformat()}"

    def is_landing_page(self, url: str) -> bool:
        """Whether url is https://tldr.tech/<edition>, give or take a final slash or a query."""
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname == "tldr.tech"
            and "@" not in parts.netloc
            and parts.port is None
            and parts.path.rstrip("/") == f"/{self.edition}"
        )


def current_day() -> date:
    return datetime.now(UTC).date()


def list_edition_days(last_collected_at: datetime | None, today: date) -> list[date]:
    """Weekdays from the day of the last collection, or 7 days ago, to today.

    The day of the last collection is read again: its edition may have come out after it. The
    overlap with the previous raw pages is removed when merging.
    """
    if last_collected_at is None:
        first_day = today - timedelta(days=FIRST_COLLECTION_DAYS)
    else:
        first_day = last_collected_at.astimezone(UTC).date()
    days = (first_day + timedelta(days=offset) for offset in range((today - first_day).days + 1))
    return [day for day in days if day.weekday() < SATURDAY]
