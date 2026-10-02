import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.github_most_starred import read_most_starred

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_most_starred_extract.json").read_bytes()


def response_with(**changes):
    response = json.loads(RECORDED_RESPONSE)
    response["items"][0].update(changes)
    return json.dumps(response).encode()


def test_a_recorded_response_gives_the_repositories_by_rank():
    repositories = read_most_starred(RECORDED_RESPONSE, expected_size=3)

    assert [(repository.rank, repository.full_name) for repository in repositories] == [
        (1, "codecrafters-io/build-your-own-x"),
        (2, "public-apis/public-apis"),
        (3, "freeCodeCamp/freeCodeCamp"),
    ]
    first = repositories[0]
    assert first.url == "https://github.com/codecrafters-io/build-your-own-x"
    assert first.stars == 551156
    assert first.created_at == datetime(2018, 5, 9, 12, 3, 18, tzinfo=UTC)
    assert "awesome-list" in first.topics
    assert first.description


def test_a_repository_without_description_keeps_an_empty_description():
    repositories = read_most_starred(response_with(description=None), expected_size=3)

    assert repositories[0].description is None


def test_an_incomplete_ranking_is_refused():
    response = json.loads(RECORDED_RESPONSE)
    response["incomplete_results"] = True

    with pytest.raises(ValueError, match="incomplete"):
        read_most_starred(json.dumps(response).encode(), expected_size=3)


def test_a_ranking_shorter_than_expected_is_refused():
    with pytest.raises(ValueError, match="3 repositories, expected 4"):
        read_most_starred(RECORDED_RESPONSE, expected_size=4)


def test_a_response_without_a_list_of_items_is_refused():
    with pytest.raises(ValueError, match="items"):
        read_most_starred(b'{"message": "Validation Failed"}', expected_size=3)


@pytest.mark.parametrize(
    "changes",
    [
        {"full_name": "../escape"},
        {"html_url": "https://evil.example.com/codecrafters-io/build-your-own-x"},
        {"stargazers_count": "many"},
        {"stargazers_count": True},
        {"topics": "awesome-list"},
        {"created_at": "2018-05-09T12:03:18"},
    ],
)
def test_an_invalid_repository_is_refused_with_its_rank(changes):
    with pytest.raises(ValueError, match="repository 1"):
        read_most_starred(response_with(**changes), expected_size=3)
