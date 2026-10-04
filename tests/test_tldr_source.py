import io
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from k_b import http_download, tldr_source
from k_b.collect import SOURCES
from k_b.tldr_source import TRACKED_EDITIONS, TldrSource, list_edition_days

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_PAGE = (FIXTURES_DIR / "tldr_ai_extract.html").read_bytes()
LANDING_PAGE = b"<html><body><h1>Keep up with AI in 5 minutes</h1></body></html>"
EMPTY_EDITION = b"<html><body><h1>TLDR AI {day}</h1></body></html>"


def edition_page(day: date) -> bytes:
    return RECORDED_PAGE.replace(b"2026-10-01", day.isoformat().encode())


class FakeResponse(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url


class FakeTldr:
    """Stands for urllib's urlopen on tldr.tech: one edition page per weekday, no network."""

    def __init__(self):
        self.requested_urls = []
        self.missing_days = set()
        self.empty_days = set()

    def __call__(self, request, timeout):
        self.requested_urls.append(request.full_url)
        day = date.fromisoformat(request.full_url.rsplit("/", 1)[1])
        if day in self.empty_days:
            empty_page = EMPTY_EDITION.replace(b"{day}", day.isoformat().encode())
            return FakeResponse(empty_page, request.full_url)
        if day.weekday() >= 5 or day in self.missing_days:
            # tldr.tech redirects a day without an edition to the landing page.
            return FakeResponse(LANDING_PAGE, "https://tldr.tech/ai")
        return FakeResponse(edition_page(day), request.full_url)


@pytest.fixture
def fake_tldr(monkeypatch):
    fake = FakeTldr()
    monkeypatch.setattr(http_download, "urlopen", fake)
    return fake


@pytest.fixture
def pauses(monkeypatch):
    recorded = []
    monkeypatch.setattr(tldr_source, "sleep", recorded.append)
    return recorded


def test_the_tracked_editions_are_sources_of_kb_collect():
    source_names = {source.name for source in SOURCES}

    assert {f"tldr_{slug}" for slug in TRACKED_EDITIONS} <= source_names
    assert {"tldr_ai", "tldr_infosec", "tldr_dev"} <= source_names


def test_an_edition_name_that_is_not_a_slug_is_refused():
    with pytest.raises(ValueError, match="edition"):
        TldrSource("../ai", "AI")


def test_a_later_collection_reads_the_weekdays_since_the_day_before_the_last_one():
    # Last collection on Friday 2026-10-09, next one on Tuesday 2026-10-13.
    days = list_edition_days(datetime(2026, 10, 9, 8, 0, tzinfo=UTC), today=date(2026, 10, 13))

    assert days == [date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13)]


def test_a_first_collection_reads_the_weekdays_of_the_last_seven_days():
    days = list_edition_days(None, today=date(2026, 10, 13))

    assert days == [
        date(2026, 10, 6),
        date(2026, 10, 7),
        date(2026, 10, 8),
        date(2026, 10, 9),
        date(2026, 10, 12),
        date(2026, 10, 13),
    ]


def test_each_edition_page_is_returned_as_received_under_its_day(fake_tldr, pauses):
    yesterday = datetime.now(UTC) - timedelta(days=1)

    pages = TldrSource("ai", "AI").fetch(last_collected_at=yesterday)

    assert pages
    for name, page in pages.items():
        assert page == edition_page(date.fromisoformat(name))
    assert all(url.startswith("https://tldr.tech/ai/") for url in fake_tldr.requested_urls)


def test_a_day_redirected_to_the_landing_page_has_no_edition(fake_tldr, pauses):
    pages = TldrSource("ai", "AI").fetch(last_collected_at=datetime(2026, 10, 2, 8, tzinfo=UTC))

    assert "2026-10-03" not in pages
    assert "2026-10-04" not in pages
    assert "2026-10-02" in pages


def test_the_site_is_paused_between_two_pages(fake_tldr, pauses):
    TldrSource("ai", "AI").fetch(last_collected_at=datetime(2026, 10, 2, 8, tzinfo=UTC))

    assert len(pauses) == len(fake_tldr.requested_urls) - 1
    assert all(pause >= 1 for pause in pauses)


def test_a_page_of_another_edition_is_not_taken_for_this_one(fake_tldr, pauses):
    # The fake site answers TLDR AI pages only: none of them may be stored as tldr_dev.
    with pytest.raises(ValueError, match="no edition"):
        TldrSource("dev", "Dev").fetch(last_collected_at=datetime(2026, 10, 2, 8, tzinfo=UTC))


def test_an_edition_page_without_any_article_is_refused(fake_tldr, pauses):
    fake_tldr.empty_days = {date(2026, 10, 2)}

    with pytest.raises(ValueError, match="no article"):
        TldrSource("ai", "AI").fetch(last_collected_at=datetime(2026, 10, 2, 8, tzinfo=UTC))


def test_past_weekdays_without_any_edition_are_refused(fake_tldr, pauses, monkeypatch):
    # Every page looks like the landing page: the site has probably changed its structure.
    monkeypatch.setattr(fake_tldr, "missing_days", _AllDays())

    with pytest.raises(ValueError, match="no edition"):
        TldrSource("ai", "AI").fetch(last_collected_at=datetime(2026, 10, 2, 8, tzinfo=UTC))


def test_nothing_new_returns_nothing(fake_tldr, pauses, monkeypatch):
    # Only today is asked for and its edition is not out yet.
    monkeypatch.setattr(tldr_source, "list_edition_days", lambda last, today: [today])
    monkeypatch.setattr(fake_tldr, "missing_days", _AllDays())

    assert TldrSource("ai", "AI").fetch(last_collected_at=datetime.now(UTC)) is None


class _AllDays:
    def __contains__(self, day):
        return True
