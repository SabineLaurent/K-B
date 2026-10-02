import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from k_b import github_most_starred_source
from k_b.collect import SOURCES
from k_b.github_most_starred_source import GithubMostStarredSource

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_most_starred_extract.json").read_bytes()


def ranking_of(size):
    """A search response of size repositories, built by repeating the recorded ones."""
    response = json.loads(RECORDED_RESPONSE)
    recorded_items = response["items"]
    response["items"] = [recorded_items[rank % len(recorded_items)] for rank in range(size)]
    return json.dumps(response).encode()


FULL_RANKING = ranking_of(100)


@pytest.fixture
def fake_github_api(monkeypatch):
    class FakeGithubApi:
        response = FULL_RANKING
        paths = []

        def __call__(self, path):
            self.paths.append(path)
            return self.response

    fake = FakeGithubApi()
    monkeypatch.setattr(github_most_starred_source, "get_from_github_api", fake)
    return fake


def test_the_most_starred_repositories_are_a_source_of_kb_collect():
    assert "github_most_starred" in {source.name for source in SOURCES}


def test_the_request_asks_for_the_100_most_starred_repositories(fake_github_api):
    GithubMostStarredSource().fetch(last_collected_at=None)

    split_path = urlsplit(fake_github_api.paths[0])
    assert split_path.path == "search/repositories"
    assert {name: values[0] for name, values in parse_qs(split_path.query).items()} == {
        "q": "stars:>10000",
        "sort": "stars",
        "order": "desc",
        "per_page": "100",
    }


def test_every_collection_writes_a_snapshot_of_the_ranking(fake_github_api):
    source = GithubMostStarredSource()

    assert source.fetch(last_collected_at=None) == FULL_RANKING
    assert source.fetch(last_collected_at=None) == FULL_RANKING


def test_a_ranking_shorter_than_100_is_not_written(fake_github_api):
    fake_github_api.response = ranking_of(99)

    with pytest.raises(ValueError, match="99 repositories, expected 100"):
        GithubMostStarredSource().fetch(last_collected_at=None)


def test_an_incomplete_ranking_is_not_written(fake_github_api):
    response = json.loads(FULL_RANKING)
    response["incomplete_results"] = True
    fake_github_api.response = json.dumps(response).encode()

    with pytest.raises(ValueError, match="incomplete"):
        GithubMostStarredSource().fetch(last_collected_at=None)
