"""When a source download gets a retry, and after which wait: the politeness of K-B towards the
services it collects (RFC 9110 Retry-After, rate limits)."""

import math
from datetime import UTC, datetime
from http import HTTPStatus

import httpx2

from k_b.core.rate_limit import (
    MIN_PAUSE_SECONDS,
    RATE_LIMIT_REMAINING_HEADER,
    RATE_LIMIT_RESET_HEADER,
    read_rate_limit_reset_value,
)
from k_b.core.retry_after import is_retry_after_too_long, read_retry_after
from k_b.etl.source_contract import SourceStatusError

# The wait before the one retry after a 429, a 5xx or a failed connection, when the answer gives
# no Retry-After. A timeout gets no retry, as for the model (ai_api/connectors/llm_client.py): it
# would double a wait of HTTP_TIMEOUT_SECONDS (core/config.py).
RETRY_WAIT_SECONDS = 5
# Never less, whatever a Retry-After says: the 3 seconds arXiv asks between two requests (Terms of
# Use for arXiv APIs).
MIN_RETRY_WAIT_SECONDS = 3
# A Retry-After above it is not waited: the source fails, its last collection date stays, and the
# next collection asks again.
RETRY_AFTER_MAX_SECONDS = 60
# A rate limit with no request left (GitHub, core/rate_limit.py): its reset can be an hour away, so
# the answer gets no retry; the reset time, in epoch seconds, is noted on the error.


def find_retry_wait(
    error: httpx2.TransportError | SourceStatusError, rate_limited_wait: float
) -> float | None:
    """The wait before the retry, or None: no retry.

    rate_limited_wait follows a 429 without Retry-After; a 403 is retried only with a Retry-After
    (the secondary rate limit of GitHub), as it is first a refusal."""
    if isinstance(error, httpx2.TransportError):
        # A failed connection, also when it drops before or during the answer; a timeout is not
        # retried (see RETRY_WAIT_SECONDS).
        is_timeout = isinstance(error, httpx2.TimeoutException)
        return None if is_timeout else RETRY_WAIT_SECONDS
    if is_rate_limit_exhausted(error):
        return None
    retry_after = error.headers.get("Retry-After")
    if not is_retried_status(error, retry_after) or is_retry_after_beyond_max(
        retry_after
    ):
        # Beyond the maximum, a shorter wait would get the same answer.
        return None
    seconds = read_retry_after(retry_after)
    if seconds is None:
        if error.status == HTTPStatus.TOO_MANY_REQUESTS:
            return rate_limited_wait
        return RETRY_WAIT_SECONDS
    return max(seconds, MIN_RETRY_WAIT_SECONDS)


def find_pause_end(error: SourceStatusError, now: float) -> float | None:
    """Until when, in epoch seconds, the service asks for no request at all, or None: the reset
    of an exhausted rate limit, or the end of a Retry-After beyond RETRY_AFTER_MAX_SECONDS."""
    # Both may come together (a secondary rate limit of GitHub): the longer wins.
    pause_ends: list[float] = []
    if is_rate_limit_exhausted(error):
        # Without a readable reset, or a reset already past (a clock off): the minute GitHub asks.
        pause_ends.append(
            max(read_rate_limit_reset(error) or 0, now + MIN_PAUSE_SECONDS)
        )
    retry_after = error.headers.get("Retry-After")
    if is_retried_status(error, retry_after) and is_retry_after_beyond_max(retry_after):
        seconds = read_retry_after(retry_after)
        # Too long to read: no request for the rest of the process.
        pause_ends.append(math.inf if seconds is None else now + seconds)
    return max(pause_ends, default=None)


def is_retried_status(error: SourceStatusError, retry_after: str | None) -> bool:
    """A 429, a 5xx, or a 403 with a Retry-After (the secondary rate limit of GitHub): a 403
    without it is first a refusal."""
    return (
        error.status == HTTPStatus.TOO_MANY_REQUESTS
        or error.status >= HTTPStatus.INTERNAL_SERVER_ERROR
        or (error.status == HTTPStatus.FORBIDDEN and retry_after is not None)
    )


def is_retry_after_beyond_max(retry_after: str | None) -> bool:
    seconds = read_retry_after(retry_after)
    return is_retry_after_too_long(retry_after) or (
        seconds is not None and seconds > RETRY_AFTER_MAX_SECONDS
    )


def read_rate_limit_reset(error: SourceStatusError) -> int | None:
    """Its reset in epoch seconds; None when missing or unreadable."""
    return read_rate_limit_reset_value(error.headers.get(RATE_LIMIT_RESET_HEADER))


def is_rate_limit_exhausted(error: SourceStatusError) -> bool:
    return error.headers.get(RATE_LIMIT_REMAINING_HEADER) == "0"


def note_rate_limit_reset(error: SourceStatusError) -> None:
    """Note on the error when a rate limit with no request left resets: the log of the failed
    source gives it."""
    if not is_rate_limit_exhausted(error):
        return
    reset = read_rate_limit_reset(error)
    if reset is None:
        error.add_note("rate limit reached, no request left")
        return
    reset_at = datetime.fromtimestamp(reset, UTC)
    error.add_note(f"rate limit reached, no request left until {reset_at.isoformat()}")
