"""The dependencies of the data routes: the connection of the request, bounded in time."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request

from k_b.database.connection import connect_database_read_only

# The instructions SQLite runs between two checks of the deadline: about 0.75 s past it on the
# longest search, measured (0.1 s at 100); each check takes the GIL back, so fewer checks spare
# the other requests (docs/specs-api.md, "Délai"). Read at each request: a test lowers it.
INSTRUCTIONS_BETWEEN_CHECKS = 1_000


def open_database(request: Request) -> Iterator[sqlite3.Connection]:
    """One read-only connection per request, its readings stopped once the deadline is passed,
    closed once the response is made."""
    connection = connect_database_read_only(request.app.state.database_path)
    try:
        connection.set_progress_handler(
            make_deadline_check(request.app.state.query_timeout_seconds),
            INSTRUCTIONS_BETWEEN_CHECKS,
        )
        yield connection
    finally:
        connection.close()


def make_deadline_check(
    timeout_seconds: float, clock: Callable[[], float] = time.monotonic
) -> Callable[[], int]:
    """A progress handler of SQLite: once it gives 1, the reading stops with SQLITE_INTERRUPT.

    The deadline starts at its first call, once SQLite reads: the dependency and the route each
    wait for a thread of the pool, and that wait is not spent in the base."""
    deadline: float | None = None

    def check_deadline() -> int:
        nonlocal deadline
        now = clock()
        if deadline is None:
            deadline = now + timeout_seconds
        return int(now >= deadline)

    return check_deadline


Database = Annotated[sqlite3.Connection, Depends(open_database)]
