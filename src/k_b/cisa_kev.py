"""Read the vulnerabilities of a raw CISA KEV catalog that were added since the last collection."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")
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
    """One vulnerability per row added on or after the day of the last collection (None: all).

    The day itself is kept: a row added that day after the collection would otherwise be lost.
    """
    rows = csv.DictReader(io.StringIO(raw_catalog.decode("utf-8"), newline=""))
    columns = rows.fieldnames or []
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing_columns:
        raise ValueError(f"catalog without the columns {', '.join(missing_columns)}")
    vulnerabilities = [parse_vulnerability(row, rows.line_num) for row in rows]
    if last_collected_at is None:
        return vulnerabilities
    since = last_collected_at.date()
    return [vulnerability for vulnerability in vulnerabilities if vulnerability.date_added >= since]


def parse_vulnerability(row: dict[str, str], line_number: int) -> Vulnerability:
    if any(row[column] is None for column in REQUIRED_COLUMNS):
        raise ValueError(f"line {line_number}: missing fields")
    cve_id = row["cveID"]
    if not CVE_ID.fullmatch(cve_id):
        raise ValueError(f"line {line_number}: not a CVE identifier: {cve_id!r}")
    try:
        date_added = date.fromisoformat(row["dateAdded"])
    except ValueError as error:
        raise ValueError(f"line {line_number}: invalid dateAdded: {row['dateAdded']!r}") from error
    return Vulnerability(
        cve_id=cve_id,
        vendor_project=row["vendorProject"],
        product=row["product"],
        vulnerability_name=row["vulnerabilityName"],
        date_added=date_added,
        short_description=row["shortDescription"],
    )
