"""Download the TLDR edition pages published since the last collection, as tldr.tech serves them."""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlsplit

from k_b.http_download import RedirectedOutsideError, download
from k_b.tldr_editions import read_articles, read_edition_date

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

logger = logging.getLogger(__name__)


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

        A past day without an edition (weekend, holiday) is redirected to the landing page of
        the edition; anything else that is not an edition page means the site has changed:
        refused. Today's edition may not be out yet: whatever answers instead is no error, and
        the next collection, which starts from today, asks again.
        """
        pages = {}
        today = current_day()
        for position, day in enumerate(list_edition_days(last_collected_at, today)):
            if position > 0:
                sleep(PAUSE_BETWEEN_PAGES_SECONDS)
            if day == today:
                page = self.download_edition_page_of_today(day)
            else:
                page = self.download_edition_page(day)
            if page is None:
                continue
            if read_edition_date(page, self.edition_title) != day:
                raise ValueError(f"{self.name} {day}: no dated edition title, structure changed?")
            if not read_articles(page):
                logger.warning("%s %s: an edition page with no article", self.name, day)
            pages[day.isoformat()] = page
        if pages and not any(read_articles(page) for page in pages.values()):
            raise ValueError(f"{self.name}: no article in any edition page, structure changed?")
        return pages or None

    def download_edition_page(self, day: date) -> bytes | None:
        """Return the edition page of day, or None if tldr.tech redirects to the landing page."""
        page_url = f"{SITE_URL}{self.edition}/{day.isoformat()}"
        try:
            # The page url itself is the trusted prefix: any redirection is noticed.
            return download(page_url, page_url, MAX_PAGE_BYTES)
        except RedirectedOutsideError as refusal:
            if self.is_landing_page(refusal.redirect_url):
                return None
            raise

    def download_edition_page_of_today(self, day: date) -> bytes | None:
        """Return today's edition page, or None if it does not look out yet."""
        try:
            page = self.download_edition_page(day)
        except (RedirectedOutsideError, HTTPError) as answer:
            logger.info("%s %s: edition not out yet (%s)", self.name, day, answer)
            return None
        if page is not None and read_edition_date(page, self.edition_title) != day:
            logger.info("%s %s: edition not out yet (not an edition page)", self.name, day)
            return None
        return page

    def is_landing_page(self, url: str) -> bool:
        """Whether url is https://tldr.tech/<edition>, give or take a final slash or a query."""
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname == "tldr.tech"
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
