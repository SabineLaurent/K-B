"""Connect to the items database, SQLite or PostgreSQL, through the one type of connection every
module of K-B is given; lock it for a writer, and bound the time of its readings on SQLite."""

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from k_b.database import postgresql
from k_b.database.location import DatabaseLocation, check_database_exists
from k_b.database.postgresql import PostgresConnection

# The class of sqlite3 itself, not a wrapper: the SQLite path stays as it is.
SqliteConnection = sqlite3.Connection
# The connection of either engine: PostgresConnection has the methods of sqlite3 that K-B uses.
Connection = SqliteConnection | PostgresConnection

# The instructions SQLite runs between two checks of the deadline: about 0.75 s past it on the
# longest search, measured (0.1 s at 100); each check takes the GIL back, so fewer checks spare
# the other requests (docs/specs-api.md, "Délai"). Read at each request: a test lowers it.
INSTRUCTIONS_BETWEEN_CHECKS = 1_000


def connect_database(location: DatabaseLocation) -> Connection:
    """Open the database of the engine the location names."""
    if isinstance(location, Path):
        return connect_sqlite(location)
    return postgresql.connect_postgresql(location)


def connect_sqlite(database_path: Path) -> SqliteConnection:
    """Open the SQLite file; SQLite ignores foreign keys unless each connection turns them on."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def lock_for_writing(connection: Connection) -> None:
    """Hold the lock of the writers until the end of the transaction, on PostgreSQL; SQLite holds
    its own write lock from the first write to the commit."""
    if isinstance(connection, PostgresConnection):
        postgresql.lock_for_writing(connection)


def is_commit_finished_before_a_signal(connection: Connection) -> bool:
    """Whether a signal received during a commit is raised once the commit has returned: on
    SQLite, where Python runs the handler after the call to SQLite; not on PostgreSQL, where psycopg
    waits for the answer to COMMIT in Python and, on the signal, asks the server to cancel it,
    which the server may or may not do."""
    return isinstance(connection, SqliteConnection)


def connect_database_read_only(database_path: Path) -> SqliteConnection:
    """Open the database read only, one connection per request of the data API
    (check_same_thread=False).

    The base is checked first: mode=ro does not create a missing file, but its error does not
    tell it from another; as_uri escapes a space, # or ? of the path."""
    check_database_exists(database_path)
    connection = sqlite3.connect(
        f"{database_path.absolute().as_uri()}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def set_query_timeout(connection: SqliteConnection, timeout_seconds: float) -> None:
    """Stop the readings of the connection once its deadline is passed: the error raised is one
    is_query_timeout (database/errors.py) recognizes."""
    connection.set_progress_handler(
        make_deadline_check(timeout_seconds), INSTRUCTIONS_BETWEEN_CHECKS
    )


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
