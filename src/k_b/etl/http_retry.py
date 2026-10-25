"""When a source download gets a retry, and after which wait: the politeness of K-B towards the
services it collects (RFC 9110 Retry-After, rate limits)."""

import re
from datetime import UTC, datetime
from http import HTTPStatus
from urllib.error import HTTPError, URLError

# The wait before the one retry after a 429, a 5xx or a failed connection, when the answer gives
# no Retry-After. A timeout gets no retry, as for the model (ai_api/connectors/llm_client.py): it
# would double a wait of http_download.TIMEOUT_SECONDS.
RETRY_WAIT_SECONDS = 5
# Never less, whatever a Retry-After says: the 3 seconds arXiv asks between two requests (Terms of
# Use for arXiv APIs).
MIN_RETRY_WAIT_SECONDS = 3
# A Retry-After above it is not waited: the source fails, its last collection date stays, and the
# next collection asks again.
RETRY_AFTER_MAX_SECONDS = 60
# The delay-seconds form of Retry-After (RFC 9110, § 10.2.3); its HTTP-date form, rare, is read as
# no header. Over 9 digits, about 31 years, it is a wait beyond the maximum: int() is not asked.
RETRY_AFTER_SECONDS = re.compile(r"[0-9]+")
MAX_RETRY_AFTER_DIGITS = 9
# A rate limit with no request left (GitHub): its reset may be an hour away, so the answer gets no
# retry; the reset time, in epoch seconds, is noted on the error.
RATE_LIMIT_REMAINING_HEADER = "x-ratelimit-remaining"
RATE_LIMIT_RESET_HEADER = "x-ratelimit-reset"
EPOCH_SECONDS = re.compile(r"[0-9]{1,10}")


def find_retry_wait(
    error: URLError | ConnectionError,
    trusted_url_prefix: str,
    rate_limited_wait: float,
) -> float | None:
    """The wait before the retry, or None: no retry.

    rate_limited_wait follows a 429 without Retry-After; a 403 is retried only with a Retry-After
    (the secondary rate limit of GitHub), as it is first a refusal. An answer served from outside
    trusted_url_prefix, after a redirection, is not read."""
    if not isinstance(error, HTTPError):
        # A failed connection, also when it drops before the answer (ConnectionError); a
        # timeout is not retried (see RETRY_WAIT_SECONDS).
        is_timeout = isinstance(error, URLError) and isinstance(
            error.reason, TimeoutError
        )
        return None if is_timeout else RETRY_WAIT_SECONDS
    if not is_served_from(error, trusted_url_prefix) or is_rate_limit_exhausted(error):
        return None
    retry_after = error.headers.get("Retry-After")
    is_retried_status = (
        error.code == HTTPStatus.TOO_MANY_REQUESTS
        or error.code >= HTTPStatus.INTERNAL_SERVER_ERROR
        or (error.code == HTTPStatus.FORBIDDEN and retry_after is not None)
    )
    if not is_retried_status:
        return None
    if retry_after is None or not RETRY_AFTER_SECONDS.fullmatch(retry_after):
        if error.code == HTTPStatus.TOO_MANY_REQUESTS:
            return rate_limited_wait
        return RETRY_WAIT_SECONDS
    if (
        len(retry_after) > MAX_RETRY_AFTER_DIGITS
        or int(retry_after) > RETRY_AFTER_MAX_SECONDS
    ):
        # A shorter wait would get the same answer.
        return None
    return max(int(retry_after), MIN_RETRY_WAIT_SECONDS)


def is_served_from(error: HTTPError, trusted_url_prefix: str) -> bool:
    """Whether the error answer came from the trusted prefix: urlopen follows redirections."""
    return error.geturl().startswith(trusted_url_prefix)


def is_rate_limit_exhausted(error: HTTPError) -> bool:
    return error.headers.get(RATE_LIMIT_REMAINING_HEADER) == "0"


def note_rate_limit_reset(error: HTTPError, trusted_url_prefix: str) -> None:
    """Note on the error when a rate limit with no request left resets: the log of the failed
    source gives it. An answer served from outside trusted_url_prefix is not read."""
    if not is_served_from(error, trusted_url_prefix) or not is_rate_limit_exhausted(
        error
    ):
        return
    reset = error.headers.get(RATE_LIMIT_RESET_HEADER)
    if reset is None or not EPOCH_SECONDS.fullmatch(reset):
        error.add_note("rate limit reached, no request left")
        return
    reset_at = datetime.fromtimestamp(int(reset), UTC)
    error.add_note(f"rate limit reached, no request left until {reset_at.isoformat()}")
