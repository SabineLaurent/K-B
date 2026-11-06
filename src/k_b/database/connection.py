"""The file of the items database: its name, and the check that it exists before a connection
opens it."""

from pathlib import Path

DATABASE_FILE_NAME = "k-b.sqlite"


class MissingDatabaseError(FileNotFoundError):
    """The database file does not exist yet: kb create-db creates it."""


def check_database_exists(database_path: Path) -> None:
    """Connecting to a missing file would create an empty base."""
    if not database_path.is_file():
        raise MissingDatabaseError(f"{database_path} does not exist")
