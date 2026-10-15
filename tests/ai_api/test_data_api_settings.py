"""The settings of the data API, read from a dict given as the environment: never from .env."""

import logging
import secrets

import pytest

from k_b.ai_api.data_api_settings import read_data_api_settings
from k_b.core.config import DATA_API_URL

# Made for the test: never a real key.
TEST_API_KEY = secrets.token_urlsafe(32)


def test_without_url_the_settings_take_the_local_default():
    settings = read_data_api_settings({"KB_API_KEY_AI_DIGEST": TEST_API_KEY})

    assert settings is not None
    assert settings.base_url == DATA_API_URL == "http://127.0.0.1:8000"
    assert settings.api_key.get_secret_value() == TEST_API_KEY


def test_the_url_of_the_environment_is_read():
    settings = read_data_api_settings(
        {
            "KB_DATA_API_URL": "http://api-donnees:8000",
            "KB_API_KEY_AI_DIGEST": TEST_API_KEY,
        }
    )

    assert settings is not None
    assert settings.base_url == "http://api-donnees:8000"


def test_an_empty_url_is_unset():
    settings = read_data_api_settings(
        {"KB_DATA_API_URL": "", "KB_API_KEY_AI_DIGEST": TEST_API_KEY}
    )

    assert settings is not None
    assert settings.base_url == DATA_API_URL


def test_a_url_refused_is_logged_by_its_variable_never_quoted(caplog):
    settings = read_data_api_settings(
        {
            "KB_DATA_API_URL": f"http://user:{TEST_API_KEY}@api-donnees",
            "KB_API_KEY_AI_DIGEST": TEST_API_KEY,
        }
    )

    assert settings is None
    assert caplog.messages == ["KB_DATA_API_URL: with user information"]


@pytest.mark.parametrize("key", [None, ""])
def test_without_key_the_settings_are_refused(key, caplog):
    environ = {} if key is None else {"KB_API_KEY_AI_DIGEST": key}

    assert read_data_api_settings(environ) is None
    assert caplog.messages == ["KB_API_KEY_AI_DIGEST: not set"]


@pytest.mark.parametrize(
    ("key", "refusal"),
    [
        (
            "short-key",
            "KB_API_KEY_AI_DIGEST: key of 9 characters, minimum 32",
        ),
        (
            TEST_API_KEY + " ",
            "KB_API_KEY_AI_DIGEST: key with a character outside [A-Za-z0-9_-]+",
        ),
    ],
)
def test_a_key_refused_is_never_quoted(key, refusal, caplog):
    caplog.set_level(logging.INFO)

    assert read_data_api_settings({"KB_API_KEY_AI_DIGEST": key}) is None
    assert caplog.messages == [refusal]
    assert key.strip() not in caplog.text
