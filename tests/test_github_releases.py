import json
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.github_releases import Release, convert_release, read_releases

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_releases_extract.json").read_bytes()
REPOSITORY = "anthropics/claude-code"
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = (
    "automation/github_releases_anthropics_claude_code/2026-10-05T093000Z.json"
)
PUBLISHED_AT = datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)


def release_payload(**changes):
    payload = json.loads(RECORDED_RESPONSE)[0]
    payload.update(changes)
    return json.dumps([payload]).encode()


def test_a_recorded_response_gives_one_release_per_entry_newest_first():
    releases = read_releases(RECORDED_RESPONSE, REPOSITORY)

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
    release = read_releases(release_payload(name=None, body=None), REPOSITORY)[0]

    assert release.name is None
    assert release.body is None


def test_a_response_that_is_not_a_list_is_refused():
    with pytest.raises(ValueError, match="list"):
        read_releases(b'{"message": "Not Found"}', REPOSITORY)


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
        read_releases(release_payload(**changes), REPOSITORY)


def test_a_release_is_identified_by_its_release_id():
    release = Release(
        repository="anthropics/claude-code",
        release_id=401174143,
        tag_name="v2.1.287",
        name=None,
        url="https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
        published_at=PUBLISHED_AT,
        is_prerelease=False,
        body="## What's changed",
    )

    item = convert_release(release, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "github"
    assert item.source_item_id == "401174143"
    assert item.title == "anthropics/claude-code v2.1.287"
    assert item.url == "https://github.com/anthropics/claude-code/releases/tag/v2.1.287"
    assert item.published_at == PUBLISHED_AT
    assert item.summary == "## What's changed"
    assert item.repository_name is None


def test_a_named_release_is_titled_by_its_name():
    release = Release(
        repository="langchain-ai/langgraph",
        release_id=1,
        tag_name="0.6.0",
        name="LangGraph 0.6",
        url="https://github.com/langchain-ai/langgraph/releases/tag/0.6.0",
        published_at=PUBLISHED_AT,
        is_prerelease=False,
        body=None,
    )

    item = convert_release(release, COLLECTED_AT, RAW_FILE_PATH)

    assert item.title == "langchain-ai/langgraph LangGraph 0.6"
    assert item.summary is None
