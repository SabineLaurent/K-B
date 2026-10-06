"""The items database: create it, and open a connection that checks its foreign keys."""

import sqlite3
from importlib.resources import files
from pathlib import Path

DATABASE_FILE_NAME = "k-b.sqlite"
DATABASE_SCRIPTS = files("k_b.database")


def connect_database(database_path: Path) -> sqlite3.Connection:
    """Open the database; SQLite ignores foreign keys unless each connection turns them on."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_database(database_path: Path) -> None:
    """Create the tables and the sources; refuse an existing file, which is left untouched.

    A creation that fails leaves no file behind: a half-built database would look valid and
    block the next attempt.
    """
    if database_path.exists():
        raise FileExistsError(f"{database_path} already exists")
    try:
        connection = connect_database(database_path)
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
