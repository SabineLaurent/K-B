"""Read the items database."""

import sqlite3

SELECT_RAW_FILE_PATHS = "SELECT raw_file_path FROM raw_data"


def read_raw_file_paths(connection: sqlite3.Connection) -> frozenset[str]:
    """The raw files already imported: raw_data is their registry, one row per file (#106)."""
    return frozenset(
        str(raw_file_path)
        for (raw_file_path,) in connection.execute(SELECT_RAW_FILE_PATHS)
    )
