"""The deadline of a digest request: DIGEST_REQUEST_TIMEOUT_SECONDS after its arrival, the bound of
its reading by the data API and of its calls to the model (docs/fiches-veille.md, "Lecture
plafonnée").

The timeouts of httpx2 bound each wait, not a request: the read timeout applies to each piece of
an answer. The deadline shortens each of them to the time left and is checked before each
request, and, for the data API, between two pieces read. Limit written in the spec: a request
started before the deadline may end past it by the sum of its timeouts (pool, connection, write,
read), each shortened to the time left at its start: 30 seconds at most for the data API; for the
model, 20 seconds and its read, without bound for an answer sent in pieces, which httpx2 reads
whole."""

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from k_b.core.config import MIN_SECONDS_FOR_LLM_REQUEST


@dataclass(frozen=True)
class Deadline:
    # An instant of the clock, in seconds: time.monotonic, which the time of the machine does not
    # move, or the clock of a test.
    at_seconds: float
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def after(
        cls, seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> "Deadline":
        return cls(clock() + seconds, clock)

    def remaining_seconds(self) -> float:
        return self.at_seconds - self.clock()

    def is_passed(self) -> bool:
        return self.remaining_seconds() <= 0

    def allows_llm_request(self, wait_seconds: float = 0) -> bool:
        """Whether a request to the model, sent after wait_seconds, still has the time it needs."""
        return self.remaining_seconds() - wait_seconds >= MIN_SECONDS_FOR_LLM_REQUEST

    def cap(self, timeout: httpx2.Timeout) -> httpx2.Timeout:
        """The timeouts, each shortened to the time left; None (no timeout) becomes it."""
        left = max(self.remaining_seconds(), 0.0)

        def shorten(seconds: float | None) -> float:
            return left if seconds is None else min(seconds, left)

        return httpx2.Timeout(
            connect=shorten(timeout.connect),
            read=shorten(timeout.read),
            write=shorten(timeout.write),
            pool=shorten(timeout.pool),
        )
