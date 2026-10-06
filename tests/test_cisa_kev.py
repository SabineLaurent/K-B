from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from k_b.cisa_kev import (
    Vulnerability,
    convert_vulnerability,
    read_new_vulnerabilities,
)

EXTRACT = (Path(__file__).parent / "fixtures" / "cisa_kev_extract.csv").read_bytes()
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = "automation/cisa_kev/2026-10-05T093000Z.csv"


def test_the_first_collection_reads_the_whole_catalog():
    vulnerabilities = read_new_vulnerabilities(EXTRACT, last_collected_at=None)

    assert [vulnerability.cve_id for vulnerability in vulnerabilities] == [
        "CVE-2026-86950",
        "CVE-2026-88772",
        "CVE-2026-88771",
        "CVE-2020-29583",
    ]


def test_only_vulnerabilities_added_since_the_day_before_the_last_collection_are_read():
    last_collected_at = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)

    vulnerabilities = read_new_vulnerabilities(EXTRACT, last_collected_at)

    assert [vulnerability.cve_id for vulnerability in vulnerabilities] == [
        "CVE-2026-86950",
        "CVE-2026-88772",
        "CVE-2026-88771",
    ]


def test_a_vulnerability_keeps_its_publication_date_and_description():
    newest = read_new_vulnerabilities(EXTRACT, last_collected_at=None)[0]

    assert newest.date_added == date(2026, 9, 29)
    assert newest.vendor_project == "Apple"
    assert newest.product == "Multiple Products"
    assert (
        newest.vulnerability_name
        == "Apple Multiple Products Out-of-Bounds Write Vulnerability"
    )
    assert newest.short_description.startswith("Apple iOS, macOS, and iPadOS contain")


def test_a_catalog_without_the_expected_columns_is_refused():
    with pytest.raises(ValueError, match="dateAdded"):
        read_new_vulnerabilities(b"cveID,vendorProject\nCVE-2026-1234,Apple\n", None)


@pytest.mark.parametrize(
    ("cve_id", "date_added"),
    [("not-a-cve", "2026-09-29"), ("CVE-2026-1234", "29/09/2026")],
)
def test_a_malformed_row_is_refused(cve_id, date_added):
    header, first_row = EXTRACT.decode("utf-8").splitlines()[:2]
    fields = first_row.split(",", 5)
    fields[0], fields[4] = cve_id, date_added
    malformed_catalog = f"{header}\n{','.join(fields)}\n".encode()

    with pytest.raises(ValueError, match="line 2"):
        read_new_vulnerabilities(malformed_catalog, None)


def test_a_row_with_missing_fields_is_refused():
    header = EXTRACT.decode("utf-8").splitlines()[0]

    with pytest.raises(ValueError, match="line 2: missing fields"):
        read_new_vulnerabilities(f"{header}\nCVE-2026-1234,Apple\n".encode(), None)


def test_a_vulnerability_dated_the_day_before_a_collection_run_after_midnight_utc_is_kept():
    # 02:00 UTC on the 30th is still the 29th in the Americas: rows dated the 29th may follow.
    last_collected_at = datetime(2026, 9, 30, 2, 0, tzinfo=UTC)

    vulnerabilities = read_new_vulnerabilities(EXTRACT, last_collected_at)

    assert [vulnerability.cve_id for vulnerability in vulnerabilities] == [
        "CVE-2026-86950"
    ]


def test_a_catalog_starting_with_a_byte_order_mark_is_read():
    vulnerabilities = read_new_vulnerabilities(b"\xef\xbb\xbf" + EXTRACT, None)

    assert len(vulnerabilities) == 4


def test_a_vulnerability_points_to_its_nvd_page_and_is_dated_at_midnight_utc():
    vulnerability = Vulnerability(
        cve_id="CVE-2026-86950",
        vendor_project="Apple",
        product="Multiple Products",
        vulnerability_name="Apple Multiple Products Out-of-Bounds Write Vulnerability",
        date_added=date(2026, 9, 29),
        short_description="An out-of-bounds write.",
    )

    item = convert_vulnerability(vulnerability, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "cisa_kev"
    assert item.source_item_id == "CVE-2026-86950"
    assert item.title == "Apple Multiple Products Out-of-Bounds Write Vulnerability"
    assert item.url == "https://nvd.nist.gov/vuln/detail/CVE-2026-86950"
    assert item.published_at == datetime(2026, 9, 29, tzinfo=UTC)
    assert item.summary == "An out-of-bounds write."
    assert item.cve == "CVE-2026-86950"
    assert item.is_vulnerability is True
