import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b import github_releases_source
from k_b.collect import SOURCES
from k_b.github_releases_source import GithubReleasesSource
from k_b.tracked_repositories import TRACKED_REPOSITORIES

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_releases_extract.json").read_bytes()
# The recorded releases were published on 2026-09-29, 09-30 and 10-01.
BEFORE_ALL_RELEASES = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
BETWEEN_RELEASES = datetime(2026, 9, 30, 0, 0, tzinfo=UTC)
AFTER_ALL_RELEASES = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def requested_paths(monkeypatch):
    paths = []

    def fake_get_from_github_api(path):
        paths.append(path)
        return RECORDED_RESPONSE

    monkeypatch.setattr(github_releases_source, "get_from_github_api", fake_get_from_github_api)
    return paths


def test_each_tracked_repository_is_a_source_of_kb_collect():
    source_names = {source.name for source in SOURCES}

    assert len(TRACKED_REPOSITORIES) == 4
    assert "github_releases_langchain_ai_langchain" in source_names
    assert "github_releases_run_llama_llama_index" in source_names
    assert all(
        GithubReleasesSource(repository.name).name in source_names
        for repository in TRACKED_REPOSITORIES
    )


@pytest.mark.parametrize("repository", ["../escape", "owner", "owner/repo/extra", "owner/re po"])
def test_a_repository_that_is_not_owner_slash_name_is_refused(repository):
    with pytest.raises(ValueError, match="repository"):
        GithubReleasesSource(repository)


def test_a_first_collection_returns_the_first_page_unchanged(requested_paths):
    source = GithubReleasesSource("anthropics/claude-code")

    assert source.fetch(last_collected_at=None) == RECORDED_RESPONSE
    assert requested_paths == ["repos/anthropics/claude-code/releases?per_page=100"]


def test_a_page_with_a_release_newer_than_the_last_collection_is_returned(requested_paths):
    source = GithubReleasesSource("anthropics/claude-code")

    assert source.fetch(last_collected_at=BETWEEN_RELEASES) == RECORDED_RESPONSE


def test_a_page_without_any_new_release_returns_nothing(requested_paths):
    source = GithubReleasesSource("anthropics/claude-code")

    assert source.fetch(last_collected_at=AFTER_ALL_RELEASES) is None


def test_a_full_page_of_new_releases_warns_that_some_may_be_missing(
    requested_paths, monkeypatch, caplog
):
    monkeypatch.setattr(github_releases_source, "RELEASES_PER_PAGE", 3)

    with caplog.at_level(logging.WARNING):
        GithubReleasesSource("anthropics/claude-code").fetch(last_collected_at=BEFORE_ALL_RELEASES)

    assert "anthropics/claude-code" in caplog.text
    assert "may be missing" in caplog.text


@pytest.mark.parametrize("last_collected_at", [None, BETWEEN_RELEASES])
def test_no_warning_when_the_page_reaches_back_to_the_last_collection(
    requested_paths, monkeypatch, caplog, last_collected_at
):
    monkeypatch.setattr(github_releases_source, "RELEASES_PER_PAGE", 3)

    with caplog.at_level(logging.WARNING):
        GithubReleasesSource("anthropics/claude-code").fetch(last_collected_at)

    assert caplog.text == ""
