from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from k_b.etl.http_retry import (
    RETRY_AFTER_MAX_SECONDS,
    RETRY_WAIT_SECONDS,
    find_retry_wait,
    note_rate_limit_reset,
)

URL = "https://example.org/feed"
DEFAULT_WAIT = 7


def http_error(status, **headers):
    message = Message()
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    return HTTPError(URL, status, "error", message, None)


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_a_429_or_a_5xx_without_retry_after_waits_the_default(status):
    assert find_retry_wait(http_error(status), DEFAULT_WAIT) == DEFAULT_WAIT


def test_a_retry_after_in_seconds_is_waited():
    assert find_retry_wait(http_error(429, Retry_After="12"), DEFAULT_WAIT) == 12


def test_a_retry_after_at_the_maximum_is_waited():
    error = http_error(503, Retry_After=str(RETRY_AFTER_MAX_SECONDS))

    assert find_retry_wait(error, DEFAULT_WAIT) == RETRY_AFTER_MAX_SECONDS


@pytest.mark.parametrize(
    "retry_after", [str(RETRY_AFTER_MAX_SECONDS + 1), "9" * 10, "9" * 5000]
)
def test_a_retry_after_above_the_maximum_gets_no_retry(retry_after):
    assert (
        find_retry_wait(http_error(429, Retry_After=retry_after), DEFAULT_WAIT) is None
    )


@pytest.mark.parametrize(
    "retry_after", ["Wed, 21 Oct 2026 07:28:00 GMT", "-1", "1.5", "\uff11"]
)
def test_a_retry_after_not_in_seconds_is_read_as_no_header(retry_after):
    error = http_error(429, Retry_After=retry_after)

    assert find_retry_wait(error, DEFAULT_WAIT) == DEFAULT_WAIT


@pytest.mark.parametrize("status", [304, 400, 401, 403, 404])
def test_another_status_gets_no_retry(status):
    assert find_retry_wait(http_error(status), DEFAULT_WAIT) is None


@pytest.mark.parametrize("status", [403, 429])
def test_a_rate_limit_with_no_request_left_gets_no_retry(status):
    error = http_error(status, x_ratelimit_remaining="0", Retry_After="1")

    assert find_retry_wait(error, DEFAULT_WAIT) is None


def test_a_rate_limit_with_requests_left_is_retried():
    error = http_error(429, x_ratelimit_remaining="12")

    assert find_retry_wait(error, DEFAULT_WAIT) == DEFAULT_WAIT


def test_a_failed_connection_waits_the_default():
    error = URLError(ConnectionRefusedError(61, "Connection refused"))

    assert find_retry_wait(error, DEFAULT_WAIT) == DEFAULT_WAIT


def test_a_timeout_gets_no_retry():
    assert find_retry_wait(URLError(TimeoutError("timed out")), DEFAULT_WAIT) is None


def test_the_default_wait_is_longer_than_the_3_seconds_arxiv_asks_between_requests():
    assert RETRY_WAIT_SECONDS > 3


def test_a_rate_limit_with_no_request_left_notes_its_reset_in_utc():
    # GitHub gives the reset in epoch seconds.
    error = http_error(403, x_ratelimit_remaining="0", x_ratelimit_reset="1792944000")

    note_rate_limit_reset(error)

    assert error.__notes__ == [
        "rate limit reached, no request left until 2026-10-25T16:00:00+00:00"
    ]


@pytest.mark.parametrize("reset", [None, "soon", "9" * 11])
def test_a_reset_missing_or_unreadable_is_not_given(reset):
    headers = {"x_ratelimit_remaining": "0"}
    if reset is not None:
        headers["x_ratelimit_reset"] = reset
    error = http_error(429, **headers)

    note_rate_limit_reset(error)

    assert error.__notes__ == ["rate limit reached, no request left"]


def test_an_error_with_requests_left_gets_no_note():
    error = http_error(429, x_ratelimit_remaining="3", x_ratelimit_reset="1792944000")

    note_rate_limit_reset(error)

    assert not hasattr(error, "__notes__")
