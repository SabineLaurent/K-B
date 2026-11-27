"""Create the items database from its SQL scripts: schema.sql in a SQLite file, or
schema_postgresql.sql in a PostgreSQL base, then the sources; and kb migrate-database, which creates
a base that has no tables yet, its tables granted to the roles of the base online, and leaves one
that has them as it is."""

from importlib.resources import files
from pathlib import Path

from k_b.core.quoting import quote_value
from k_b.database.engine import Connection, connect_database, connect_sqlite
from k_b.database.location import DatabaseLocation, PostgresUrl
from k_b.database.postgresql import SELECT_SOURCE_TABLE

DATABASE_SCRIPTS = files("k_b.database")

# The settings the base was created with, which kb create-db does not choose: the server creates a
# base, kb creates its tables.
SELECT_DATABASE_SETTINGS = """
SELECT pg_encoding_to_char(encoding), datlocprovider, datcollate, datctype, datlocale
FROM pg_database WHERE datname = current_database()
"""
# UTF8: in SQL_ASCII, psycopg reads bytes and length() counts bytes. The collation C, of libc or
# of the builtin provider: text sorts and compares byte by byte, as in SQLite, and citext folds
# the case of ASCII letters alone, as COLLATE NOCASE (docs/stockage.md).
UTF8 = "UTF8"
LIBC_PROVIDER = "c"
BUILTIN_PROVIDER = "b"
C_LOCALE = "C"


class ExistingDatabaseError(Exception):
    """The PostgreSQL base already has the tables of K-B: kb create-db never writes over them."""


class UnsuitableDatabaseError(Exception):
    """The PostgreSQL base was created with other settings than those K-B needs."""


def create_database(location: DatabaseLocation) -> None:
    """Create the tables and the sources in the base of the location."""
    if isinstance(location, Path):
        create_sqlite_database(location)
        return
    create_postgresql_database(location)


def create_sqlite_database(database_path: Path) -> None:
    """Create the tables and the sources; refuse an existing file, and leave no file behind on
    failure: a half-built database would look valid and block the next attempt."""
    if database_path.exists():
        raise FileExistsError(f"{database_path} already exists")
    try:
        connection = connect_sqlite(database_path)
        try:
            # Kept in the file: the pipeline writes while the API reads (docs/stockage.md).
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                DATABASE_SCRIPTS.joinpath("schema.sql").read_text()
            )
            connection.executescript(
                DATABASE_SCRIPTS.joinpath("seed_sources.sql").read_text()
            )
        finally:
            connection.close()
    except BaseException:
        # BaseException: Ctrl-C during the creation must not leave a half-built file either.
        for suffix in ("", "-wal", "-shm"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
        raise


def create_postgresql_database(location: PostgresUrl) -> None:
    """Create the tables and the sources in one transaction, in a base of the settings K-B needs
    and without its tables yet; on any failure, the transaction undone leaves the base empty."""
    connection = connect_database(location)
    try:
        if has_its_tables(connection):
            raise ExistingDatabaseError("the PostgreSQL base already has its tables")
        write_postgresql_schema(connection)
        connection.commit()
    finally:
        # A transaction not committed is undone by the server.
        connection.close()


def migrate_database(location: DatabaseLocation) -> bool:
    """Create the base of the location when it has no tables yet, and say whether it did: a base
    that has them is left as it is, nothing written.

    On PostgreSQL, the tables are granted to the roles of the base online in the same transaction:
    their owner, the role of kb migrate-database, is the one that can."""
    if isinstance(location, Path):
        if location.exists():
            return False
        create_sqlite_database(location)
        return True
    connection = connect_database(location)
    try:
        if has_its_tables(connection):
            return False
        write_postgresql_schema(connection)
        connection.executescript(
            DATABASE_SCRIPTS.joinpath("grants_postgresql.sql").read_text()
        )
        connection.commit()
    finally:
        # A reading or a transaction not committed is undone by the server.
        connection.close()
    return True


def has_its_tables(connection: Connection) -> bool:
    """Whether the base, checked to have the settings K-B needs, already has the tables of K-B."""
    check_database_settings(connection.execute(SELECT_DATABASE_SETTINGS).fetchone())
    (has_tables,) = connection.execute(SELECT_SOURCE_TABLE).fetchone()
    return bool(has_tables)


def write_postgresql_schema(connection: Connection) -> None:
    """Write the tables and the sources, in the transaction of the connection."""
    connection.executescript(
        DATABASE_SCRIPTS.joinpath("schema_postgresql.sql").read_text()
    )
    connection.executescript(DATABASE_SCRIPTS.joinpath("seed_sources.sql").read_text())


def check_database_settings(settings: tuple[str | bytes | None, ...]) -> None:
    """Refuse a base that is not in UTF8 and in the collation C."""
    # In a base in SQL_ASCII, psycopg reads every text as bytes.
    encoding, provider, collation, character_type, locale = (
        value.decode() if isinstance(value, bytes) else value for value in settings
    )
    if encoding != UTF8:
        raise UnsuitableDatabaseError(
            f"the PostgreSQL base is in the encoding {encoding}, not {UTF8}"
        )
    is_libc_c = provider == LIBC_PROVIDER and collation == character_type == C_LOCALE
    is_builtin_c = provider == BUILTIN_PROVIDER and locale == C_LOCALE
    if not (is_libc_c or is_builtin_c):
        # Each setting read: the one to change depends on the provider.
        raise UnsuitableDatabaseError(
            f"the PostgreSQL base is not in the collation {C_LOCALE}:"
            f" datlocprovider {quote_value(provider)}, datcollate {quote_value(collation)},"
            f" datctype {quote_value(character_type)}, datlocale {quote_value(locale)}"
        )
