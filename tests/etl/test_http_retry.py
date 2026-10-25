from urllib.error import URLError

import pytest
from http_helpers import http_error

from k_b.etl.http_retry import (
    MIN_RETRY_WAIT_SECONDS,
    RETRY_AFTER_MAX_SECONDS,
    RETRY_WAIT_SECONDS,
    find_retry_wait,
    note_rate_limit_reset,
)

TRUSTED_URL_PREFIX = "https://example.org/"
URL = TRUSTED_URL_PREFIX + "feed"
RATE_LIMITED_WAIT = 60
# 2026-10-25T16:00:00Z, as GitHub gives a reset: in epoch seconds.
RESET_EPOCH_SECONDS = "1792944000"


def retry_wait(error):
    return find_retry_wait(error, TRUSTED_URL_PREFIX, RATE_LIMITED_WAIT)


def test_a_429_without_retry_after_waits_the_rate_limited_wait():
    assert retry_wait(http_error(URL, 429)) == RATE_LIMITED_WAIT


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_5xx_without_retry_after_waits_the_default(status):
    assert retry_wait(http_error(URL, status)) == RETRY_WAIT_SECONDS


def test_a_retry_after_in_seconds_is_waited():
    assert retry_wait(http_error(URL, 429, Retry_After="12")) == 12


def test_a_retry_after_at_the_maximum_is_waited():
    error = http_error(URL, 503, Retry_After=str(RETRY_AFTER_MAX_SECONDS))

    assert retry_wait(error) == RETRY_AFTER_MAX_SECONDS


@pytest.mark.parametrize("retry_after", ["0", "2"])
def test_a_short_retry_after_still_waits_the_3_seconds_arxiv_asks(retry_after):
    assert retry_wait(http_error(URL, 503, Retry_After=retry_after)) == 3
    assert MIN_RETRY_WAIT_SECONDS == 3


@pytest.mark.parametrize(
    "retry_after", [str(RETRY_AFTER_MAX_SECONDS + 1), "9" * 10, "9" * 5000]
)
def test_a_retry_after_above_the_maximum_gets_no_retry(retry_after):
    assert retry_wait(http_error(URL, 429, Retry_After=retry_after)) is None


@pytest.mark.parametrize(
    "retry_after", ["Wed, 21 Oct 2026 07:28:00 GMT", "-1", "1.5", "\uff11"]
)
def test_a_retry_after_not_in_seconds_is_read_as_no_header(retry_after):
    assert retry_wait(http_error(URL, 503, Retry_After=retry_after)) == (
        RETRY_WAIT_SECONDS
    )


@pytest.mark.parametrize("status", [304, 400, 401, 403, 404])
def test_another_status_gets_no_retry(status):
    assert retry_wait(http_error(URL, status)) is None


def test_a_403_with_retry_after_is_the_secondary_rate_limit_of_github_and_is_retried():
    error = http_error(URL, 403, Retry_After="30", x_ratelimit_remaining="4000")

    assert retry_wait(error) == 30


@pytest.mark.parametrize("status", [403, 429])
def test_a_rate_limit_with_no_request_left_gets_no_retry(status):
    error = http_error(URL, status, x_ratelimit_remaining="0", Retry_After="5")

    assert retry_wait(error) is None


def test_a_rate_limit_with_requests_left_is_retried():
    error = http_error(URL, 429, x_ratelimit_remaining="12")

    assert retry_wait(error) == RATE_LIMITED_WAIT


def test_an_answer_served_from_outside_the_trusted_prefix_is_not_read():
    error = http_error("https://example.com/landing", 503, Retry_After="10")

    assert retry_wait(error) is None


@pytest.mark.parametrize(
    "error",
    [
        URLError(ConnectionRefusedError(61, "Connection refused")),
        # Dropped before the answer: http.client raises it as is, not in a URLError.
        ConnectionResetError(54, "Connection reset by peer"),
    ],
    ids=["refused", "dropped"],
)
def test_a_failed_connection_waits_the_default(error):
    assert retry_wait(error) == RETRY_WAIT_SECONDS


def test_a_timeout_gets_no_retry():
    assert retry_wait(URLError(TimeoutError("timed out"))) is None


def test_a_rate_limit_with_no_request_left_notes_its_reset_in_utc():
    error = http_error(
        URL, 403, x_ratelimit_remaining="0", x_ratelimit_reset=RESET_EPOCH_SECONDS
    )

    note_rate_limit_reset(error, TRUSTED_URL_PREFIX)

    assert error.__notes__ == [
        "rate limit reached, no request left until 2026-10-25T16:00:00+00:00"
    ]


@pytest.mark.parametrize("reset", [None, "soon", "9" * 11])
def test_a_reset_missing_or_unreadable_is_not_given(reset):
    headers = {"x_ratelimit_remaining": "0"}
    if reset is not None:
        headers["x_ratelimit_reset"] = reset
    error = http_error(URL, 429, **headers)

    note_rate_limit_reset(error, TRUSTED_URL_PREFIX)

    assert error.__notes__ == ["rate limit reached, no request left"]


@pytest.mark.parametrize(
    ("url", "remaining"),
    [(URL, "3"), ("https://example.com/landing", "0")],
    ids=["requests-left", "served-from-outside"],
)
def test_no_note_without_an_exhausted_rate_limit_from_the_trusted_prefix(
    url, remaining
):
    error = http_error(
        url, 429, x_ratelimit_remaining=remaining, x_ratelimit_reset=RESET_EPOCH_SECONDS
    )

    note_rate_limit_reset(error, TRUSTED_URL_PREFIX)

    assert not hasattr(error, "__notes__")
