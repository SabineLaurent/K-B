"""The PostgreSQL branch of the engine: a connection of psycopg 3 that the modules of K-B use as one
of sqlite3, its SQL translated to the placeholders of psycopg, and the lock of the writers."""

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

import psycopg
from psycopg import pq

from k_b.core.config import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DATABASE_LOCK_TIMEOUT_SECONDS,
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
# the other, as behind the write lock of SQLite; the purges do not take it yet (#418). The key is
# any one number, the same for every writer: the bytes "k-b" read as an integer.
WRITING_LOCK_KEY = int.from_bytes(b"k-b")
SET_LOCK_TIMEOUT = "SELECT set_config('lock_timeout', ?, true)"
LOCK_FOR_WRITING = "SELECT pg_advisory_xact_lock(?)"

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
        raise UnreadableDatabaseUrlError(
            f"{DATABASE_URL_VARIABLE} is not a URL libpq reads"
        ) from None
    return PostgresConnection(connection)


def lock_for_writing(connection: PostgresConnection) -> None:
    """Wait for the lock of the writers, until the end of the transaction, for at most the
    timeout of sqlite3 (core/config.py): past it, PostgreSQL raises 55P03."""
    milliseconds = round(DATABASE_LOCK_TIMEOUT_SECONDS * 1000)
    connection.execute(SET_LOCK_TIMEOUT, (f"{milliseconds}ms",))
    connection.execute(LOCK_FOR_WRITING, (WRITING_LOCK_KEY,))
