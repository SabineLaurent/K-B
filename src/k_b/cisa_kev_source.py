"""Download the CISA catalog of known exploited vulnerabilities (KEV), as published."""

from datetime import datetime
from email.utils import format_datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CATALOG_URL = "https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv"
USER_AGENT = "K-B (+https://github.com/SabineLaurent/K-B)"
TIMEOUT_SECONDS = 30
# The catalog weighs about 1 MB in 2026: ten times that is not a catalog any more.
MAX_CATALOG_BYTES = 10 * 1024 * 1024
HTTP_NOT_MODIFIED = 304


class CisaKevSource:
    name = "cisa_kev"
    extension = "csv"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the whole catalog, or None if it has not changed since last_collected_at."""
        headers = {"User-Agent": USER_AGENT}
        if last_collected_at is not None:
            headers["If-Modified-Since"] = format_datetime(last_collected_at, usegmt=True)
        request = Request(CATALOG_URL, headers=headers)
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                catalog = response.read(MAX_CATALOG_BYTES + 1)
        except HTTPError as error:
            if error.code == HTTP_NOT_MODIFIED:
                return None
            raise
        if len(catalog) > MAX_CATALOG_BYTES:
            raise ValueError(f"catalog larger than {MAX_CATALOG_BYTES} bytes, refused")
        return catalog
