"""Download the CISA catalog of known exploited vulnerabilities (KEV), as published."""

from datetime import datetime
from email.utils import format_datetime
from urllib.error import HTTPError

from k_b.http_download import download

CATALOG_URL = "https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv"
# The catalog weighs about 1 MB in 2026: ten times that is not a catalog any more.
MAX_CATALOG_BYTES = 10 * 1024 * 1024
# Redirections are followed, even to plain HTTP: only a catalog served from here is trusted.
TRUSTED_URL_PREFIX = "https://www.cisa.gov/"
HTTP_NOT_MODIFIED = 304


class CisaKevSource:
    name = "cisa_kev"
    extension = "csv"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the whole catalog, or None if it has not changed since last_collected_at."""
        headers = {}
        if last_collected_at is not None:
            headers["If-Modified-Since"] = format_datetime(last_collected_at, usegmt=True)
        try:
            return download(CATALOG_URL, TRUSTED_URL_PREFIX, MAX_CATALOG_BYTES, headers)
        except HTTPError as error:
            if error.code == HTTP_NOT_MODIFIED:
                error.close()
                return None
            raise
