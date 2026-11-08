"""The reading of the sheet and of the README of a repository on GitHub, on a simulated GitHub
serving a real answer (tests/fixtures/github_repository_extract.json) and a README in the form of
a real one (tests/fixtures/github_readme_extract.md): no test calls GitHub."""

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
    Readme,
    build_github_client,
    read_readme,
    read_repository,
    to_repository_path,
)
from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.repository_texts import RAW_CUT_FACTOR, clean_repository_text
from k_b.core.config import (
    GITHUB_MAX_FORBIDDEN_PER_REPORT,
    GITHUB_MAX_REQUESTS_PER_REPORT,
    MAX_GITHUB_README_BYTES,
    MAX_GITHUB_REPOSITORY_BYTES,
    MAX_GITHUB_RETRY_AFTER_SECONDS,
    MAX_README_CHARS_FOR_WRITING,
)
from k_b.core.github_api import API_VERSION
from k_b.core.user_agent import USER_AGENT

FIXTURE = Path(__file__).parent.parent / "fixtures" / "github_repository_extract.json"
README_FIXTURE = Path(__file__).parent.parent / "fixtures" / "github_readme_extract.md"
README_MEDIA_TYPE = "application/vnd.github.raw+json"
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


@pytest.mark.parametrize("language", ["C#", "C++", "F*", "Ren'Py", "Visual Basic .NET"])
def test_a_language_with_punctuation_is_read(language):
    assert read(SimulatedGithub(edit(language=language))).language == language


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
        {"language": "Py" + chr(0x202E) + "thon"},
        {"language": "Py" + chr(0x200B) + "thon"},
        {"language": "Py" + chr(0x2028) + "thon"},
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
        "language-format",
        "language-zero-width",
        "language-line-separator",
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


def readme_answer(status=200, content=None, headers=None):
    body = README_FIXTURE.read_bytes() if content is None else content
    return httpx2.Response(
        status,
        content=body,
        headers={"Content-Type": "application/vnd.github.raw+json"} | (headers or {}),
    )


def read_the_readme(github, reading=None):
    return read_readme(reading or start_reading(github), REPOSITORY_NAME)


def read_the_readme_error(github, reading=None):
    with pytest.raises(GithubError) as raised:
        read_the_readme(github, reading)
    return raised.value


def test_a_readme_is_read_raw_with_the_headers_of_k_b():
    github = SimulatedGithub(readme_answer())

    readme = read_the_readme(github)

    assert readme == Readme(README_FIXTURE.read_text())
    [request] = github.requests
    assert str(request.url) == "https://api.github.com/repos/fastapi/fastapi/readme"
    assert request.headers["Accept"] == README_MEDIA_TYPE
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["X-GitHub-Api-Version"] == API_VERSION


def test_the_sheet_keeps_its_accept_after_a_readme():
    github = SimulatedGithub(readme_answer(), answer())
    reading = start_reading(github)

    read_the_readme(github, reading)
    read(github, reading)

    assert github.requests[1].headers["Accept"] == "application/vnd.github+json"


@pytest.mark.parametrize(
    ("content_type", "is_read"),
    [
        ("application/vnd.github.raw+json", True),
        ("application/vnd.github.raw+json; charset=utf-8", True),
        ("text/plain; charset=utf-8", True),
        ("application/json", False),
        ("application/json; charset=utf-8", False),
        ("Application/JSON ; charset=utf-8", False),
    ],
)
def test_a_readme_served_as_json_is_refused_by_its_exact_media_type(
    content_type, is_read
):
    github = SimulatedGithub(readme_answer(headers={"Content-Type": content_type}))

    if is_read:
        assert isinstance(read_the_readme(github), Readme)
    else:
        assert read_the_readme_error(github).state == "github_invalid_response"


def test_a_readme_keeps_its_head_up_to_its_bound_the_rest_unread():
    pieces = CountedPieces(b"a" * MAX_GITHUB_README_BYTES, b"b" * 10, b"c" * 10)
    github = SimulatedGithub(readme_answer(content=pieces))

    readme = read_the_readme(github)

    assert readme == Readme("a" * MAX_GITHUB_README_BYTES)
    assert pieces.pieces_read == 2


def test_a_readme_announced_beyond_the_bound_of_a_sheet_is_still_read():
    github = SimulatedGithub(
        readme_answer(
            content=iter([b"a" * 100]),
            headers={"Content-Length": str(MAX_GITHUB_REPOSITORY_BYTES + 1)},
        )
    )

    assert read_the_readme(github) == Readme("a" * 100)


def test_the_head_of_a_readme_holds_more_than_the_raw_cut_of_the_cleaning():
    # 4 bytes at most per character in UTF-8: the head always reaches the raw cut, which the
    # cleaning cuts again, the word it breaks removed.
    assert MAX_GITHUB_README_BYTES // 4 > RAW_CUT_FACTOR * MAX_README_CHARS_FOR_WRITING


def test_a_readme_cut_in_a_character_leaves_no_broken_character_to_the_model():
    emoji = chr(0x1F680).encode()
    # Cut at the bound in the middle of an emoji, after a word: the cut word and the broken
    # character go.
    content = (b"word " + emoji * MAX_GITHUB_README_BYTES)[
        : MAX_GITHUB_README_BYTES + 2
    ]
    github = SimulatedGithub(readme_answer(content=iter([content])))

    readme = read_the_readme(github)
    cleaned = clean_repository_text(readme.text, MAX_README_CHARS_FOR_WRITING)

    assert readme.text.endswith(chr(0xFFFD))
    assert chr(0xFFFD) not in cleaned.text
    assert cleaned.is_cut
    assert len(cleaned.text) <= MAX_README_CHARS_FOR_WRITING


@pytest.mark.parametrize(
    ("status", "missing"),
    [(404, "absent"), (410, "absent"), (451, "refused"), (301, "refused")],
)
def test_a_readme_github_does_not_give_is_absent_or_refused(status, missing):
    github = SimulatedGithub(
        readme_answer(status, b'{"message": "Not Found"}', {"Location": "x"})
    )

    assert read_the_readme(github) == missing
    assert len(github.requests) == 1


def test_a_403_alone_on_a_readme_is_refused_and_counts_among_the_refusals():
    github = SimulatedGithub(readme_answer(403, b'{"message": "Access blocked"}'))
    reading = start_reading(github)
    reading.forbidden = GITHUB_MAX_FORBIDDEN_PER_REPORT - 2

    assert read_the_readme(github, reading) == "refused"
    assert read_the_readme_error(github, reading).state == "github_forbidden"


def test_a_403_of_rate_limit_on_a_readme_is_read_beyond_the_head():
    # The head is for a 200 only: a long message would be cut, and no longer read as a limit.
    message = json.dumps(
        {"message": "API rate limit exceeded", "documentation_url": "a" * 70_000}
    ).encode()
    github = SimulatedGithub(readme_answer(403, message))

    assert read_the_readme_error(github).state == "github_rate_limited"


@pytest.mark.parametrize(
    ("answers", "state"),
    [
        ((readme_answer(401, b"{}"),), "github_unauthorized"),
        ((readme_answer(429, b"{}"),), "github_rate_limited"),
        (
            (readme_answer(403, b"{}", {"x-ratelimit-remaining": "0"}),),
            "github_rate_limited",
        ),
        ((readme_answer(503, b"{}"),), "github_unavailable"),
        ((readme_answer(422, b"{}"),), "github_invalid_response"),
    ],
    ids=["401", "429", "403-of-limit", "two-5xx", "422"],
)
def test_a_failure_of_github_on_a_readme_raises_its_state(answers, state):
    assert read_the_readme_error(SimulatedGithub(*answers)).state == state


def test_a_server_error_on_a_readme_is_retried_once_without_wait():
    github = SimulatedGithub(readme_answer(502, b"{}"), readme_answer())

    assert isinstance(read_the_readme(github), Readme)
    assert len(github.requests) == 2


def test_a_readme_counts_in_the_budget():
    github = SimulatedGithub(readme_answer())
    reading = start_reading(github)
    reading.requests = GITHUB_MAX_REQUESTS_PER_REPORT

    assert read_the_readme_error(github, reading).state == "github_unavailable"
    assert github.requests == []


def test_a_readme_late_is_github_timeout():
    def time_out(request):
        raise httpx2.ReadTimeout("timeout of the test", request=request)

    assert read_the_readme_error(SimulatedGithub(time_out)).state == "github_timeout"


@pytest.mark.parametrize("name", ["owner/..", "../name", "owner/.", "./name", "a/b/c"])
def test_a_name_with_dot_or_dotdot_never_makes_a_path(name):
    github = SimulatedGithub(readme_answer())

    with pytest.raises(ValueError, match="not owner/name") as raised:
        read_readme(start_reading(github), name)

    assert name not in str(raised.value)
    assert github.requests == []
    with pytest.raises(ValueError):
        to_repository_path(name)


class CountedPieces:
    """A body sent in pieces, counting those read."""

    def __init__(self, *pieces):
        self.pieces = pieces
        self.pieces_read = 0

    def __iter__(self):
        for piece in self.pieces:
            self.pieces_read += 1
            yield piece
