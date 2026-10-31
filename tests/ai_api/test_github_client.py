"""The reading of the sheet of a candidate on GitHub, on a simulated GitHub serving a real answer
(tests/fixtures/github_repository_extract.json): no test calls GitHub."""

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from k_b.ai_api.connectors.github_client import (
    GithubError,
    GithubReading,
    build_github_client,
    read_repository,
)
from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.deadline import Deadline
from k_b.core.config import (
    GITHUB_MAX_REQUESTS_PER_REPORT,
    MAX_GITHUB_REPOSITORY_BYTES,
    MAX_GITHUB_RETRY_AFTER_SECONDS,
)
from k_b.core.github_api import API_VERSION
from k_b.core.user_agent import USER_AGENT

FIXTURE = Path(__file__).parent.parent / "fixtures" / "github_repository_extract.json"
ANSWER = json.loads(FIXTURE.read_bytes())
REPOSITORY_ID = ANSWER["id"]
REPOSITORY_NAME = ANSWER["full_name"]
# Made for the test: never a real token.
TOKEN = f"github_pat_{secrets.token_hex(41)}"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
NOW_SECONDS = int(NOW.timestamp())


class SimulatedGithub:
    """Answers in turn, the last one again, keeping each request."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        answer = self.answers[min(len(self.requests), len(self.answers)) - 1]
        return answer(request) if callable(answer) else answer


def answer(status=200, body=None, headers=None):
    content = FIXTURE.read_bytes() if body is None else json.dumps(body).encode()
    return httpx2.Response(status, content=content, headers=headers)


def edit(**fields):
    return answer(body=ANSWER | fields)


def start_reading(github, deadline=None):
    http_client = build_github_client(
        GithubSettings(token=SecretStr(TOKEN)), httpx2.MockTransport(github.handle)
    )
    return GithubReading(http_client, deadline or Deadline.after(60), NOW)


def read(github, reading=None):
    return read_repository(
        reading or start_reading(github), REPOSITORY_ID, REPOSITORY_NAME
    )


def read_error(github, reading=None):
    with pytest.raises(GithubError) as raised:
        read(github, reading)
    return raised.value


def test_the_card_is_read_from_a_real_answer_with_the_headers_of_k_b():
    github = SimulatedGithub(answer())

    card = read(github)

    assert card.repository_id == REPOSITORY_ID
    assert card.license == "MIT"
    assert card.created_at == datetime(2018, 12, 8, 8, 21, 47, tzinfo=UTC)
    assert card.language == "Python"
    assert card.topics == tuple(ANSWER["topics"])
    assert card.stars_total == ANSWER["stargazers_count"]
    [request] = github.requests
    assert str(request.url) == "https://api.github.com/repos/fastapi/fastapi"
    assert request.method == "GET"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Accept"] == "application/vnd.github+json"
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["X-GitHub-Api-Version"] == API_VERSION


@pytest.mark.parametrize(
    "license",
    [None, {"key": "other", "spdx_id": "NOASSERTION"}, {"key": "x", "spdx_id": None}],
    ids=["none", "noassertion", "spdx-null"],
)
def test_a_license_github_does_not_recognize_is_none(license):
    assert read(SimulatedGithub(edit(license=license))).license is None


def test_a_language_null_is_none():
    assert read(SimulatedGithub(edit(language=None))).language is None


def test_another_id_leaves_the_candidate_out():
    assert read(SimulatedGithub(edit(id=REPOSITORY_ID + 1))) == "id_mismatch"


@pytest.mark.parametrize("status", [301, 302, 307])
def test_a_redirection_is_not_followed_and_leaves_the_candidate_out(status):
    github = SimulatedGithub(
        httpx2.Response(
            status, headers={"Location": "https://api.github.com/repositories/1"}
        )
    )

    assert read(github) == "moved"
    assert len(github.requests) == 1


@pytest.mark.parametrize(
    ("status", "reason"),
    [(404, "not_found"), (410, "not_found"), (451, "unavailable_for_legal_reasons")],
)
def test_a_repository_gone_or_blocked_is_left_out(status, reason):
    assert read(SimulatedGithub(answer(status, {"message": "Not Found"}))) == reason


def test_a_token_refused_is_github_unauthorized():
    error = read_error(SimulatedGithub(answer(401, {"message": "Bad credentials"})))

    assert error.state == "github_unauthorized"
    assert error.http_status == 401
    assert TOKEN not in str(error)


@pytest.mark.parametrize(
    ("headers", "message", "retry_after"),
    [
        (
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(NOW_SECONDS + 600)},
            "API rate limit exceeded",
            600,
        ),
        ({"x-ratelimit-remaining": "0"}, "", 60),
        (
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(NOW_SECONDS + 5)},
            "",
            60,
        ),
        (
            {
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": str(NOW_SECONDS + 7_200),
            },
            "",
            MAX_GITHUB_RETRY_AFTER_SECONDS,
        ),
        ({"retry-after": "120"}, "", 120),
        ({"retry-after": "9" * 12}, "", MAX_GITHUB_RETRY_AFTER_SECONDS),
        (
            # A reset with requests left is not a pause GitHub asks.
            {
                "x-ratelimit-remaining": "12",
                "x-ratelimit-reset": str(NOW_SECONDS + 600),
            },
            "You have exceeded a secondary rate limit",
            60,
        ),
        ({}, "You have triggered an ABUSE detection mechanism", 60),
    ],
    ids=[
        "primary",
        "primary-without-reset",
        "reset-in-5-seconds",
        "reset-beyond-an-hour",
        "retry-after",
        "retry-after-too-long",
        "secondary-message",
        "abuse-message",
    ],
)
def test_a_403_of_rate_limit_stops_with_its_retry_after(headers, message, retry_after):
    error = read_error(SimulatedGithub(answer(403, {"message": message}, headers)))

    assert error.state == "github_rate_limited"
    assert error.retry_after_seconds == retry_after


@pytest.mark.parametrize("headers", [{}, {"retry-after": "30"}])
def test_any_429_stops_as_a_rate_limit(headers):
    error = read_error(SimulatedGithub(answer(429, {"message": "slow"}, headers)))

    assert error.state == "github_rate_limited"
    assert error.retry_after_seconds == int(headers.get("retry-after", 60))


def test_a_403_alone_leaves_the_candidate_out_and_the_third_stops_the_reading():
    github = SimulatedGithub(answer(403, {"message": "Repository access blocked"}))
    reading = start_reading(github)

    assert read(github, reading) == "forbidden"
    assert read(github, reading) == "forbidden"
    error = read_error(github, reading)

    assert error.state == "github_forbidden"
    assert error.retry_after_seconds is None


def test_a_server_error_is_retried_once_without_wait():
    github = SimulatedGithub(answer(502, {}), answer())

    assert read(github).repository_id == REPOSITORY_ID
    assert len(github.requests) == 2


def test_two_server_errors_are_github_unavailable():
    github = SimulatedGithub(answer(503, {}))

    assert read_error(github).state == "github_unavailable"
    assert len(github.requests) == 2


@pytest.mark.parametrize("status", [204, 400, 405, 409, 422])
def test_any_other_status_is_an_invalid_response(status):
    assert read_error(SimulatedGithub(answer(status, {}))).state == (
        "github_invalid_response"
    )


def test_the_requests_of_a_report_stop_at_the_budget():
    github = SimulatedGithub(answer())
    reading = start_reading(github)
    for _ in range(GITHUB_MAX_REQUESTS_PER_REPORT):
        read(github, reading)

    error = read_error(github, reading)

    assert error.state == "github_unavailable"
    assert len(github.requests) == GITHUB_MAX_REQUESTS_PER_REPORT


def test_a_retry_counts_in_the_budget():
    github = SimulatedGithub(answer(500, {}))
    reading = start_reading(github)
    reading.requests = GITHUB_MAX_REQUESTS_PER_REPORT - 1

    assert read_error(github, reading).state == "github_unavailable"
    assert len(github.requests) == 1


def test_a_body_announced_beyond_the_bound_is_refused():
    github = SimulatedGithub(
        httpx2.Response(
            200,
            content=b"{}",
            headers={"Content-Length": str(MAX_GITHUB_REPOSITORY_BYTES + 1)},
        )
    )

    assert read_error(github).state == "github_invalid_response"


def test_a_body_beyond_the_bound_without_its_length_is_refused():
    def stream():
        yield b" " * MAX_GITHUB_REPOSITORY_BYTES
        yield FIXTURE.read_bytes()

    github = SimulatedGithub(httpx2.Response(200, content=stream()))

    assert read_error(github).state == "github_invalid_response"


@pytest.mark.parametrize(
    "fields",
    [
        {"id": 0},
        {"id": str(REPOSITORY_ID)},
        {"stargazers_count": -1},
        {"created_at": "2018-12-08T08:21:47"},
        {"language": "Py\x1bthon"},
        {"language": ""},
        {"topics": ["Python"]},
        {"topics": ["a" * 51]},
        {"topics": ["python"] * 101},
        {"license": {"spdx_id": "MIT License"}},
        {"license": "MIT"},
    ],
    ids=[
        "id-zero",
        "id-text",
        "stars-negative",
        "created-at-naive",
        "language-control",
        "language-empty",
        "topic-uppercase",
        "topic-too-long",
        "too-many-topics",
        "license-not-spdx",
        "license-text",
    ],
)
def test_an_answer_out_of_its_schema_is_an_invalid_response(fields):
    assert read_error(SimulatedGithub(edit(**fields))).state == (
        "github_invalid_response"
    )


def test_a_body_not_json_is_an_invalid_response():
    github = SimulatedGithub(httpx2.Response(200, content=b"<html>"))

    assert read_error(github).state == "github_invalid_response"


def test_a_timeout_is_github_timeout():
    def time_out(request):
        raise httpx2.ReadTimeout("timeout of the test", request=request)

    assert read_error(SimulatedGithub(time_out)).state == "github_timeout"


def test_a_connection_refused_is_github_unavailable():
    def refuse(request):
        raise httpx2.ConnectError("refused by the test", request=request)

    assert read_error(SimulatedGithub(refuse)).state == "github_unavailable"


def test_a_deadline_passed_sends_nothing():
    github = SimulatedGithub(answer())
    reading = start_reading(github, Deadline.after(0, clock=lambda: 0.0))

    assert read_error(github, reading).state == "github_timeout"
    assert github.requests == []
