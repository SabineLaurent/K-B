"""Open a connection to the items database that checks its foreign keys."""

import sqlite3
from pathlib import Path

DATABASE_FILE_NAME = "k-b.sqlite"


def connect_database(database_path: Path) -> sqlite3.Connection:
    """Open the database; SQLite ignores foreign keys unless each connection turns them on."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
