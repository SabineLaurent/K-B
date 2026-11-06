"""Where the items database is: the SQLite file of the data directory, or the PostgreSQL base
KB_DATABASE_URL names; and the check that the file exists before a connection opens it."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from k_b.core.config import DATABASE_FILE_NAME

DATABASE_URL_VARIABLE = "KB_DATABASE_URL"
POSTGRESQL_URL_PREFIXES = ("postgresql://", "postgres://")
# The variables libpq reads besides the URL it is given: PostgreSQL 18, 32.15 "Environment
# Variables" (https://www.postgresql.org/docs/18/libpq-envars.html, read on 2026-11-06). kb reads its
# settings in its own variables only (.claude/rules/poc.md, rule 2); PGDATA, a variable of the
# server that Homebrew sets, is not one of them (decision of Sabine of 2026-11-06).
LIBPQ_VARIABLES = frozenset(
    {
        # The defaults of the parameters of a connection.
        "PGHOST",
        "PGSSLNEGOTIATION",
        "PGHOSTADDR",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGPASSFILE",
        "PGREQUIREAUTH",
        "PGCHANNELBINDING",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGOPTIONS",
        "PGAPPNAME",
        "PGSSLMODE",
        "PGREQUIRESSL",
        "PGSSLCOMPRESSION",
        "PGSSLCERT",
        "PGSSLKEY",
        "PGSSLCERTMODE",
        "PGSSLROOTCERT",
        "PGSSLCRL",
        "PGSSLCRLDIR",
        "PGSSLSNI",
        "PGREQUIREPEER",
        "PGSSLMINPROTOCOLVERSION",
        "PGSSLMAXPROTOCOLVERSION",
        "PGGSSENCMODE",
        "PGKRBSRVNAME",
        "PGGSSLIB",
        "PGGSSDELEGATION",
        "PGCONNECT_TIMEOUT",
        "PGCLIENTENCODING",
        "PGTARGETSESSIONATTRS",
        "PGLOADBALANCEHOSTS",
        "PGMINPROTOCOLVERSION",
        "PGMAXPROTOCOLVERSION",
        # The default behavior of each session.
        "PGDATESTYLE",
        "PGTZ",
        "PGGEQO",
        # The internal behavior of libpq.
        "PGSYSCONFDIR",
        "PGLOCALEDIR",
    }
)


@dataclass(frozen=True)
class PostgresUrl:
    """The URL of a PostgreSQL base, as libpq reads it; never shown: it may hold a password."""

    value: str = field(repr=False)


# The SQLite file of a base, or the URL of a PostgreSQL one.
DatabaseLocation = Path | PostgresUrl


class UnreadableDatabaseUrlError(Exception):
    """KB_DATABASE_URL is not a URL libpq reads: a setting refused, as one that names no PostgreSQL
    base."""


class MissingDatabaseError(FileNotFoundError):
    """The database file does not exist yet: kb create-db creates it."""


def read_database_location_or_refusal(
    environ: Mapping[str, str], data_dir: Path
) -> Path | PostgresUrl | str:
    """The base of KB_DATABASE_URL, or the SQLite file of the data directory when it is not set, or
    why the setting is refused; the value is never quoted, as it may hold a password."""
    value = environ.get(DATABASE_URL_VARIABLE)
    if value is None:
        return data_dir / DATABASE_FILE_NAME
    # An empty value too: a secret not given to a container must not send the import to SQLite.
    if not value.startswith(POSTGRESQL_URL_PREFIXES):
        return (
            f"{DATABASE_URL_VARIABLE} is neither a postgresql:// nor a postgres:// URL"
        )
    libpq_variables_set = sorted(LIBPQ_VARIABLES & environ.keys())
    if libpq_variables_set:
        return (
            f"{', '.join(libpq_variables_set)} set: libpq reads these variables besides"
            f" {DATABASE_URL_VARIABLE}"
        )
    return PostgresUrl(value)


def describe_location(location: DatabaseLocation) -> str:
    """The base for a message: the path of its file, or no part of the URL of a PostgreSQL base: a
    character the URL does not encode (a slash, a fullwidth one) moves a part of the password into
    its path, or into the text of the error of urlsplit."""
    if isinstance(location, Path):
        return str(location)
    return f"the PostgreSQL base of {DATABASE_URL_VARIABLE}"


def check_database_exists(location: DatabaseLocation) -> None:
    """Connecting to a missing file would create an empty base; the server of a PostgreSQL base
    answers for it at the first query."""
    if isinstance(location, Path) and not location.is_file():
        raise MissingDatabaseError(f"{location} does not exist")
