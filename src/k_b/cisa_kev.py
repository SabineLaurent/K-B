"""Read the vulnerabilities of a raw CISA KEV catalog that were added since the last collection,
and convert each one into an item.
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from k_b.items import CVE_ID, Item

NVD_PAGE_URL = "https://nvd.nist.gov/vuln/detail/"
REQUIRED_COLUMNS = (
    "cveID",
    "vendorProject",
    "product",
    "vulnerabilityName",
    "dateAdded",
    "shortDescription",
)


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
