import logging
from datetime import UTC, date, datetime
from urllib.error import HTTPError

import pytest

from k_b import tldr_source
from k_b.collect import SOURCES
from k_b.http_download import RedirectedOutsideError
from k_b.tldr_source import TldrSource

# Sunday: the window of a collection on this day holds a weekend.
TODAY = date(2026, 10, 4)
EDITION_PAGE = b"<html><h1>TLDR AI 2026-10-02</h1></html>"


class FakeDownload:
    """Stands for download: answers each url as given, records the urls asked."""

    def __init__(self, answers):
        self.answers = answers
        self.urls = []

    def __call__(self, url, trusted_url_prefix, max_bytes):
        self.urls.append(url)
        answer = self.answers.get(url, RedirectedOutsideError(url, "https://tldr.tech/ai"))
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def fake_download(monkeypatch):
    fake = FakeDownload({})
    monkeypatch.setattr(tldr_source, "download", fake)
    monkeypatch.setattr(tldr_source, "current_day", lambda: TODAY)
    monkeypatch.setattr(tldr_source, "sleep", lambda seconds: None)
    return fake


def test_each_tracked_edition_is_a_source_of_kb_collect():
    names = [source.name for source in SOURCES]
    assert {"tldr_ai", "tldr_infosec", "tldr_dev"} <= set(names)


def test_the_page_of_a_day_is_asked_at_its_edition_and_date_url(fake_download):
    TldrSource("ai").fetch(datetime(2026, 10, 4, 8, 0, tzinfo=UTC))

    assert fake_download.urls == ["https://tldr.tech/ai/2026-10-04"]


def test_every_day_from_the_last_collection_day_to_today_is_asked(fake_download):
    TldrSource("ai").fetch(datetime(2026, 10, 2, 18, 0, tzinfo=UTC))

    assert fake_download.urls == [
        "https://tldr.tech/ai/2026-10-02",
        "https://tldr.tech/ai/2026-10-03",
        "https://tldr.tech/ai/2026-10-04",
    ]


def test_a_first_collection_asks_the_seven_days_before_today_and_today(fake_download):
    TldrSource("ai").fetch(last_collected_at=None)

    assert fake_download.urls[0] == "https://tldr.tech/ai/2026-09-27"
    assert len(fake_download.urls) == 8


def test_an_edition_page_is_returned_unchanged_under_its_day(fake_download):
    fake_download.answers["https://tldr.tech/ai/2026-10-02"] = EDITION_PAGE

    pages = TldrSource("ai").fetch(datetime(2026, 10, 2, 6, 0, tzinfo=UTC))

    assert pages == {"2026-10-02": EDITION_PAGE}


@pytest.mark.parametrize("landing_url", ["https://tldr.tech/ai", "https://tldr.tech/ai/"])
def test_a_day_redirected_to_the_edition_landing_page_is_logged_and_skipped(
    fake_download, caplog, landing_url
):
    fake_download.answers["https://tldr.tech/ai/2026-10-02"] = EDITION_PAGE
    fake_download.answers["https://tldr.tech/ai/2026-10-03"] = RedirectedOutsideError(
        "https://tldr.tech/ai/2026-10-03", landing_url
    )
    caplog.set_level(logging.INFO, logger="k_b.tldr_source")

    pages = TldrSource("ai").fetch(datetime(2026, 10, 2, 6, 0, tzinfo=UTC))

    assert list(pages) == ["2026-10-02"]
    assert f"tldr_ai 2026-10-03: no edition page, redirected to {landing_url}" in caplog.text


def test_a_redirection_elsewhere_than_the_edition_landing_page_is_raised(fake_download):
    fake_download.answers["https://tldr.tech/ai/2026-10-04"] = RedirectedOutsideError(
        "https://tldr.tech/ai/2026-10-04", "https://tldr.tech/login"
    )

    with pytest.raises(RedirectedOutsideError, match="https://tldr.tech/login"):
        TldrSource("ai").fetch(datetime(2026, 10, 4, 6, 0, tzinfo=UTC))


def test_no_edition_page_in_the_window_returns_none(fake_download):
    assert TldrSource("ai").fetch(datetime(2026, 10, 2, 6, 0, tzinfo=UTC)) is None


def test_an_http_error_is_raised(fake_download):
    url = "https://tldr.tech/ai/2026-10-04"
    fake_download.answers[url] = HTTPError(url, 500, "Internal Server Error", {}, None)

    with pytest.raises(HTTPError):
        TldrSource("ai").fetch(datetime(2026, 10, 4, 6, 0, tzinfo=UTC))


@pytest.mark.parametrize("edition", ["", "AI", "ai/../x", "ai?x=1"])
def test_an_edition_that_is_not_a_slug_is_refused(edition):
    with pytest.raises(ValueError, match="not a TLDR edition slug"):
        TldrSource(edition)
