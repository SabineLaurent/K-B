import io

import pytest

from k_b import github_api
from k_b.github_api import get_from_github_api
from k_b.user_agent import USER_AGENT

BODY = b'[{"tag_name": "v1.0.0"}]'
PATH = "repos/octocat/hello-world/releases?per_page=100"


class FakeResponse(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url


class FakeUrlopen:
    """Stands for urllib's urlopen: records the request, answers without any network."""

    def __init__(self):
        self.body = BODY
        self.final_url = github_api.API_URL + PATH
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeResponse(self.body, self.final_url)


@pytest.fixture
def fake_urlopen(monkeypatch):
    fake = FakeUrlopen()
    monkeypatch.setattr(github_api, "urlopen", fake)
    monkeypatch.delenv(github_api.TOKEN_VARIABLE, raising=False)
    return fake


def test_the_response_is_returned_unchanged(fake_urlopen):
    assert get_from_github_api(PATH) == BODY


def test_the_request_follows_the_github_conventions_and_has_a_timeout(fake_urlopen):
    get_from_github_api(PATH)

    request = fake_urlopen.requests[0]
    assert request.full_url == "https://api.github.com/" + PATH
    assert request.get_header("User-agent") == USER_AGENT
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("X-github-api-version") == "2026-03-10"
    assert fake_urlopen.timeouts[0] > 0


def test_without_a_token_the_request_is_anonymous(fake_urlopen):
    get_from_github_api(PATH)

    assert not fake_urlopen.requests[0].has_header("Authorization")


def test_the_token_is_sent_but_never_forwarded_to_a_redirection(fake_urlopen, monkeypatch):
    monkeypatch.setenv(github_api.TOKEN_VARIABLE, "test-token")

    get_from_github_api(PATH)

    request = fake_urlopen.requests[0]
    assert request.get_header("Authorization") == "Bearer test-token"
    # urllib copies request.headers to a redirection, never the unredirected ones.
    assert "Authorization" not in request.headers


@pytest.mark.parametrize(
    "final_url",
    ["http://api.github.com/" + PATH, "https://api.github.com.example.com/" + PATH],
)
def test_a_redirection_away_from_https_api_github_com_is_refused(fake_urlopen, final_url):
    fake_urlopen.final_url = final_url

    with pytest.raises(ValueError, match="redirected"):
        get_from_github_api(PATH)


def test_a_response_larger_than_the_limit_is_refused(fake_urlopen, monkeypatch):
    monkeypatch.setattr(github_api, "MAX_RESPONSE_BYTES", len(BODY) - 1)

    with pytest.raises(ValueError, match="larger than"):
        get_from_github_api(PATH)
