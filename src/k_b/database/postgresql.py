"""The PostgreSQL branch of the engine: a connection of psycopg 3 that the modules of K-B use as one
of sqlite3, its SQL translated to the placeholders of psycopg, the lock of the writers, and the
pool the data API reads with."""

import logging
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from functools import partial
from typing import Any

import psycopg
from psycopg import IsolationLevel, pq
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool

from k_b.core.config import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DATABASE_LOCK_TIMEOUT_SECONDS,
    READING_POOL_MAX_SIZE,
    READING_POOL_MIN_SIZE,
    READING_POOL_WAIT_SECONDS,
)
from k_b.database.location import (
    DATABASE_URL_VARIABLE,
    PostgresUrl,
    UnreadableDatabaseUrlError,
)

# A named placeholder of sqlite3 by the rule of SQLAlchemy 2.0.55, for its text(): a name after a
# colon that follows neither a colon, a letter, a digit nor a backslash, and that a colon does not
# follow; so a cast (x::text) and a time ('09:30:00') are left as they are.
NAMED_PLACEHOLDER = re.compile(r"(?<![:\w\\]):(\w+)(?![:\w])")
# The transaction is open while the connection writes, and still open after an error, until it is
# undone: a savepoint can then be rolled back to (database/savepoint.py).
OPEN_TRANSACTION_STATUSES = frozenset(
    {pq.TransactionStatus.INTRANS, pq.TransactionStatus.INERROR}
)
# The lock of the writers of K-B, held until the end of the transaction: two imports write one after
# the other, as behind the write lock of SQLite, and a purge waits for an import. The key is any one
# number, the same for every writer: the bytes "k-b" read as an integer.
WRITING_LOCK_KEY = int.from_bytes(b"k-b")
SET_LOCK_TIMEOUT = "SELECT set_config('lock_timeout', ?, true)"
LOCK_FOR_WRITING = "SELECT pg_advisory_xact_lock(?)"
# The deadline of every statement of a connection of the readers, for its whole session: set by
# K-B, not by the server, so that a base set up without it is never read without a deadline.
SET_STATEMENT_TIMEOUT = "SELECT set_config('statement_timeout', ?, false)"
# statement_timeout at 0 disables the deadline: a shorter one is refused.
MIN_STATEMENT_TIMEOUT_MILLISECONDS = 1

logger = logging.getLogger(__name__)

# The state logged when the server ended the session of a reader before its rollback.
READER_SESSION_LOST = "reader_session_lost"

# The parameters of a statement: by position for ?, by name for :name.
type Parameters = Sequence[Any] | Mapping[str, Any]


def translate_placeholders(sql: str) -> str:
    """The SQL of K-B, written for sqlite3, with the placeholders of psycopg: ? becomes %s, :name
    becomes %(name)s, and a % is doubled, as psycopg reads % as the start of a placeholder."""
    escaped = sql.replace("%", "%%").replace("?", "%s")
    return NAMED_PLACEHOLDER.sub(r"%(\1)s", escaped)


class PostgresCursor:
    """The rows of a statement, read as those of a cursor of sqlite3."""

    def __init__(self, cursor: psycopg.Cursor[tuple[Any, ...]]) -> None:
        """Wrap the cursor of psycopg that ran the statement."""
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        """The rows the statement changed; of executemany, the rows of every statement."""
        return self._cursor.rowcount

    def fetchone(self) -> Any:
        """The next row, or None: typed as with sqlite3, so that a row unpacks as it does there."""
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        """The rows left."""
        return self._cursor.fetchall()

    def __iter__(self) -> Iterator[Any]:
        """The rows left, one by one."""
        return iter(self._cursor)


class PostgresConnection:
    """A connection of psycopg with the methods of a connection of sqlite3 that K-B uses; each
    statement is translated, and always given parameters: psycopg turns %% back into % only then."""

    def __init__(self, connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        """Wrap an open connection of psycopg, out of autocommit: a transaction opens at the first
        statement, as with sqlite3."""
        self._connection = connection

    def execute(self, sql: str, parameters: Parameters = ()) -> PostgresCursor:
        """Run one statement of K-B."""
        return PostgresCursor(
            self._connection.execute(translate_placeholders(sql), parameters)
        )

    def executemany(self, sql: str, parameters: Iterable[Parameters]) -> PostgresCursor:
        """Run one statement of K-B for each set of parameters."""
        cursor = self._connection.cursor()
        cursor.executemany(translate_placeholders(sql), parameters)
        return PostgresCursor(cursor)

    def executescript(self, script: str) -> None:
        """Run a script of several statements as written: without parameters, psycopg sends it
        whole and reads no placeholder in it (the schema)."""
        self._connection.execute(script)

    @property
    def in_transaction(self) -> bool:
        """Whether a transaction is open, an error in it included (#302)."""
        return self._connection.info.transaction_status in OPEN_TRANSACTION_STATUSES

    def commit(self) -> None:
        """Commit the transaction."""
        self._connection.commit()

    def rollback(self) -> None:
        """Undo the transaction."""
        self._connection.rollback()

    def close(self) -> None:
        """Close the connection; a transaction still open is undone by the server."""
        self._connection.close()


def connect_postgresql(location: PostgresUrl) -> PostgresConnection:
    """Open the base of the URL, with a bound on the wait for its server.

    A URL libpq cannot read is refused by an error of K-B without the text of libpq, which quotes
    the whole URL, its password included."""
    try:
        connection = psycopg.connect(
            location.value, connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS
        )
    except psycopg.ProgrammingError:
        raise make_unreadable_url_error() from None
    return PostgresConnection(connection)


def make_unreadable_url_error() -> UnreadableDatabaseUrlError:
    """The refusal of a URL libpq cannot read, which names the variable only: the text of libpq
    quotes the whole URL, its password included, and is never chained (raise … from None)."""
    return UnreadableDatabaseUrlError(
        f"{DATABASE_URL_VARIABLE} is not a URL libpq reads"
    )


def lock_for_writing(connection: PostgresConnection) -> None:
    """Wait for the lock of the writers, until the end of the transaction, for at most the
    timeout of sqlite3 (core/config.py): past it, PostgreSQL raises 55P03."""
    milliseconds = round(DATABASE_LOCK_TIMEOUT_SECONDS * 1000)
    connection.execute(SET_LOCK_TIMEOUT, (f"{milliseconds}ms",))
    connection.execute(LOCK_FOR_WRITING, (WRITING_LOCK_KEY,))


# The pool of connections the data API reads with.
type ReadingPool = ConnectionPool[psycopg.Connection[tuple[Any, ...]]]


@contextmanager
def open_reading_pool(
    location: PostgresUrl, query_timeout_seconds: float
) -> Iterator[ReadingPool]:
    """The pool of the readers of the base, open until the end of the block; it connects in the
    background, so that kb serve-data starts without waiting for the base, as on SQLite.

    The URL is read before: a URL libpq cannot read is refused by an error of K-B without the text
    of libpq, which quotes it; the pool would otherwise fail on it in the background."""
    milliseconds = round(query_timeout_seconds * 1000)
    if milliseconds < MIN_STATEMENT_TIMEOUT_MILLISECONDS:
        raise ValueError(
            "query timeout below 1 ms: statement_timeout at 0 disables the deadline"
        )
    try:
        conninfo_to_dict(location.value)
    except psycopg.ProgrammingError:
        raise make_unreadable_url_error() from None
    pool: ReadingPool = ConnectionPool(
        location.value,
        kwargs={"connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS},
        min_size=READING_POOL_MIN_SIZE,
        max_size=READING_POOL_MAX_SIZE,
        timeout=READING_POOL_WAIT_SECONDS,
        configure=partial(configure_reader, statement_timeout=f"{milliseconds}ms"),
        # A connection a restart or a failover of the server closed is not lent.
        check=ConnectionPool.check_connection,
        name="k-b-readers",
        open=False,
    )
    pool.open(wait=False)
    try:
        yield pool
    finally:
        pool.close()


def configure_reader(
    connection: psycopg.Connection[tuple[Any, ...]], statement_timeout: str
) -> None:
    """Make a new connection of the pool a reader: each transaction in REPEATABLE READ READ ONLY,
    each statement within its deadline; it is left without transaction, or the pool discards it.

    The attributes first: psycopg refuses them once a transaction is open."""
    connection.isolation_level = IsolationLevel.REPEATABLE_READ
    connection.read_only = True
    reader = PostgresConnection(connection)
    reader.execute(SET_STATEMENT_TIMEOUT, (statement_timeout,))
    # A rollback would undo the setting.
    reader.commit()


@contextmanager
def borrow_reader(pool: ReadingPool) -> Iterator[PostgresConnection]:
    """A connection of the pool for one request, waited for at most READING_POOL_WAIT_SECONDS
    (PoolTimeout), its transaction ended here, on a success as on an error: the pool would
    otherwise undo it itself and log the connection, its host and user.

    A session the server ended before the rollback is logged by the type of the error, the
    connection closed for the pool to replace: the request keeps its response or its own
    error."""
    connection = pool.getconn()
    reader = PostgresConnection(connection)
    try:
        yield reader
    finally:
        try:
            # A connection psycopg knows closed has no transaction left to end.
            if reader.in_transaction:
                reader.rollback()
        except psycopg.Error as error:
            # The type only: the message of libpq may name the server.
            logger.warning("%s: %s", READER_SESSION_LOST, type(error).__name__)
            connection.close()
        finally:
            pool.putconn(connection)
