import logging
from datetime import UTC, date, datetime
from urllib.error import HTTPError, URLError

import pytest

from k_b import tldr_source
from k_b.http_download import RedirectedOutsideError
from k_b.source import list_sources
from k_b.source_kinds import SOURCE_KINDS
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
        answer = self.answers.get(
            url, RedirectedOutsideError(url, "https://tldr.tech/ai")
        )
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
    names = [source.name for source in list_sources(SOURCE_KINDS)]
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


def test_an_edition_page_is_returned_unchanged_under_its_day_and_logged(
    fake_download, caplog
):
    fake_download.answers["https://tldr.tech/ai/2026-10-02"] = EDITION_PAGE
    caplog.set_level(logging.INFO, logger="k_b.tldr_source")

    pages = TldrSource("ai").fetch(datetime(2026, 10, 2, 6, 0, tzinfo=UTC))

    assert pages == {"2026-10-02": EDITION_PAGE}
    assert f"tldr_ai 2026-10-02: edition page, {len(EDITION_PAGE)} bytes" in caplog.text


@pytest.mark.parametrize(
    "landing_url", ["https://tldr.tech/ai", "https://tldr.tech/ai/"]
)
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
    assert (
        f"tldr_ai 2026-10-03: no edition page, redirected to {landing_url}"
        in caplog.text
    )


def test_a_redirection_elsewhere_than_the_edition_landing_page_is_logged_and_raised(
    fake_download, caplog
):
    fake_download.answers["https://tldr.tech/ai/2026-10-04"] = RedirectedOutsideError(
        "https://tldr.tech/ai/2026-10-04", "https://tldr.tech/login"
    )

    with pytest.raises(RedirectedOutsideError, match="https://tldr.tech/login"):
        TldrSource("ai").fetch(datetime(2026, 10, 4, 6, 0, tzinfo=UTC))
    assert (
        "tldr_ai 2026-10-04: response redirected to https://tldr.tech/login, outside "
        "https://tldr.tech/ai/2026-10-04, refused, from https://tldr.tech/ai/2026-10-04"
    ) in caplog.text


def test_no_edition_page_in_the_window_returns_none_and_is_logged(
    fake_download, caplog
):
    caplog.set_level(logging.INFO, logger="k_b.tldr_source")

    assert TldrSource("ai").fetch(datetime(2026, 10, 2, 6, 0, tzinfo=UTC)) is None
    assert "tldr_ai: no edition page from 2026-10-02 to 2026-10-04" in caplog.text


@pytest.mark.parametrize(
    ("error", "observed"),
    [
        (
            HTTPError(
                "https://tldr.tech/ai/2026-10-04",
                500,
                "Internal Server Error",
                {},
                None,
            ),
            "HTTP Error 500: Internal Server Error",
        ),
        (URLError("timed out"), "<urlopen error timed out>"),
        (
            ValueError("response larger than 1048576 bytes, refused"),
            "response larger than",
        ),
    ],
)
def test_an_error_is_logged_with_its_day_and_url_then_raised(
    fake_download, caplog, error, observed
):
    fake_download.answers["https://tldr.tech/ai/2026-10-04"] = error

    with pytest.raises(type(error)):
        TldrSource("ai").fetch(datetime(2026, 10, 4, 6, 0, tzinfo=UTC))
    assert f"tldr_ai 2026-10-04: {observed}" in caplog.text
    assert "from https://tldr.tech/ai/2026-10-04" in caplog.text


@pytest.mark.parametrize("edition", ["", "AI", "ai/../x", "ai?x=1"])
def test_an_edition_that_is_not_a_slug_is_refused(edition):
    with pytest.raises(ValueError, match="not a TLDR edition slug"):
        TldrSource(edition)


def test_a_last_collection_after_today_is_refused_with_both_days(fake_download):
    with pytest.raises(
        ValueError, match="last collection day 2026-10-05 is after today 2026-10-04"
    ):
        TldrSource("ai").fetch(datetime(2026, 10, 5, 6, 0, tzinfo=UTC))
    assert fake_download.urls == []
