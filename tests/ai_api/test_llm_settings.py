"""The settings of the model, read from a dict given as the environment: never from .env."""

import logging
from pathlib import Path

import pytest

from k_b.ai_api.llm_settings import read_llm_settings
from k_b.core.config import LLM_REPLAY_BASE_URL

# Made for the test: never a real key.
TEST_API_KEY = "test-key-0123456789"
PROVIDER_ENVIRONMENT = {
    "KB_LLM_PROVIDER": "openai_compatible",
    "KB_LLM_BASE_URL": "https://models.example/openai/v1",
    "KB_LLM_MODEL": "gpt-5.6-luna",
    "KB_LLM_API_KEY": TEST_API_KEY,
}
REPLAY_ENVIRONMENT = {
    "KB_LLM_PROVIDER": "replay",
    "KB_LLM_REPLAY_FILE": "tests/fixtures/llm_replay.json",
}


def test_the_settings_of_a_provider_are_read(caplog):
    caplog.set_level(logging.INFO)

    settings = read_llm_settings(PROVIDER_ENVIRONMENT)

    assert settings is not None
    assert settings.provider == "openai_compatible"
    assert settings.base_url == "https://models.example/openai/v1"
    assert settings.model == "gpt-5.6-luna"
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == TEST_API_KEY
    assert settings.reasoning_effort is None
    assert caplog.messages == ["LLM provider openai_compatible, model gpt-5.6-luna"]


def test_the_settings_of_the_replay_need_neither_url_nor_key(caplog):
    caplog.set_level(logging.INFO)

    settings = read_llm_settings(REPLAY_ENVIRONMENT)

    assert settings is not None
    assert settings.provider == "replay"
    assert settings.base_url == LLM_REPLAY_BASE_URL
    assert settings.api_key is None
    assert settings.replay_file == Path("tests/fixtures/llm_replay.json")
    # A container set on the replay by mistake says it.
    assert caplog.messages == ["LLM provider replay, model replay"]


def test_reasoning_effort_none_is_read():
    settings = read_llm_settings(
        PROVIDER_ENVIRONMENT | {"KB_LLM_REASONING_EFFORT": "none"}
    )

    assert settings is not None
    assert settings.reasoning_effort == "none"


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "KB_LLM_PROVIDER: not set, openai_compatible or replay"),
        (
            {"KB_LLM_PROVIDER": "openai"},
            "KB_LLM_PROVIDER: 'openai' not openai_compatible nor replay",
        ),
        (
            {"KB_LLM_PROVIDER": "replay"},
            "KB_LLM_REPLAY_FILE: not set, required by KB_LLM_PROVIDER=replay",
        ),
        (
            PROVIDER_ENVIRONMENT | {"KB_LLM_BASE_URL": ""},
            "KB_LLM_BASE_URL: not set, required by KB_LLM_PROVIDER=openai_compatible",
        ),
        (
            {k: v for k, v in PROVIDER_ENVIRONMENT.items() if k != "KB_LLM_MODEL"},
            "KB_LLM_MODEL: not set, required by KB_LLM_PROVIDER=openai_compatible",
        ),
        (
            {k: v for k, v in PROVIDER_ENVIRONMENT.items() if k != "KB_LLM_API_KEY"},
            "KB_LLM_API_KEY: not set, required by KB_LLM_PROVIDER=openai_compatible",
        ),
        (
            PROVIDER_ENVIRONMENT | {"KB_LLM_BASE_URL": "http://models.example/v1"},
            "KB_LLM_BASE_URL: scheme not https",
        ),
        (
            PROVIDER_ENVIRONMENT | {"KB_LLM_BASE_URL": "https:///v1"},
            "KB_LLM_BASE_URL: no host",
        ),
        (
            PROVIDER_ENVIRONMENT | {"KB_LLM_BASE_URL": "https://[::1/v1"},
            "KB_LLM_BASE_URL: not a URL",
        ),
        (
            PROVIDER_ENVIRONMENT | {"KB_LLM_MODEL": "gpt 5\n"},
            r"KB_LLM_MODEL: 'gpt 5\n' not [A-Za-z0-9][A-Za-z0-9._:-]{0,99}",
        ),
        (
            PROVIDER_ENVIRONMENT | {"KB_LLM_REASONING_EFFORT": "low"},
            "KB_LLM_REASONING_EFFORT: 'low' not none",
        ),
    ],
    ids=[
        "no-provider",
        "unknown-provider",
        "replay-without-file",
        "empty-url",
        "no-model",
        "no-key",
        "http",
        "no-host",
        "not-a-url",
        "model-out-of-pattern",
        "reasoning-effort-other-than-none",
    ],
)
def test_a_setting_refused_is_logged_and_gives_none(environment, message, caplog):
    assert read_llm_settings(environment) is None
    assert caplog.messages == [message]


@pytest.mark.parametrize(
    ("base_url", "message"),
    [
        (
            f"https://user:{TEST_API_KEY}@models.example/v1",
            "KB_LLM_BASE_URL: with user information",
        ),
        (
            f"https://models.example/v1?api-key={TEST_API_KEY}",
            "KB_LLM_BASE_URL: with a query or a fragment",
        ),
        (
            f"https://models.example/v1#{TEST_API_KEY}",
            "KB_LLM_BASE_URL: with a query or a fragment",
        ),
    ],
    ids=["user-information", "query", "fragment"],
)
def test_a_url_refused_is_never_quoted_since_it_may_carry_a_key(
    base_url, message, caplog
):
    environment = PROVIDER_ENVIRONMENT | {"KB_LLM_BASE_URL": base_url}

    assert read_llm_settings(environment) is None
    assert caplog.messages == [message]
    assert TEST_API_KEY not in caplog.text


@pytest.mark.parametrize(
    "api_key",
    [" key", "key with space", "clé", "key\n"],
    ids=["space-before", "space", "non-ascii", "line-break"],
)
def test_a_key_refused_is_never_quoted(api_key, caplog):
    environment = PROVIDER_ENVIRONMENT | {"KB_LLM_API_KEY": api_key}

    assert read_llm_settings(environment) is None
    assert caplog.messages == [
        "KB_LLM_API_KEY: a character outside printable ASCII, or a space"
    ]
    assert api_key.strip() not in caplog.text


def test_the_key_is_not_in_the_representation_of_the_settings():
    settings = read_llm_settings(PROVIDER_ENVIRONMENT)

    assert TEST_API_KEY not in repr(settings)
