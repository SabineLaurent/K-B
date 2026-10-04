import io
from urllib.error import HTTPError
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from k_b import http_download, tldr_source
from k_b.http_download import RedirectedOutsideError
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
        self.undated_days = set()
        self.failing_days = set()
        self.landing_url = "https://tldr.tech/ai"

    def __call__(self, request, timeout):
        self.requested_urls.append(request.full_url)
        day = date.fromisoformat(request.full_url.rsplit("/", 1)[1])
        if day.weekday() >= 5 or day in self.missing_days:
            # tldr.tech redirects a day without an edition to the landing page of the edition.
            return FakeResponse(LANDING_PAGE, self.landing_url)
        if day in self.failing_days:
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        if day in self.undated_days:
            return FakeResponse(LANDING_PAGE, request.full_url)
        if day in self.empty_days:
            empty_page = EMPTY_EDITION.replace(b"{day}", day.isoformat().encode())
            return FakeResponse(empty_page, request.full_url)
        return FakeResponse(edition_page(day), request.full_url)


class AllDays:
    def __contains__(self, day):
        return True


@pytest.fixture
def fake_tldr(monkeypatch):
    fake = FakeTldr()
    monkeypatch.setattr(http_download, "urlopen", fake)
    # Collections run on Thursday 2026-10-08: the weekend of 3-4 October is in the window.
    monkeypatch.setattr(tldr_source, "current_day", lambda: date(2026, 10, 8))
    return fake


@pytest.fixture
def pauses(monkeypatch):
    recorded = []
    monkeypatch.setattr(tldr_source, "sleep", recorded.append)
    return recorded


SINCE_OCTOBER_2 = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)


def test_the_tracked_editions_are_sources_of_kb_collect():
    source_names = {source.name for source in SOURCES}

    assert {f"tldr_{slug}" for slug in TRACKED_EDITIONS} <= source_names
    assert {"tldr_ai", "tldr_infosec", "tldr_dev"} <= source_names


def test_an_edition_name_that_is_not_a_slug_is_refused():
    with pytest.raises(ValueError, match="edition"):
        TldrSource("../ai", "AI")


def test_a_later_collection_reads_the_weekdays_from_the_last_one_to_today():
    # Last collection on Friday 2026-10-09, next one on Tuesday 2026-10-13.
    days = list_edition_days(datetime(2026, 10, 9, 8, 0, tzinfo=UTC), today=date(2026, 10, 13))

    assert days == [date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13)]


def test_a_first_collection_reads_the_weekdays_of_the_last_seven_days_and_today():
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
    pages = TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)

    assert pages
    for name, page in pages.items():
        assert page == edition_page(date.fromisoformat(name))
    assert all(url.startswith("https://tldr.tech/ai/") for url in fake_tldr.requested_urls)


THURSDAY_MORNING = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
TODAY = date(2026, 10, 8)


def test_the_edition_of_today_is_read_once_out(fake_tldr, pauses):
    pages = TldrSource("ai", "AI").fetch(last_collected_at=THURSDAY_MORNING)

    assert list(pages) == ["2026-10-08"]


@pytest.mark.parametrize("answer", ["missing_days", "failing_days", "undated_days"])
def test_an_edition_of_today_not_out_yet_is_no_error(fake_tldr, pauses, answer):
    # Redirected, not found or not an edition page: today's edition may simply be not out yet.
    setattr(fake_tldr, answer, {TODAY})
    fake_tldr.landing_url = "https://tldr.tech/somewhere-else"

    assert TldrSource("ai", "AI").fetch(last_collected_at=THURSDAY_MORNING) is None


def test_a_holiday_then_an_edition_of_today_not_out_yet_is_no_error(fake_tldr, pauses):
    fake_tldr.missing_days = {date(2026, 10, 7), TODAY}

    wednesday_morning = datetime(2026, 10, 7, 6, tzinfo=UTC)

    assert TldrSource("ai", "AI").fetch(last_collected_at=wednesday_morning) is None


def test_a_past_day_that_is_not_an_edition_page_is_still_refused(fake_tldr, pauses):
    fake_tldr.undated_days = {date(2026, 10, 7)}

    with pytest.raises(ValueError, match="structure"):
        TldrSource("ai", "AI").fetch(last_collected_at=datetime(2026, 10, 7, 6, tzinfo=UTC))


def test_a_holiday_redirected_to_the_landing_page_has_no_edition(fake_tldr, pauses):
    fake_tldr.missing_days = {date(2026, 10, 5)}

    pages = TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)

    assert "2026-10-05" not in pages
    assert "2026-10-02" in pages
    assert "2026-10-06" in pages


@pytest.mark.parametrize(
    "landing_url", ["https://tldr.tech/ai/", "https://tldr.tech/ai?ref=home", "https://TLDR.tech/ai"]
)
def test_the_landing_page_is_recognised_in_its_variants(fake_tldr, pauses, landing_url):
    fake_tldr.landing_url = landing_url
    fake_tldr.missing_days = {date(2026, 10, 5)}

    pages = TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)

    assert "2026-10-05" not in pages


@pytest.mark.parametrize(
    "landing_url",
    ["https://tldr.tech/dev", "https://tldr.tech/ai/subscribe", "http://tldr.tech/ai"],
)
def test_a_redirection_elsewhere_is_refused(fake_tldr, pauses, landing_url):
    fake_tldr.landing_url = landing_url
    fake_tldr.missing_days = {date(2026, 10, 5)}

    with pytest.raises(RedirectedOutsideError):
        TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)


def test_a_page_served_at_its_address_without_a_dated_title_is_refused(fake_tldr, pauses):
    # The fake site serves TLDR AI pages only: as tldr_dev they no longer look like an edition.
    with pytest.raises(ValueError, match="structure"):
        TldrSource("dev", "Dev").fetch(last_collected_at=SINCE_OCTOBER_2)


def test_the_site_is_paused_between_two_pages(fake_tldr, pauses):
    TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)

    assert len(pauses) == len(fake_tldr.requested_urls) - 1
    assert all(pause >= 1 for pause in pauses)


def test_an_edition_page_without_any_article_is_kept_among_others(fake_tldr, pauses):
    fake_tldr.empty_days = {date(2026, 10, 2)}

    pages = TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)

    assert b"<article" not in pages["2026-10-02"]
    assert "2026-10-06" in pages


def test_edition_pages_all_without_any_article_are_refused(fake_tldr, pauses):
    # Every edition page is empty: the article selectors have probably stopped matching.
    fake_tldr.empty_days = AllDays()

    with pytest.raises(ValueError, match="no article"):
        TldrSource("ai", "AI").fetch(last_collected_at=SINCE_OCTOBER_2)
