"""The sliding window of core/api_rate_limit.py, on a clock set by the test."""

from k_b.core.api_rate_limit import RateLimiter
from k_b.core.config import RateLimit

ROUTE = "/items"
OTHER_ROUTE = "/trends"


class SetClock:
    """A clock that moves only when the test says so."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_limiter(clock, requests=2, window_seconds=60):
    limit = RateLimit(requests=requests, window_seconds=window_seconds)
    return RateLimiter({ROUTE: limit, OTHER_ROUTE: limit}, clock=clock)


def test_calls_under_the_limit_are_allowed():
    limiter = make_limiter(SetClock())

    assert limiter.admit_call("TERMINAL", ROUTE) is None
    assert limiter.admit_call("TERMINAL", ROUTE) is None


def test_a_call_beyond_the_limit_gets_the_wait_of_the_oldest_call():
    clock = SetClock()
    limiter = make_limiter(clock)
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 10
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 5

    assert limiter.admit_call("TERMINAL", ROUTE) == 45


def test_the_wait_is_rounded_up_never_to_zero():
    clock = SetClock()
    limiter = make_limiter(clock, requests=1)
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 59.5

    assert limiter.admit_call("TERMINAL", ROUTE) == 1


def test_a_call_refused_is_not_counted():
    clock = SetClock()
    limiter = make_limiter(clock, requests=1)
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 30
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 30

    assert limiter.admit_call("TERMINAL", ROUTE) is None


def test_the_window_slides_a_call_at_its_end_is_gone():
    clock = SetClock()
    limiter = make_limiter(clock)
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 30
    limiter.admit_call("TERMINAL", ROUTE)
    clock.now += 30

    # The first call has left the window, the second is still in it.
    assert limiter.admit_call("TERMINAL", ROUTE) is None
    assert limiter.admit_call("TERMINAL", ROUTE) == 30


def test_each_client_and_each_route_has_its_own_count():
    limiter = make_limiter(SetClock(), requests=1)
    limiter.admit_call("TERMINAL", ROUTE)

    assert limiter.admit_call("AGENT", ROUTE) is None
    assert limiter.admit_call("TERMINAL", OTHER_ROUTE) is None
    assert limiter.admit_call("TERMINAL", ROUTE) == 60
