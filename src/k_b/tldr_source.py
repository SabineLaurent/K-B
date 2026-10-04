"""Download the TLDR edition pages published since the last collection, as tldr.tech serves them."""

import re
from datetime import UTC, date, datetime, timedelta
from time import sleep

from k_b.http_download import download
from k_b.tldr_editions import read_articles, read_edition_date

# Adding an edition is adding its slug, as in https://tldr.tech/<edition>/<YYYY-MM-DD>.
TRACKED_EDITIONS = ("ai", "infosec", "dev")
EDITION_SLUG = re.compile(r"[a-z]+")
SITE_URL = "https://tldr.tech/"
# An edition page weighs about 80 KB in 2026.
MAX_PAGE_BYTES = 1024 * 1024
# One page at a time, with a pause: tldr.tech publishes no rate limit (decided in #6).
PAUSE_BETWEEN_PAGES_SECONDS = 2
# For testing the collection; to widen when K-B is put into service.
FIRST_COLLECTION_DAYS = 7
SATURDAY = 5


class TldrSource:
    extension = "html"

    def __init__(self, edition: str):
        if not EDITION_SLUG.fullmatch(edition):
            raise ValueError(f"not a TLDR edition slug: {edition!r}")
        self.edition = edition
        self.name = f"tldr_{edition}"

    def fetch(self, last_collected_at: datetime | None) -> dict[str, bytes] | None:
        """Return each edition page since the day before last_collected_at, by day; None if none.

        A day without an edition (weekend, holiday, not out yet) is redirected to the landing
        page: it is recognised by its title, which carries no edition date.
        """
        today = datetime.now(UTC).date()
        days = list_edition_days(last_collected_at, today)
        pages = {}
        for position, day in enumerate(days):
            if position > 0:
                sleep(PAUSE_BETWEEN_PAGES_SECONDS)
            page = download(f"{SITE_URL}{self.edition}/{day.isoformat()}", SITE_URL, MAX_PAGE_BYTES)
            if read_edition_date(page) != day:
                continue
            if not read_articles(page):
                raise ValueError(f"{self.name} {day}: an edition page with no article")
            pages[day.isoformat()] = page
        if not pages and any(day < today for day in days):
            # Past weekdays all without an edition: the page structure has probably changed.
            raise ValueError(f"{self.name}: no edition found on past weekdays, refused")
        return pages or None


def list_edition_days(last_collected_at: datetime | None, today: date) -> list[date]:
    """Weekdays from the day before the last collection (a margin), or the last 7 days, to today.

    The day before is read again in case its edition came out after the last collection; the
    overlap with the previous raw pages is removed when merging.
    """
    if last_collected_at is None:
        first_day = today - timedelta(days=FIRST_COLLECTION_DAYS)
    else:
        first_day = last_collected_at.astimezone(UTC).date() - timedelta(days=1)
    days = (first_day + timedelta(days=offset) for offset in range((today - first_day).days + 1))
    return [day for day in days if day.weekday() < SATURDAY]
