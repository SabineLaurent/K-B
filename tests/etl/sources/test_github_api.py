import pytest
from http_helpers import answer

from k_b.core.user_agent import USER_AGENT
from k_b.etl.source_contract import SourceStatusError
from k_b.etl.sources.github import api as github_api
from k_b.etl.sources.github.api import GithubPausedError, get_from_github_api

BODY = b'[{"tag_name": "v1.0.0"}]'
PATH = "repos/octocat/hello-world/releases?per_page=100"


@pytest.fixture
def network(fake_network, monkeypatch):
    fake_network.body = BODY
    monkeypatch.delenv(github_api.TOKEN_VARIABLE, raising=False)
    return fake_network


def test_the_response_is_returned_unchanged(network):
    assert get_from_github_api(PATH) == BODY


def test_the_request_follows_the_github_conventions_and_has_a_timeout(network):
    get_from_github_api(PATH)

    request = network.requests[0]
    assert str(request.url) == "https://api.github.com/" + PATH
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["Accept"] == "application/vnd.github+json"
    assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"
    assert request.extensions["timeout"]["read"] > 0


def test_without_a_token_the_request_is_anonymous(network):
    get_from_github_api(PATH)

    assert "Authorization" not in network.requests[0].headers


def test_the_token_is_sent_but_never_forwarded_to_a_redirection(network, monkeypatch):
    monkeypatch.setenv(github_api.TOKEN_VARIABLE, "test-token")
    network.answers = [answer(301, Location="https://api.github.com/repositories/1")]

    assert get_from_github_api(PATH) == BODY

    first, redirected = network.requests
    assert first.headers["Authorization"] == "Bearer test-token"
    assert str(redirected.url) == "https://api.github.com/repositories/1"
    assert "Authorization" not in redirected.headers


@pytest.mark.parametrize(
    ("status", "wait"), [(429, github_api.RATE_LIMITED_WAIT_SECONDS), (502, 5)]
)
def test_only_a_rate_limited_request_waits_the_minute_github_asks(
    network, no_wait_before_a_retry, status, wait
):
    network.answers = [answer(status)]

    assert get_from_github_api(PATH) == BODY
    assert no_wait_before_a_retry == [wait]
    assert github_api.RATE_LIMITED_WAIT_SECONDS == 60


# 2026-10-25T16:00:00Z, in epoch seconds.
RESET = 1792944000


def test_after_a_rate_limit_with_no_request_left_no_request_is_sent_until_its_reset(
    network, monkeypatch
):
    network.answers = [
        answer(403, x_ratelimit_remaining="0", x_ratelimit_reset=str(RESET))
    ]
    monkeypatch.setattr(github_api, "time", lambda: RESET - 3600)
    with pytest.raises(SourceStatusError):
        get_from_github_api(PATH)

    with pytest.raises(
        GithubPausedError, match="until 2026-10-25T16:00:00\\+00:00; none sent"
    ):
        get_from_github_api(PATH)
    assert len(network.requests) == 1

    monkeypatch.setattr(github_api, "time", lambda: RESET)
    assert get_from_github_api(PATH) == BODY
    assert len(network.requests) == 2
