"""The fabricated Zotero library, shared by the tests of the source and of the command line."""

import sqlite3
from pathlib import Path

import pytest

ZOTERO_LIBRARY_SCRIPT = Path(__file__).parent / "fixtures" / "zotero_extract.sql"


def run_on_library(zotero_dir, script):
    """Run an SQL script on the library of zotero_dir, in WAL mode as Zotero's own base."""
    connection = sqlite3.connect(zotero_dir / "zotero.sqlite")
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(script)
    finally:
        connection.close()


@pytest.fixture
def zotero_dir(tmp_path):
    """A Zotero data directory with the fabricated library, closed cleanly."""
    directory = tmp_path / "Zotero"
    directory.mkdir()
    run_on_library(directory, ZOTERO_LIBRARY_SCRIPT.read_text())
    return directory


@pytest.fixture
def run_on_zotero_library():
    """Change the fabricated library of a test with an SQL script."""
    return run_on_library
