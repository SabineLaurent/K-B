"""The errors of the items database: those its engines raise, and those due to an entry, that an
import turns into a rejection (conventions.md, rule 1)."""

import sqlite3

import psycopg

# The roots of the errors of each engine, for except and isinstance. sqlite3.Error is wider than
# sqlite3.DatabaseError (PEP 249: InterfaceError does not descend from it): any error of the base,
# a refused constraint as a full disk.
ENGINE_ERRORS = (sqlite3.Error, psycopg.Error)
# The same, for an annotation: an except never takes it (TypeError once an error comes).
EngineError = sqlite3.Error | psycopg.Error

# The constraints an entry breaks by its own values, the only ones an import turns into a
# rejection (conventions.md, rule 1), with a value Python cannot hand to the base (an integer
# beyond 64 bits, a lone surrogate). A FOREIGN KEY, a PRIMARY KEY or a type of a STRICT table
# refused is not due to the entry: its writer chose the rows it points to, its key and the types
# of its values; the writer or the schema is wrong, and the import stops, as on an error of the
# system (full disk, locked base).
ENTRY_CONSTRAINT_ERROR_NAMES = frozenset(
    {"SQLITE_CONSTRAINT_CHECK", "SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_NOTNULL"}
)
# The same on PostgreSQL: check_violation, unique_violation, not_null_violation, and
# numeric_value_out_of_range, which a bigint column raises on an integer beyond 64 bits.
ENTRY_SQLSTATES = frozenset({"23514", "23505", "23502", "22003"})
UNIQUE_VIOLATION = "23505"
# The name PostgreSQL gives the constraint of a primary key, <table>_pkey: schema_postgresql.sql
# names none itself (tests/test_schema_postgresql.py).
PRIMARY_KEY_SUFFIX = "_pkey"


def is_entry_refusal(error: BaseException) -> bool:
    """Tell whether the error refuses this entry only, so that the import goes on."""
    if isinstance(error, sqlite3.IntegrityError):
        return error.sqlite_errorname in ENTRY_CONSTRAINT_ERROR_NAMES
    if isinstance(error, psycopg.Error):
        return error.sqlstate in ENTRY_SQLSTATES and not is_primary_key_refusal(error)
    return isinstance(error, (OverflowError, UnicodeEncodeError))


def is_primary_key_refusal(error: psycopg.Error) -> bool:
    """Whether PostgreSQL refused a key already taken by a primary key."""
    constraint_name = error.diag.constraint_name or ""
    return error.sqlstate == UNIQUE_VIOLATION and constraint_name.endswith(
        PRIMARY_KEY_SUFFIX
    )


def describe_refusal(error: BaseException) -> str:
    """What the base refused, without the value refused: a constraint by its state and the
    message of SQLite, which names the constraint, never the value; on PostgreSQL by its SQLSTATE
    and primary message, never its DETAIL, which quotes the row refused; a UnicodeEncodeError by
    its reason and position, as its text quotes the character."""
    if isinstance(error, sqlite3.IntegrityError):
        return f"{error.sqlite_errorname}: {' '.join(str(error).split())}"
    if isinstance(error, psycopg.Error):
        return f"{error.sqlstate}: {error.diag.message_primary}"
    if isinstance(error, UnicodeEncodeError):
        return f"UnicodeEncodeError: {error.reason} at position {error.start}"
    return f"{type(error).__name__}: {error}"


def describe_engine_error(error: EngineError) -> str:
    """An error of the base, for the log of a command: as SQLite gives it; on PostgreSQL by its
    class, its SQLSTATE and its primary message, never its DETAIL, which quotes the row refused; an
    error of psycopg without SQLSTATE by its class alone, as its text may quote the URL of the
    base, password included."""
    if not isinstance(error, psycopg.Error):
        return f"{type(error).__name__}: {error}"
    if error.sqlstate is None:
        return type(error).__name__
    return f"{type(error).__name__} {error.sqlstate}: {error.diag.message_primary}"


def is_query_timeout(error: EngineError) -> bool:
    """Whether the deadline stopped the reading, the only interruption of a connection of the data
    API; an error raised by Python, not by SQLite, has no code."""
    return getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
