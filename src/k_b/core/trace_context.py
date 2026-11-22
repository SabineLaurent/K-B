"""The trace of a request across the two APIs: its traceparent header, read and written as the W3C
Trace Context writes it (https://www.w3.org/TR/trace-context/), and its trace id, carried by each
log line written during the request (commands/run_log.py). No OpenTelemetry here: the data API
does not import it (tests/architecture/test_opentelemetry.py)."""

import re
import secrets
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import Request, Response

TRACEPARENT_HEADER = "traceparent"
# Version 00, ids in lowercase hex: any other value, a later version included, starts a new trace.
TRACEPARENT_PATTERN = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}")
INVALID_TRACE_ID = "0" * 32
INVALID_PARENT_ID = "0" * 16
# Sampled: the AI API keeps every span (connectors/trace_export.py, ALWAYS_ON).
SAMPLED_FLAGS = "01"
TRACE_ID_BYTES = 16
SPAN_ID_BYTES = 8

CURRENT_TRACE_ID: ContextVar[str | None] = ContextVar("current_trace_id", default=None)


async def follow_trace(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """The data API: the trace id of the request is the one of its traceparent, sent by the AI API,
    or a new one; never the value received when it is refused. The outermost middleware, so that
    the request line carries it."""
    received = read_trace_id(request.headers.getlist(TRACEPARENT_HEADER))
    with following_trace(received or draw_trace_id()):
        return await call_next(request)


async def start_trace(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """The AI API: a new trace id for each request, a traceparent received ignored, so that no
    caller chooses the trace of its spans. The outermost middleware, as follow_trace."""
    with following_trace(draw_trace_id()):
        return await call_next(request)


@contextmanager
def following_trace(trace_id: str) -> Iterator[None]:
    """The trace id of the request under way, for the time of the block."""
    token = CURRENT_TRACE_ID.set(trace_id)
    try:
        yield
    finally:
        CURRENT_TRACE_ID.reset(token)


def read_trace_id(values: list[str]) -> str | None:
    """The trace id of the one traceparent received, or None: absent, repeated, or not valid."""
    if len(values) != 1:
        return None
    match = TRACEPARENT_PATTERN.fullmatch(values[0])
    if match is None:
        return None
    trace_id, parent_id = match.groups()
    if trace_id == INVALID_TRACE_ID or parent_id == INVALID_PARENT_ID:
        return None
    return trace_id


def read_current_trace_id() -> str | None:
    """The trace id of the request under way, None out of a request."""
    return CURRENT_TRACE_ID.get()


def draw_trace_id() -> str:
    """A new trace id; all zeros, the invalid one, has a chance of one in 2**128."""
    return secrets.token_hex(TRACE_ID_BYTES)


def draw_span_id() -> str:
    """A new span id, the parent id of a request sent when no span of its trace records."""
    return secrets.token_hex(SPAN_ID_BYTES)


def format_traceparent(trace_id: str, parent_id: str) -> str:
    """The traceparent of a request sent, sampled."""
    return f"00-{trace_id}-{parent_id}-{SAMPLED_FLAGS}"
