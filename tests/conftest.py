"""The fabricated Zotero library, shared by the tests of the source and of the command line; the
test base of the readers of the items; the settings of kb read from the terminal, removed; the
end-to-end tests, left out unless -m names them."""

import re
import sqlite3
from pathlib import Path

import pytest

from k_b.database.connection import connect_database
from k_b.database.creation import create_database

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ZOTERO_LIBRARY_SCRIPT = FIXTURES_DIR / "zotero_extract.sql"
ITEMS_DATABASE_SCRIPT = FIXTURES_DIR / "items_database.sql"
# The settings of kb serve and of the log, which a terminal may export (a .env loaded).
KB_SETTINGS_VARIABLES = (
    "KB_DATA_API_HOST",
    "KB_DATA_API_PORT",
    "KB_DATA_API_ALLOWED_HOSTS",
    "KB_LOG_TO_FILE",
)
# The marker of the tests that run kb on the real sources (tests/e2e/).
E2E_MARKER = "e2e"
# A marker name of a -m expression, by the rule ident of pytest's grammar
# (_pytest/mark/expression.py:10, pytest 9.1.1): nightly-e2e and e2e.slow are one name each.
MARKER_NAME = re.compile(r"(?:\w|:|\+|-|\.|\[|\]|\\|/)+")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{E2E_MARKER}: runs kb on a real source; left out unless -m names {E2E_MARKER}",
    )


def pytest_collection_modifyitems(config, items):
    """Leave out the end-to-end tests unless -m names them: uv run pytest, the command of the
    CI, never calls a real source; uv run pytest -m e2e runs them."""
    # The name e2e, not a marker name that holds it (nightly_e2e, nightly-e2e, e2e.slow).
    if E2E_MARKER in MARKER_NAME.findall(config.option.markexpr):
        return
    deselected = [item for item in items if item.get_closest_marker(E2E_MARKER)]
    if not deselected:
        return
    config.hook.pytest_deselected(items=deselected)
    items[:] = [item for item in items if not item.get_closest_marker(E2E_MARKER)]


@pytest.fixture
def connect_with_factory():
    """connect_database, opening a subclass of sqlite3.Connection: the tests change its commit."""

    def connect_with(factory):
        def connect(database_path):
            connection = sqlite3.connect(database_path, factory=factory)
            connection.execute("PRAGMA foreign_keys = ON")
            return connection

        return connect

    return connect_with


@pytest.fixture(autouse=True)
def no_kb_setting_of_the_terminal(monkeypatch):
    """A terminal that exports a setting of kb must not change what the tests check."""
    for name in KB_SETTINGS_VARIABLES:
        monkeypatch.delenv(name, raising=False)


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
    holds a space, #, ? and %, which its URI must escape. Read only: no test writes in it."""
    database_dir = tmp_path_factory.mktemp("data dir #1 ?%", numbered=False)
    database_path = database_dir / "k-b.sqlite"
    create_database(database_path)
    connection = connect_database(database_path)
    try:
        connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
    finally:
        connection.close()
    return database_path
