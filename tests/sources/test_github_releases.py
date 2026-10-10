import json
import logging
import re
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.source_contract import list_sources
from k_b.source_kinds import SOURCE_KINDS
from k_b.sources import github_releases
from k_b.sources.github_releases import (
    GithubReleasesSource,
    Release,
    read_releases,
)
from k_b.sources.tracked_repositories import TRACKED_REPOSITORIES

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
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

    monkeypatch.setattr(
        github_releases, "get_from_github_api", fake_get_from_github_api
    )
    return paths


def test_each_tracked_repository_is_a_source_of_kb_collect():
    source_names = {source.name for source in list_sources(SOURCE_KINDS)}

    assert len(TRACKED_REPOSITORIES) == 4
    assert "github_releases_langchain_ai_langchain" in source_names
    assert "github_releases_run_llama_llama_index" in source_names
    assert all(
        GithubReleasesSource(repository.name).name in source_names
        for repository in TRACKED_REPOSITORIES
    )


@pytest.mark.parametrize(
    "repository",
    ["../escape", "./x", "x/.", "owner", "owner/repo/extra", "owner/re po"],
)
def test_a_repository_that_is_not_owner_slash_name_is_refused(repository):
    with pytest.raises(ValueError, match="repository"):
        GithubReleasesSource(repository)


def test_a_first_collection_returns_the_first_page_unchanged(requested_paths):
    source = GithubReleasesSource("anthropics/claude-code")

    assert source.fetch(last_collected_at=None) == RECORDED_RESPONSE
    assert requested_paths == ["repos/anthropics/claude-code/releases?per_page=100"]


@pytest.mark.parametrize("last_collected_at", [None, BETWEEN_RELEASES])
def test_a_page_of_another_repository_is_refused(requested_paths, last_collected_at):
    source = GithubReleasesSource("anthropics/another-repository")

    with pytest.raises(ValueError, match="anthropics/claude-code"):
        source.fetch(last_collected_at)


def test_the_case_of_the_repository_name_is_ignored(requested_paths):
    source = GithubReleasesSource("Anthropics/Claude-Code")

    assert source.fetch(last_collected_at=None) == RECORDED_RESPONSE


def test_a_page_with_a_release_newer_than_the_last_collection_is_returned(
    requested_paths,
):
    source = GithubReleasesSource("anthropics/claude-code")

    assert source.fetch(last_collected_at=BETWEEN_RELEASES) == RECORDED_RESPONSE


def test_a_page_without_any_new_release_returns_nothing(requested_paths):
    source = GithubReleasesSource("anthropics/claude-code")

    assert source.fetch(last_collected_at=AFTER_ALL_RELEASES) is None


def test_a_full_page_of_new_releases_warns_that_some_may_be_missing(
    requested_paths, monkeypatch, caplog
):
    monkeypatch.setattr(github_releases, "RELEASES_PER_PAGE", 3)

    with caplog.at_level(logging.WARNING):
        GithubReleasesSource("anthropics/claude-code").fetch(
            last_collected_at=BEFORE_ALL_RELEASES
        )

    assert "anthropics/claude-code" in caplog.text
    assert "may be missing" in caplog.text


@pytest.mark.parametrize("last_collected_at", [None, BETWEEN_RELEASES])
def test_no_warning_when_the_page_reaches_back_to_the_last_collection(
    requested_paths, monkeypatch, caplog, last_collected_at
):
    monkeypatch.setattr(github_releases, "RELEASES_PER_PAGE", 3)

    with caplog.at_level(logging.WARNING):
        GithubReleasesSource("anthropics/claude-code").fetch(last_collected_at)

    assert caplog.text == ""


def test_a_page_that_is_not_a_list_of_releases_fails_the_first_collection(monkeypatch):
    monkeypatch.setattr(
        github_releases,
        "get_from_github_api",
        lambda path: b'{"message": "Not Found"}',
    )

    with pytest.raises(ValueError, match="expected a list of releases"):
        GithubReleasesSource("anthropics/claude-code").fetch(last_collected_at=None)


REPOSITORY = "anthropics/claude-code"
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = (
    "automated_watch/github_releases_anthropics_claude_code/2026-10-05T093000Z.json"
)
PUBLISHED_AT = datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)


def release_payload(**changes):
    payload = json.loads(RECORDED_RESPONSE)[0]
    payload.update(changes)
    return json.dumps([payload]).encode()


def test_a_recorded_response_gives_one_release_per_entry_newest_first():
    releases = read_releases(RECORDED_RESPONSE)

    assert [release.tag_name for release in releases] == [
        "v2.1.287",
        "v2.1.286",
        "v2.1.285",
    ]
    newest = releases[0]
    assert newest.repository == REPOSITORY
    assert newest.release_id == 401174143
    assert newest.name == "v2.1.287"
    assert (
        newest.url == "https://github.com/anthropics/claude-code/releases/tag/v2.1.287"
    )
    assert newest.published_at == datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)
    assert newest.is_prerelease is False
    assert newest.body.startswith("## What's changed")


def test_the_author_login_is_not_kept():
    assert not any("author" in field.name for field in fields(Release))


def test_a_missing_name_or_body_stays_empty():
    release = read_releases(release_payload(name=None, body=None))[0]

    assert release.name is None
    assert release.body is None


def test_a_response_that_is_not_a_list_is_refused():
    with pytest.raises(ValueError, match="list"):
        read_releases(b'{"message": "Not Found"}')


@pytest.mark.parametrize(
    "changes",
    [
        {"id": None},
        {"id": "401174143"},
        {"id": True},
        {"tag_name": None},
        {"published_at": None},
        {"published_at": "yesterday"},
        {"published_at": "2026-10-01T18:00:22"},
        {"html_url": "https://evil.example.com/releases/tag/v2.1.287"},
        {"prerelease": "no"},
    ],
)
def test_an_invalid_release_is_refused_with_its_position(changes):
    with pytest.raises(ValueError, match="release 0"):
        read_releases(release_payload(**changes))


def test_the_repository_is_read_in_the_release_url():
    payload = release_payload(
        html_url="https://github.com/someone/untracked/releases/tag/v1"
    )

    assert read_releases(payload)[0].repository == "someone/untracked"


@pytest.mark.parametrize(
    "tag", ["release/1.0", "v1.0+build.5", "langchain-core==0.3.1", "v1%E2%80%A6"]
)
def test_a_release_url_with_any_path_character_in_its_tag_is_read(tag):
    payload = release_payload(html_url=f"https://github.com/a/b/releases/tag/{tag}")

    assert read_releases(payload)[0].repository == "a/b"


@pytest.mark.parametrize(
    "html_url",
    [
        None,
        "https://github.com/../x/releases/tag/v1",
        "https://github.com/a/./releases/tag/v1",
        "https://github.com/a/releases/tag/v1",
        "https://example.com/a/b/releases/tag/v1",
        # A browser resolves the dots: the link would open another repository than the title's.
        "https://github.com/a/b/releases/../../../evil/x/releases/tag/v9",
        "https://github.com/a/b/releases/tag/../../../../evil/x",
        "https://github.com/a/b/releases/tag/%2e%2e/%2E%2E/x",
        "https://github.com/a/b/releases/tag/v1?next=https://evil.example.com",
        "https://github.com/a/b/releases/tag/v1#fragment",
        "https://github.com/a/b/releases/tag/v1 ",
        "https://github.com/a/b/releases/tag/v1\n",
        "https://github.com/a/b/releases/tag/v1\u202e",
        "https://github.com/a/b/releases/v1",
        # Refused by the repository name rule alone: ... is not a dot segment.
        "https://github.com/a/.../releases/tag/v1",
        "https://github.com/a/b/releases/tag/.%2e/.%2e/x",
        "https://github.com/a/b/releases/tag/%2E./%2E./x",
        "https://github.com/a/b/releases/tag/..\\..\\x",
        "https://github.com/a/b/releases/tag/%",
        "https://github.com/a/b/releases/tag/v1%2",
    ],
)
def test_a_release_url_without_a_repository_is_refused_with_the_url(html_url):
    with pytest.raises(ValueError, match=re.escape(repr(html_url))):
        read_releases(release_payload(html_url=html_url))
