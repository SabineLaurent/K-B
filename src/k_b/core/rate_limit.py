"""The rate limit of a service (GitHub) in the headers of its answer: one reading for every client
of K-B calling it."""

import re

# A rate limit with no request left gives "0" remaining, and its reset in epoch seconds.
RATE_LIMIT_REMAINING_HEADER = "x-ratelimit-remaining"
RATE_LIMIT_RESET_HEADER = "x-ratelimit-reset"
EPOCH_SECONDS = re.compile(r"[0-9]{1,10}")
# A pause asked by a service lasts at least a minute: GitHub asks it when it gives no reset
# (docs: "Rate limits for the REST API", 2026-10-25).
MIN_PAUSE_SECONDS = 60


def read_rate_limit_reset_value(value: str | None) -> int | None:
    """The reset of a rate limit header in epoch seconds; None when missing or unreadable."""
    if value is None or not EPOCH_SECONDS.fullmatch(value):
        return None
    return int(value)
