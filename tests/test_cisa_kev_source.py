import io
from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest

from k_b import cisa_kev_source
from k_b.cisa_kev_source import CisaKevSource

CATALOG = b"cveID,dateAdded\nCVE-2026-1234,2026-09-29\n"


class FakeResponse(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url


class FakeUrlopen:
    """Stands for urllib's urlopen: records the request, answers without any network."""

    def __init__(self, body=CATALOG, error=None, final_url=cisa_kev_source.CATALOG_URL):
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
    monkeypatch.setattr(cisa_kev_source, "urlopen", fake)
    return fake


def test_the_whole_catalog_is_returned_unchanged(fake_urlopen):
    assert CisaKevSource().fetch(last_collected_at=None) == CATALOG


def test_the_request_names_k_b_and_has_a_timeout(fake_urlopen):
    CisaKevSource().fetch(last_collected_at=None)

    request = fake_urlopen.requests[0]
    assert request.full_url == cisa_kev_source.CATALOG_URL
    assert request.get_header("User-agent").startswith("K-B")
    assert fake_urlopen.timeouts[0] > 0
    assert not request.has_header("If-modified-since")


def test_a_later_collection_asks_only_for_a_catalog_modified_since_the_last_one(fake_urlopen):
    CisaKevSource().fetch(last_collected_at=datetime(2026, 9, 30, 10, 0, tzinfo=UTC))

    request = fake_urlopen.requests[0]
    assert request.get_header("If-modified-since") == "Wed, 30 Sep 2026 10:00:00 GMT"


def test_an_unmodified_catalog_returns_nothing(fake_urlopen):
    fake_urlopen.error = HTTPError(cisa_kev_source.CATALOG_URL, 304, "Not Modified", {}, None)

    assert CisaKevSource().fetch(datetime(2026, 9, 30, 10, 0, tzinfo=UTC)) is None


def test_another_http_error_is_raised(fake_urlopen):
    fake_urlopen.error = HTTPError(cisa_kev_source.CATALOG_URL, 503, "Unavailable", {}, None)

    with pytest.raises(HTTPError):
        CisaKevSource().fetch(last_collected_at=None)


def test_a_catalog_larger_than_the_limit_is_refused(fake_urlopen, monkeypatch):
    monkeypatch.setattr(cisa_kev_source, "MAX_CATALOG_BYTES", len(CATALOG) - 1)

    with pytest.raises(ValueError, match="larger than"):
        CisaKevSource().fetch(last_collected_at=None)


@pytest.mark.parametrize(
    "final_url",
    [
        "http://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv",
        "https://www.cisa.gov.example.com/known_exploited_vulnerabilities.csv",
    ],
)
def test_a_redirection_away_from_https_cisa_gov_is_refused(fake_urlopen, final_url):
    fake_urlopen.final_url = final_url

    with pytest.raises(ValueError, match="redirected"):
        CisaKevSource().fetch(last_collected_at=None)
