import logging
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from k_b import github_advisories_source
from k_b.collect import SOURCES
from k_b.github_advisories_source import GithubAdvisoriesSource

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_advisories_extract.json").read_bytes()
# The recorded advisories were published on 2026-05-13, 06-16 and 06-25.
BEFORE_ALL_ADVISORIES = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
BETWEEN_ADVISORIES = datetime(2026, 6, 20, 0, 0, tzinfo=UTC)
AFTER_ALL_ADVISORIES = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)
PACKAGES = ("langchain", "langchain-core")


@pytest.fixture
def fake_github_api(monkeypatch):
    class FakeGithubApi:
        response = RECORDED_RESPONSE
        paths = []

        def __call__(self, path):
            self.paths.append(path)
            return self.response

    fake = FakeGithubApi()
    monkeypatch.setattr(github_advisories_source, "get_from_github_api", fake)
    return fake


def query_of(path):
    split_path = urlsplit(path)
    assert split_path.path == "advisories"
    return {name: values[0] for name, values in parse_qs(split_path.query).items()}


def test_each_ecosystem_of_the_tracked_repositories_is_a_source_of_kb_collect():
    source_names = {source.name for source in SOURCES}

    assert {"github_advisories_pip", "github_advisories_npm"} <= source_names


def test_an_unknown_ecosystem_is_refused():
    with pytest.raises(ValueError, match="ecosystem"):
        GithubAdvisoriesSource("../escape", PACKAGES)


def test_a_first_collection_asks_for_the_reviewed_advisories_of_the_packages(fake_github_api):
    raw_response = GithubAdvisoriesSource("pip", PACKAGES).fetch(last_collected_at=None)

    assert raw_response == RECORDED_RESPONSE
    assert query_of(fake_github_api.paths[0]) == {
        "type": "reviewed",
        "ecosystem": "pip",
        "affects": "langchain,langchain-core",
        "per_page": "100",
    }


def test_a_later_collection_asks_from_the_day_before_the_last_one(fake_github_api):
    GithubAdvisoriesSource("pip", PACKAGES).fetch(last_collected_at=BETWEEN_ADVISORIES)

    assert query_of(fake_github_api.paths[0])["published"] == ">=2026-06-19"


def test_a_page_with_an_advisory_newer_than_the_last_collection_is_returned(fake_github_api):
    source = GithubAdvisoriesSource("pip", PACKAGES)

    assert source.fetch(last_collected_at=BETWEEN_ADVISORIES) == RECORDED_RESPONSE


def test_a_page_without_any_new_advisory_returns_nothing(fake_github_api):
    source = GithubAdvisoriesSource("pip", PACKAGES)

    assert source.fetch(last_collected_at=AFTER_ALL_ADVISORIES) is None


def test_an_empty_first_collection_returns_nothing(fake_github_api):
    fake_github_api.response = b"[]"

    assert GithubAdvisoriesSource("pip", PACKAGES).fetch(last_collected_at=None) is None


def test_a_full_page_of_new_advisories_warns_that_some_may_be_missing(
    fake_github_api, monkeypatch, caplog
):
    monkeypatch.setattr(github_advisories_source, "ADVISORIES_PER_PAGE", 3)

    with caplog.at_level(logging.WARNING):
        GithubAdvisoriesSource("pip", PACKAGES).fetch(last_collected_at=BEFORE_ALL_ADVISORIES)

    assert "github_advisories_pip" in caplog.text
    assert "may be missing" in caplog.text


def test_no_warning_when_the_page_reaches_back_to_the_last_collection(
    fake_github_api, monkeypatch, caplog
):
    monkeypatch.setattr(github_advisories_source, "ADVISORIES_PER_PAGE", 3)

    with caplog.at_level(logging.WARNING):
        GithubAdvisoriesSource("pip", PACKAGES).fetch(last_collected_at=BETWEEN_ADVISORIES)

    assert caplog.text == ""
