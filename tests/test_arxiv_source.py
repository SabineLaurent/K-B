import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from k_b import arxiv_source
from k_b.arxiv_source import ArxivSource
from k_b.collect import SOURCES

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "arxiv_extract.xml").read_bytes()
EMPTY_FEED = (
    b'<feed xmlns="http://www.w3.org/2005/Atom" '
    b'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
    b"<opensearch:totalResults>0</opensearch:totalResults></feed>"
)


class FakeResponse(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url


class FakeUrlopen:
    """Stands for urllib's urlopen: records the request, answers without any network."""

    def __init__(self):
        self.body = RECORDED_RESPONSE
        self.final_url = None
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeResponse(self.body, self.final_url or request.full_url)

    def search_query(self):
        return parse_qs(urlsplit(self.requests[0].full_url).query)["search_query"][0]


@pytest.fixture
def fake_urlopen(monkeypatch):
    fake = FakeUrlopen()
    monkeypatch.setattr(arxiv_source, "urlopen", fake)
    return fake


def test_arxiv_is_a_source_of_kb_collect():
    assert "arxiv" in [source.name for source in SOURCES]


def test_the_response_is_returned_unchanged(fake_urlopen):
    assert ArxivSource().fetch(last_collected_at=None) == RECORDED_RESPONSE


def test_the_request_names_k_b_and_has_a_timeout(fake_urlopen):
    ArxivSource().fetch(last_collected_at=None)

    request = fake_urlopen.requests[0]
    assert request.full_url.startswith("https://export.arxiv.org/api/query?")
    assert request.get_header("User-agent").startswith("K-B")
    assert fake_urlopen.timeouts[0] > 0


def test_the_query_keeps_the_ai_security_papers_only(fake_urlopen):
    ArxivSource().fetch(last_collected_at=None)

    search_query = fake_urlopen.search_query()
    assert search_query.startswith("cat:cs.CR AND cat:cs.AI AND (abs:")
    assert 'abs:"prompt injection" OR abs:jailbreak OR' in search_query


def test_the_window_reaches_back_seven_days_before_the_last_collection(fake_urlopen):
    ArxivSource().fetch(last_collected_at=datetime(2026, 9, 30, 10, 5, tzinfo=UTC))

    assert "submittedDate:[202609231005 TO " in fake_urlopen.search_query()


def test_a_first_collection_takes_the_last_seven_days(fake_urlopen):
    ArxivSource().fetch(last_collected_at=None)

    window_start = datetime.strptime(
        fake_urlopen.search_query().split("submittedDate:[")[1][:12], "%Y%m%d%H%M"
    ).replace(tzinfo=UTC)
    assert abs(datetime.now(UTC) - timedelta(days=7) - window_start) < timedelta(minutes=2)


def test_a_window_without_any_paper_returns_nothing(fake_urlopen):
    fake_urlopen.body = EMPTY_FEED

    assert ArxivSource().fetch(last_collected_at=None) is None


def test_a_page_that_does_not_hold_every_result_is_refused(fake_urlopen):
    fake_urlopen.body = RECORDED_RESPONSE.replace(
        b"<opensearch:totalResults>3<", b"<opensearch:totalResults>2001<"
    )

    with pytest.raises(ValueError, match="2001"):
        ArxivSource().fetch(last_collected_at=None)


@pytest.mark.parametrize(
    "final_url", ["http://export.arxiv.org/api/query", "https://evil.example/api/query"]
)
def test_a_redirection_away_from_https_export_arxiv_org_is_refused(fake_urlopen, final_url):
    fake_urlopen.final_url = final_url

    with pytest.raises(ValueError, match="redirected"):
        ArxivSource().fetch(last_collected_at=None)


def test_a_response_larger_than_the_limit_is_refused(fake_urlopen, monkeypatch):
    monkeypatch.setattr(arxiv_source, "MAX_RESPONSE_BYTES", 10)

    with pytest.raises(ValueError, match="larger"):
        ArxivSource().fetch(last_collected_at=None)
