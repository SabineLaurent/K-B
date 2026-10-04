"""Download the raw TLDR edition pages, one per day, as tldr.tech serves them."""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from time import sleep

from k_b.http_download import RedirectedOutsideError, download

# Adding an edition is adding its slug, as in https://tldr.tech/<slug>/<YYYY-MM-DD>.
TRACKED_EDITIONS = ("ai", "infosec", "dev")
EDITION_SLUG = re.compile(r"[a-z]+")
SITE_URL = "https://tldr.tech/"
# An edition page weighs about 80 KB in 2026.
MAX_PAGE_BYTES = 1024 * 1024
# One page at a time, with a pause: tldr.tech publishes no rate limit (decided in #6).
PAUSE_BETWEEN_PAGES_SECONDS = 2
# For testing the collection; to widen when K-B is put into service.
FIRST_COLLECTION_DAYS = 7

logger = logging.getLogger(__name__)


class TldrSource:
    extension = "html"

    def __init__(self, edition: str):
        if not EDITION_SLUG.fullmatch(edition):
            raise ValueError(f"not a TLDR edition slug: {edition!r}")
        self.edition = edition
        self.name = f"tldr_{edition}"

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
                # The error alone does not always say which day and url it is about.
                logger.error("%s %s: %s, from %s", self.name, day, error, page_url)
                raise
            logger.info("%s %s: edition page, %d bytes", self.name, day, len(page))
            pages[day.isoformat()] = page
        if not pages:
            logger.info("%s: no edition page from %s to %s", self.name, days[0], days[-1])
        return pages or None


def current_day() -> date:
    return datetime.now(UTC).date()


def list_days_to_collect(last_collected_at: datetime | None, today: date) -> list[date]:
    """Every day from the day of the last collection, or 7 days ago, to today.

    The day of the last collection is read again: its edition may have come out after it. The
    duplicate page is removed when transforming.
    """
    if last_collected_at is None:
        first_day = today - timedelta(days=FIRST_COLLECTION_DAYS)
    else:
        first_day = last_collected_at.astimezone(UTC).date()
    return [first_day + timedelta(days=offset) for offset in range((today - first_day).days + 1)]
