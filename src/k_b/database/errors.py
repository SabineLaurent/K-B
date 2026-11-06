"""The errors of the items database: the one its engine raises, and those due to an entry, that
an import turns into a rejection (conventions.md, rule 1)."""

import sqlite3

# The root of the errors of sqlite3, wider than sqlite3.DatabaseError (PEP 249: InterfaceError
# does not descend from it): any error of the base, a refused constraint as a full disk.
EngineError = sqlite3.Error

# The constraints an entry breaks by its own values, the only ones an import turns into a
# rejection (conventions.md, rule 1), with a value Python cannot hand to SQLite (an integer
# beyond 64 bits, a lone surrogate). A FOREIGN KEY, a PRIMARY KEY or a type of a STRICT table
# refused is not due to the entry: its writer chose the rows it points to, its key and the types
# of its values; the writer or the schema is wrong, and the import stops, as on an error of the
# system (full disk, locked base).
ENTRY_CONSTRAINT_ERROR_NAMES = frozenset(
    {"SQLITE_CONSTRAINT_CHECK", "SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_NOTNULL"}
)


def is_entry_refusal(error: BaseException) -> bool:
    """Tell whether the error refuses this entry only, so that the import goes on."""
    if isinstance(error, sqlite3.IntegrityError):
        return error.sqlite_errorname in ENTRY_CONSTRAINT_ERROR_NAMES
    return isinstance(error, (OverflowError, UnicodeEncodeError))


def describe_refusal(error: BaseException) -> str:
    """What the base refused, without the value refused: a constraint by its state and the
    message of SQLite, which names the constraint, never the value; a UnicodeEncodeError by its
    reason and position, as its text quotes the character."""
    if isinstance(error, sqlite3.IntegrityError):
        return f"{error.sqlite_errorname}: {' '.join(str(error).split())}"
    if isinstance(error, UnicodeEncodeError):
        return f"UnicodeEncodeError: {error.reason} at position {error.start}"
    return f"{type(error).__name__}: {error}"


def is_query_timeout(error: EngineError) -> bool:
    """Whether the deadline stopped the reading, the only interruption of a connection of the data
    API; an error raised by Python, not by SQLite, has no code."""
    return getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
