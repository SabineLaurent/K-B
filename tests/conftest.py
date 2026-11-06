"""What the tests share: the fabricated Zotero library, the test base of the readers on each engine,
the settings of the terminal removed, the end-to-end tests and those on PostgreSQL left out, a
fresh PostgreSQL base, and the HTML report."""

import html
import os
import re
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from k_b.core.config import DATA_API_QUERY_TIMEOUT_SECONDS
from k_b.database.creation import create_database
from k_b.database.engine import connect_database, open_readers
from k_b.database.location import LIBPQ_VARIABLES, PostgresUrl

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ZOTERO_LIBRARY_SCRIPT = FIXTURES_DIR / "zotero_extract.sql"
ITEMS_DATABASE_SCRIPT = FIXTURES_DIR / "items_database.sql"
# The settings of kb serve-data and of the log, which a terminal may export (a .env loaded).
# KB_DATABASE_URL among them: a terminal that exports it must not make the suite write into a real
# PostgreSQL base.
KB_SETTINGS_VARIABLES = (
    "KB_DATA_API_HOST",
    "KB_DATA_API_PORT",
    "KB_DATA_API_ALLOWED_HOSTS",
    "KB_LOG_TO_FILE",
    "KB_DATABASE_URL",
)
# The marker of the tests that run kb on the real sources (tests/e2e/).
E2E_MARKER = "e2e"
# The marker of the tests that need a PostgreSQL server, given by KB_TEST_POSTGRESQL_URL: the URL
# of a base of that server whose role may create and drop a base (the CI service, or a server of
# the developer's machine, never the base of production).
POSTGRESQL_MARKER = "postgresql"
POSTGRESQL_SERVER_VARIABLE = "KB_TEST_POSTGRESQL_URL"
# The markers -m must name for their tests to run.
MARKERS_LEFT_OUT_BY_DEFAULT = (E2E_MARKER, POSTGRESQL_MARKER)
# The engines a test of the reading runs on: its PostgreSQL half is left out unless -m names
# postgresql, as any test with the marker, never skipped.
ENGINES = ("sqlite", pytest.param("postgresql", marks=pytest.mark.postgresql))
# A marker name of a -m expression, by the rule ident of pytest's grammar
# (_pytest/mark/expression.py:10, pytest 9.1.1): nightly-e2e and e2e.slow are one name each.
MARKER_NAME = re.compile(r"(?:\w|:|\+|-|\.|\[|\]|\\|/)+")
# The HTML report keeps the captured output of every test: the user alone reads it
# (docs/registre-traitements.md, step 10 of the sorting). In the repository, only its folder
# is ignored by git (.gitignore).
REPORT_DIR_NAME = "reports"
REPORT_DIR_MODE = 0o700
REPORT_FILE_MODE = 0o600
# The column of the recorded properties, before the links (the last default column of
# pytest-html 4.2.0: result, test, duration, links).
PROPERTIES_COLUMN = 3


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{E2E_MARKER}: runs kb on a real source; left out unless -m names {E2E_MARKER}",
    )
    config.addinivalue_line(
        "markers",
        f"{POSTGRESQL_MARKER}: needs the PostgreSQL server of {POSTGRESQL_SERVER_VARIABLE};"
        f" left out unless -m names {POSTGRESQL_MARKER}",
    )
    restrict_report_to_user(config)


def restrict_report_to_user(config):
    """Create the report of --html in 0600, and its new folder in 0700, before pytest-html writes
    it in place; a report in the repository outside reports/, which git would not ignore, stops
    the run."""
    report_option = config.getoption("htmlpath", default=None)
    if not report_option:
        return
    # Resolved as pytest-html resolves it (BaseReport.__init__, pytest-html 4.2.0).
    report_path = Path.cwd() / Path(os.path.expandvars(report_option)).expanduser()
    resolved_path = report_path.resolve()
    repository_dir = config.rootpath.resolve()
    if resolved_path.is_relative_to(
        repository_dir
    ) and not resolved_path.is_relative_to(repository_dir / REPORT_DIR_NAME):
        pytest.exit(
            f"--html: {resolved_path} is in the repository outside {REPORT_DIR_NAME}/,"
            " which git does not ignore",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )
    report_path.parent.mkdir(mode=REPORT_DIR_MODE, parents=True, exist_ok=True)
    os.close(os.open(report_path, os.O_WRONLY | os.O_CREAT, REPORT_FILE_MODE))
    report_path.chmod(REPORT_FILE_MODE)


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells):
    cells.insert(PROPERTIES_COLUMN, "<th>Properties</th>")


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report, cells):
    """The properties the test recorded, one name=value a line, escaped."""
    properties = getattr(report, "user_properties", ())
    lines = "<br>".join(html.escape(f"{name}={value}") for name, value in properties)
    cells.insert(PROPERTIES_COLUMN, f'<td class="col-properties">{lines}</td>')


def pytest_collection_modifyitems(config, items):
    """Leave out the end-to-end tests and those on PostgreSQL unless -m names them, so that the CI
    never calls a real source, and the job without PostgreSQL never needs one."""
    # The name e2e, not a marker name that holds it (nightly_e2e, nightly-e2e, e2e.slow).
    named = set(MARKER_NAME.findall(config.option.markexpr))
    for marker in MARKERS_LEFT_OUT_BY_DEFAULT:
        if marker in named:
            continue
        deselected = [item for item in items if item.get_closest_marker(marker)]
        if not deselected:
            continue
        config.hook.pytest_deselected(items=deselected)
        items[:] = [item for item in items if not item.get_closest_marker(marker)]


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
    """A terminal that exports a setting of kb, or a variable libpq reads, must not change what the
    tests check."""
    for name in (*KB_SETTINGS_VARIABLES, *LIBPQ_VARIABLES):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def postgresql_server_url():
    """The URL of the test server; a test on PostgreSQL run without it fails, never skipped."""
    url = os.environ.get(POSTGRESQL_SERVER_VARIABLE)
    if not url:
        pytest.fail(
            f"{POSTGRESQL_SERVER_VARIABLE} must name the PostgreSQL server of the tests"
        )
    return url


def create_postgresql_base(server, server_url, encoding="UTF8", collation="C"):
    """Create a new base on the test server; its name and its URL."""
    name = f"kb_test_{uuid.uuid4().hex}"
    # Names and settings of the test only: nothing from outside enters the statement.
    server.execute(
        f"CREATE DATABASE {name} TEMPLATE template0 ENCODING '{encoding}'"
        f" LC_COLLATE '{collation}' LC_CTYPE '{collation}'"
    )
    parts = urlsplit(server_url)
    return name, PostgresUrl(urlunsplit(parts._replace(path=f"/{name}")))


@pytest.fixture(scope="module")
def make_postgresql_base(postgresql_server_url):
    """Create a new base on the test server, in UTF8 and collation C as kb create-db asks unless
    the test gives other settings; each one is dropped after the tests of its module."""
    created = []
    server = psycopg.connect(postgresql_server_url, autocommit=True)

    def make(encoding="UTF8", collation="C"):
        name, location = create_postgresql_base(
            server, postgresql_server_url, encoding, collation
        )
        created.append(name)
        return location

    yield make
    for name in created:
        server.execute(f"DROP DATABASE {name} WITH (FORCE)")
    server.close()


@pytest.fixture
def postgresql_base(make_postgresql_base):
    """A new, empty PostgreSQL base, as the compose or Azure gives it to kb create-db."""
    return make_postgresql_base()


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
    """The path of the test base of the readers, built once, read only; its folder name holds a
    space, #, ? and %, which its URI must escape."""
    database_dir = tmp_path_factory.mktemp("data dir #1 ?%", numbered=False)
    database_path = database_dir / "k-b.sqlite"
    create_database(database_path)
    connection = connect_database(database_path)
    try:
        connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
    finally:
        connection.close()
    return database_path


@pytest.fixture(scope="session")
def items_postgresql_base(postgresql_server_url):
    """The test base of the readers on PostgreSQL, built once, read only: the schema of
    kb create-db, then the rows of items_database.sql."""
    server = psycopg.connect(postgresql_server_url, autocommit=True)
    name, location = create_postgresql_base(server, postgresql_server_url)
    try:
        create_database(location)
        connection = connect_database(location)
        try:
            connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
            connection.commit()
        finally:
            connection.close()
        yield location
    finally:
        server.execute(f"DROP DATABASE {name} WITH (FORCE)")
        server.close()


@pytest.fixture(scope="session")
def items_postgresql_readers(items_postgresql_base):
    """The pool of the data API on the test base of the readers on PostgreSQL."""
    with open_readers(items_postgresql_base, DATA_API_QUERY_TIMEOUT_SECONDS) as readers:
        yield readers


@pytest.fixture(params=ENGINES)
def engine(request):
    """The engine of the test: SQLite, then PostgreSQL under -m postgresql."""
    return request.param


@pytest.fixture
def items_base(engine, request, items_database):
    """The test base of the readers on the engine of the test; the PostgreSQL one is asked for in
    its half only, so that the SQLite half never needs its server."""
    if engine == "sqlite":
        return items_database
    return request.getfixturevalue("items_postgresql_base")


@pytest.fixture
def items_readers(engine, request, items_database):
    """What the data API reads the test base of the readers through, on the engine of the test:
    the SQLite file, or the pool of the PostgreSQL base."""
    if engine == "sqlite":
        return items_database
    return request.getfixturevalue("items_postgresql_readers")


@pytest.fixture
def new_base(engine, request, tmp_path):
    """A new base, created by create_database on the engine of the test: its location."""
    location = (
        tmp_path / "k-b.sqlite"
        if engine == "sqlite"
        else request.getfixturevalue("postgresql_base")
    )
    create_database(location)
    return location
