import io
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest
from pydantic import ValidationError

from k_b.etl import http_download
from k_b.etl.sources import cisa_kev
from k_b.etl.sources.cisa_kev import (
    CisaKevSource,
    Vulnerability,
    convert_vulnerability,
    read_new_vulnerabilities,
)

EXTRACT = (
    Path(__file__).parent.parent / "fixtures" / "cisa_kev_extract.csv"
).read_bytes()


class FakeResponse(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url


class FakeUrlopen:
    """Stands for urllib's urlopen: records the request, answers without any network."""

    def __init__(self, body=EXTRACT, error=None, final_url=cisa_kev.CATALOG_URL):
        self.body = body
        self.final_url = final_url
        self.error = error
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error:
            raise self.error
        return FakeResponse(self.body, self.final_url)


@pytest.fixture
def fake_urlopen(monkeypatch):
    fake = FakeUrlopen()
    monkeypatch.setattr(http_download, "urlopen", fake)
    return fake


def test_the_whole_catalog_is_returned_unchanged(fake_urlopen):
    assert CisaKevSource().fetch(last_collected_at=None) == EXTRACT


def test_the_request_names_k_b_and_has_a_timeout(fake_urlopen):
    CisaKevSource().fetch(last_collected_at=None)

    request = fake_urlopen.requests[0]
    assert request.full_url == cisa_kev.CATALOG_URL
    assert request.get_header("User-agent").startswith("K-B")
    assert fake_urlopen.timeouts[0] > 0
    assert not request.has_header("If-modified-since")


def test_a_later_collection_asks_only_for_a_catalog_modified_since_the_last_one(
    fake_urlopen,
):
    CisaKevSource().fetch(last_collected_at=datetime(2026, 9, 30, 10, 0, tzinfo=UTC))

    request = fake_urlopen.requests[0]
    assert request.get_header("If-modified-since") == "Wed, 30 Sep 2026 10:00:00 GMT"


def test_an_unmodified_catalog_returns_nothing(fake_urlopen):
    fake_urlopen.error = HTTPError(cisa_kev.CATALOG_URL, 304, "Not Modified", {}, None)

    assert CisaKevSource().fetch(datetime(2026, 9, 30, 10, 0, tzinfo=UTC)) is None


def test_another_http_error_is_raised(fake_urlopen):
    fake_urlopen.error = HTTPError(cisa_kev.CATALOG_URL, 503, "Unavailable", {}, None)

    with pytest.raises(HTTPError):
        CisaKevSource().fetch(last_collected_at=None)


def test_a_page_that_is_not_the_catalog_fails_the_collection(monkeypatch):
    maintenance_page = b"<html><body>Site under maintenance</body></html>"
    monkeypatch.setattr(http_download, "urlopen", FakeUrlopen(body=maintenance_page))

    with pytest.raises(ValueError, match="catalog without the columns"):
        CisaKevSource().fetch(last_collected_at=None)


COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = "automated_watch/cisa_kev/2026-10-05T093000Z.csv"


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
    assert newest.known_ransomware_campaign_use == "Unknown"
    assert (
        newest.vulnerability_name
        == "Apple Multiple Products Out-of-Bounds Write Vulnerability"
    )
    assert newest.short_description.startswith("Apple iOS, macOS, and iPadOS contain")


def test_a_catalog_without_the_expected_columns_is_refused():
    with pytest.raises(ValueError, match="dateAdded"):
        read_new_vulnerabilities(b"cveID,vendorProject\nCVE-2026-1234,Apple\n", None)


def test_a_catalog_without_the_ransomware_column_is_refused():
    header, first_row = EXTRACT.decode("utf-8").splitlines()[:2]
    catalog = f"{header}\n{first_row}\n".replace(
        "knownRansomwareCampaignUse", "otherColumn"
    )

    with pytest.raises(ValueError, match="knownRansomwareCampaignUse"):
        read_new_vulnerabilities(catalog.encode(), None)


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
        known_ransomware_campaign_use="Known",
    )

    item = convert_vulnerability(vulnerability, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "cisa_kev"
    assert item.kind == "vulnerability"
    assert item.source_item_id == "CVE-2026-86950"
    assert item.title == "Apple Multiple Products Out-of-Bounds Write Vulnerability"
    assert item.url == "https://nvd.nist.gov/vuln/detail/CVE-2026-86950"
    assert item.published_at == datetime(2026, 9, 29, tzinfo=UTC)
    assert item.summary == "An out-of-bounds write."
    assert item.cve == "CVE-2026-86950"
    assert item.vendor == "Apple"
    assert item.product == "Multiple Products"
    assert item.ransomware_use == "Known"


def test_a_ransomware_use_outside_known_and_unknown_is_refused_as_an_item():
    vulnerability = read_new_vulnerabilities(EXTRACT, last_collected_at=None)[0]

    with pytest.raises(ValidationError):
        convert_vulnerability(
            replace(vulnerability, known_ransomware_campaign_use="Yes"),
            COLLECTED_AT,
            RAW_FILE_PATH,
        )
