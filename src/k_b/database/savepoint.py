"""Write an item in a savepoint of the import's transaction: an entry the base refuses is undone
alone, and the import goes on (conventions.md, rule 1)."""

from collections.abc import Iterator
from contextlib import contextmanager

from k_b.database.engine import Connection
from k_b.database.errors import describe_refusal, is_entry_refusal


class EntryRefusedError(Exception):
    """The base refused an entry: what it refused, without the value refused."""


class NoTransactionError(RuntimeError):
    """A savepoint outside a transaction would begin one, and its release would commit it."""


@contextmanager
def write_in_savepoint(connection: Connection) -> Iterator[None]:
    """Keep what the block writes, or undo it alone on any exception; an error due to the entry
    is raised again as an EntryRefusedError.

    On some errors (a full disk, an I/O error) SQLite undoes the whole transaction: the error is
    then raised unchanged."""
    if not connection.in_transaction:
        raise NoTransactionError(
            "a savepoint is written inside the import's transaction"
        )
    connection.execute("SAVEPOINT entry")
    try:
        yield
    except BaseException as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK TO SAVEPOINT entry")
            connection.execute("RELEASE SAVEPOINT entry")
        if is_entry_refusal(error):
            raise EntryRefusedError(describe_refusal(error)) from error
        raise
    connection.execute("RELEASE SAVEPOINT entry")
