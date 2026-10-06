"""The CISA KEV source: its download (E), then its reader (T).

Download the CISA catalog of known exploited vulnerabilities (KEV), as published.

Read the vulnerabilities of a raw CISA KEV catalog that were added since the last collection,
and convert each one into an item.
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from email.utils import format_datetime
from urllib.error import HTTPError

from k_b.http_download import download
from k_b.items import CVE_ID, Item
from k_b.source_contract import SourceReader

CATALOG_URL = (
    "https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv"
)
# The catalog weighs about 1 MB in 2026: ten times that is not a catalog any more.
MAX_CATALOG_BYTES = 10 * 1024 * 1024
# Redirections are followed, even to plain HTTP: only a catalog served from here is trusted.
TRUSTED_URL_PREFIX = "https://www.cisa.gov/"
HTTP_NOT_MODIFIED = 304


NVD_PAGE_URL = "https://nvd.nist.gov/vuln/detail/"
REQUIRED_COLUMNS = (
    "cveID",
    "vendorProject",
    "product",
    "vulnerabilityName",
    "dateAdded",
    "shortDescription",
)


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "cisa_kev"


class CisaKevSource:
    name = FOLDER_PREFIX
    extension = "csv"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the whole catalog, or None if it has not changed since last_collected_at.

        The catalog is read before it is returned: a page that is not a catalog (maintenance,
        captcha) raises ValueError instead of being stored as one.
        """
        headers = {}
        if last_collected_at is not None:
            headers["If-Modified-Since"] = format_datetime(
                last_collected_at, usegmt=True
            )
        try:
            raw_catalog = download(
                CATALOG_URL, TRUSTED_URL_PREFIX, MAX_CATALOG_BYTES, headers
            )
        except HTTPError as error:
            if error.code == HTTP_NOT_MODIFIED:
                error.close()
                return None
            raise
        read_catalog(raw_catalog)
        return raw_catalog


@dataclass(frozen=True)
class Vulnerability:
    cve_id: str
    vendor_project: str
    product: str
    vulnerability_name: str
    date_added: date
    short_description: str


def read_new_vulnerabilities(
    raw_catalog: bytes, last_collected_at: datetime | None
) -> list[Vulnerability]:
    """One vulnerability per row added since the day before the last collection (None: all).

    dateAdded is a day without a time zone, not an instant: it is not converted, it is compared
    with a day of margin, so no row is lost whatever its zone. Duplicates go at the merge.
    """
    # utf-8-sig: a byte order mark would otherwise stick to the first column name.
    rows = csv.DictReader(io.StringIO(raw_catalog.decode("utf-8-sig"), newline=""))
    columns = rows.fieldnames or []
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing_columns:
        raise ValueError(f"catalog without the columns {', '.join(missing_columns)}")
    vulnerabilities = [parse_vulnerability(row, rows.line_num) for row in rows]
    if last_collected_at is None:
        return vulnerabilities
    since = last_collected_at.date() - timedelta(days=1)
    return [
        vulnerability
        for vulnerability in vulnerabilities
        if vulnerability.date_added >= since
    ]


def parse_vulnerability(row: dict[str, str], line_number: int) -> Vulnerability:
    if any(row[column] is None for column in REQUIRED_COLUMNS):
        raise ValueError(f"line {line_number}: missing fields")
    cve_id = row["cveID"]
    if not CVE_ID.fullmatch(cve_id):
        raise ValueError(f"line {line_number}: not a CVE identifier: {cve_id!r}")
    try:
        date_added = date.fromisoformat(row["dateAdded"])
    except ValueError as error:
        raise ValueError(
            f"line {line_number}: invalid dateAdded: {row['dateAdded']!r}"
        ) from error
    return Vulnerability(
        cve_id=cve_id,
        vendor_project=row["vendorProject"],
        product=row["product"],
        vulnerability_name=row["vulnerabilityName"],
        date_added=date_added,
        short_description=row["shortDescription"],
    )


def convert_vulnerability(
    vulnerability: Vulnerability, collected_at: datetime, raw_file_path: str
) -> Item:
    return Item(
        source_code="cisa_kev",
        source_item_id=vulnerability.cve_id,
        title=vulnerability.vulnerability_name,
        url=NVD_PAGE_URL + vulnerability.cve_id,
        # dateAdded is a day: stored at midnight UTC, a writing convention (docs/stockage.md).
        published_at=datetime.combine(vulnerability.date_added, time(), tzinfo=UTC),
        summary=vulnerability.short_description,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
        cve=vulnerability.cve_id,
        is_vulnerability=True,
    )


def read_catalog(raw_catalog: bytes) -> list[Vulnerability]:
    """The whole catalog: duplicates between collections are removed by the merge."""
    return read_new_vulnerabilities(raw_catalog, last_collected_at=None)


READER: SourceReader[Vulnerability] = SourceReader(read_catalog, convert_vulnerability)
