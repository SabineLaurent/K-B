"""The dependencies of the data routes: the connection of the request, bounded in time."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request

from k_b.database.connection import connect_database_read_only

# The instructions SQLite runs between two checks of the deadline: about 70 ms past it on the
# longest search, measured; each check takes the GIL back (docs/specs-api.md, API4).
INSTRUCTIONS_BETWEEN_CHECKS = 100


def open_database(request: Request) -> Iterator[sqlite3.Connection]:
    """One read-only connection per request, its readings stopped once the deadline is passed,
    closed once the response is made."""
    connection = connect_database_read_only(request.app.state.database_path)
    try:
        deadline = time.monotonic() + request.app.state.query_timeout_seconds
        connection.set_progress_handler(
            make_deadline_check(deadline), INSTRUCTIONS_BETWEEN_CHECKS
        )
        yield connection
    finally:
        connection.close()


def make_deadline_check(deadline: float) -> Callable[[], int]:
    """A progress handler of SQLite: once it gives 1, the reading stops with SQLITE_INTERRUPT."""

    def check_deadline() -> int:
        return int(time.monotonic() >= deadline)

    return check_deadline


Database = Annotated[sqlite3.Connection, Depends(open_database)]
