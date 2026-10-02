import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from k_b import github_most_starred_source
from k_b.collect import SOURCES
from k_b.github_most_starred_source import GithubMostStarredSource

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_most_starred_extract.json").read_bytes()


@pytest.fixture
def fake_github_api(monkeypatch):
    class FakeGithubApi:
        response = RECORDED_RESPONSE
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

    assert source.fetch(last_collected_at=None) == RECORDED_RESPONSE
    assert source.fetch(last_collected_at=None) == RECORDED_RESPONSE


def test_an_incomplete_ranking_is_not_written(fake_github_api):
    response = json.loads(RECORDED_RESPONSE)
    response["incomplete_results"] = True
    fake_github_api.response = json.dumps(response).encode()

    with pytest.raises(ValueError, match="incomplete"):
        GithubMostStarredSource().fetch(last_collected_at=None)
