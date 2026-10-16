"""Write an item in a savepoint of the import's transaction: an entry the base refuses is undone
alone, and the import goes on (conventions.md, rule 1).

SAVEPOINT, ROLLBACK TO SAVEPOINT and RELEASE SAVEPOINT are written the same in SQLite and in
PostgreSQL (poc.md, rule 1).
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

# The errors due to the entry, the only ones an import turns into a rejection: a constraint of the
# base (CHECK, UNIQUE, NOT NULL, FOREIGN KEY), and a value Python cannot hand to SQLite (an
# integer beyond 64 bits, a lone surrogate). An error of the system (full disk, locked base) is
# not one: it stops the import.
ENTRY_REFUSAL_ERRORS = (sqlite3.IntegrityError, OverflowError, UnicodeEncodeError)


class NoTransactionError(RuntimeError):
    """A savepoint outside a transaction would begin one, and its release would commit it."""


@contextmanager
def write_in_savepoint(connection: sqlite3.Connection) -> Iterator[None]:
    """Keep what the block writes, or undo it alone on any exception, raised again.

    SQLite undoes the whole transaction on some errors (a full disk, an I/O error): no savepoint
    is then left to roll back to, and the error of the base is raised unchanged.
    """
    if not connection.in_transaction:
        raise NoTransactionError(
            "a savepoint is written inside the import's transaction"
        )
    connection.execute("SAVEPOINT entry")
    try:
        yield
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK TO SAVEPOINT entry")
            connection.execute("RELEASE SAVEPOINT entry")
        raise
    connection.execute("RELEASE SAVEPOINT entry")


def describe_refusal(error: Exception) -> str:
    """What the base refused, without the value refused (conventions.md, rule 3).

    A constraint is named by its state and by the message of SQLite, which names the constraint
    and not the value, on one line. The text of a UnicodeEncodeError quotes the character
    refused: only its reason and position are kept. Neither it nor an OverflowError names the
    field.
    """
    if isinstance(error, sqlite3.IntegrityError):
        return f"{error.sqlite_errorname}: {' '.join(str(error).split())}"
    if isinstance(error, UnicodeEncodeError):
        return f"UnicodeEncodeError: {error.reason} at position {error.start}"
    return f"{type(error).__name__}: {error}"
