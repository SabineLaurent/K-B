"""The fabricated Zotero library, shared by the tests of the source and of the command line; the
test base of the readers of the items."""

import sqlite3
from pathlib import Path

import pytest

from k_b.database.connection import connect_database
from k_b.database.creation import create_database

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ZOTERO_LIBRARY_SCRIPT = FIXTURES_DIR / "zotero_extract.sql"
ITEMS_DATABASE_SCRIPT = FIXTURES_DIR / "items_database.sql"


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


@pytest.fixture(scope="session")
def items_database(tmp_path_factory):
    """The path of the test base of the readers, built once for the session; its folder name
    holds a space and a #, which its URI must escape. Read only: no test writes in it."""
    database_dir = tmp_path_factory.mktemp("data dir #1", numbered=False)
    database_path = database_dir / "k-b.sqlite"
    create_database(database_path)
    connection = connect_database(database_path)
    try:
        connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
    finally:
        connection.close()
    return database_path
