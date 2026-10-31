"""The GitHub token of the trend reports, read from a dict given as the environment: never from
.env, never quoted."""

import secrets

import pytest

from k_b.ai_api.connectors.github_settings import (
    GITHUB_TOKEN_VARIABLE,
    GithubSettings,
    read_github_settings_or_refusal,
)

# Made for the test: never a real token. token_hex gives characters a fine-grained token holds.
TEST_TOKEN = f"github_pat_{secrets.token_hex(41)}"


def test_a_fine_grained_token_is_read():
    settings = read_github_settings_or_refusal({GITHUB_TOKEN_VARIABLE: TEST_TOKEN})

    assert GITHUB_TOKEN_VARIABLE == "KB_AI_GITHUB_TOKEN"  # noqa: S105 — a name, not a token
    assert isinstance(settings, GithubSettings)
    assert settings.token.get_secret_value() == TEST_TOKEN
    assert TEST_TOKEN not in repr(settings)


@pytest.mark.parametrize(
    ("environ", "refusal"),
    [
        ({}, "KB_AI_GITHUB_TOKEN: not set"),
        ({GITHUB_TOKEN_VARIABLE: ""}, "KB_AI_GITHUB_TOKEN: not set"),
        (
            {GITHUB_TOKEN_VARIABLE: f"ghp_{secrets.token_hex(18)}"},
            "KB_AI_GITHUB_TOKEN: not a fine-grained token (prefix github_pat_)",
        ),
        (
            {GITHUB_TOKEN_VARIABLE: f"{TEST_TOKEN}\n"},
            "KB_AI_GITHUB_TOKEN: token with a character outside [A-Za-z0-9_]+",
        ),
        (
            {GITHUB_TOKEN_VARIABLE: f"github_pat_{secrets.token_hex(8)}-x"},
            "KB_AI_GITHUB_TOKEN: token with a character outside [A-Za-z0-9_]+",
        ),
    ],
    ids=["missing", "empty", "classic", "line-feed", "dash"],
)
def test_a_token_refused_is_named_never_quoted(environ, refusal):
    assert read_github_settings_or_refusal(environ) == refusal
