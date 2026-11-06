"""kb create-db, then kb import, write the same rows on PostgreSQL as on SQLite, from the same raw
files: the withdrawals of CISA KEV and of Zotero, and an extract without highlight, included."""

import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime

import psycopg
import pytest
from commands.cli_helpers import make_clock
from load_helpers import (
    ADVISORIES_DIR,
    ARXIV_DIR,
    CISA_KEV_DIR,
    RELEASES_DIR,
    WITHDRAWN_CVE_ID,
    kev_catalog,
    write_collection,
)
from test_load_clips import ARTICLE, fixture_text, with_tags, write_clip
from test_load_tldr import TLDR_AI_PAGE, write_tldr_page
from test_load_trends import RANKING, write_ranking
from test_load_zotero import (
    FIRST_PAGE_HIGHLIGHT,
    SECOND_DOCUMENT,
    THIRD_PAGE_HIGHLIGHT,
    delete_in_zotero,
    extract_of,
    write_extract,
)
from test_transform import FIXTURES_DIR

from k_b import cli
from k_b.commands import import_command
from k_b.commands.exit_codes import ExitCode
from k_b.database import writing
from k_b.database.creation import DATABASE_SCRIPTS
from k_b.database.location import DATABASE_URL_VARIABLE

pytestmark = pytest.mark.postgresql

FIRST_COLLECTION = "2026-10-05T093000Z"
SECOND_COLLECTION = "2026-10-06T093000Z"
THIRD_COLLECTION = "2026-10-07T093000Z"
# Each import a day after the collection it reads; the last one four years later, once the watch
# is past its three years: the purge deletes it.
IMPORTS_AT = (
    datetime(2026, 10, 5, 12, tzinfo=UTC),
    datetime(2026, 10, 6, 12, tzinfo=UTC),
    datetime(2026, 10, 7, 12, tzinfo=UTC),
    datetime(2030, 10, 8, 12, tzinfo=UTC),
)
# The tables of schema.sql, in the order of their foreign keys, each with its key: its rows are
# compared in the order of that key, its id replaced by its rank.
TABLE_KEYS = {
    "source": "id",
    "raw_data": "id",
    "item": "id",
    "publication": "id",
    "highlight": "highlight_id",
    "trend": "id",
    "vulnerability": "id",
    "tracked_repository": "id",
    "release": "id",
    "advisory": "id",
    "newsletter_article": "id",
    "zotero_entry": "id",
    "clip": "id",
    "tag": "id",
    "item_has_tag": None,
}
# The table each foreign key points to: its value is replaced by the rank of the row it points to.
REFERENCED_TABLE_BY_COLUMN = {
    ("raw_data", "source_id"): "source",
    ("item", "raw_data_id"): "raw_data",
    ("publication", "item_id"): "item",
    ("highlight", "item_id"): "item",
    ("trend", "raw_data_id"): "raw_data",
    ("vulnerability", "item_id"): "item",
    ("release", "item_id"): "item",
    ("release", "tracked_repository_id"): "tracked_repository",
    ("advisory", "item_id"): "item",
    ("advisory", "vulnerability_id"): "vulnerability",
    ("newsletter_article", "item_id"): "item",
    ("newsletter_article", "publication_id"): "publication",
    ("zotero_entry", "item_id"): "item",
    ("zotero_entry", "publication_id"): "publication",
    ("clip", "item_id"): "item",
    ("item_has_tag", "item_id"): "item",
    ("item_has_tag", "tag_id"): "tag",
}


@pytest.fixture(autouse=True)
def temporary_root(tmp_path, monkeypatch):
    """The copy of the Zotero library is made here, not in the temporary folder of the system."""
    root = tmp_path / "temporary"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))


@pytest.fixture
def engines(tmp_path, postgresql_base):
    """A data directory for each engine, with nothing in it yet; the value of KB_DATABASE_URL of
    each, None for SQLite."""
    sqlite_dir = tmp_path / "sqlite"
    postgresql_dir = tmp_path / "postgresql"
    sqlite_dir.mkdir()
    postgresql_dir.mkdir()
    return {sqlite_dir: None, postgresql_dir: postgresql_base.value}


def run_kb(monkeypatch, data_dir, database_url, command, now=None):
    """Run a kb command on the data directory and the base given, its clock at now."""
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_LOG_TO_FILE", "false")
    if database_url is None:
        monkeypatch.delenv(DATABASE_URL_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(DATABASE_URL_VARIABLE, database_url)
    if now is not None:
        monkeypatch.setattr(import_command, "datetime", make_clock(now))
    return cli.main([command])


def write_first_collection(data_dir, zotero_extract):
    """Every source once: their raw files of the first collection."""
    for fixture, folder, extension in (
        ("arxiv_extract.xml", ARXIV_DIR, "xml"),
        ("cisa_kev_extract.csv", CISA_KEV_DIR, "csv"),
        ("github_releases_extract.json", RELEASES_DIR, "json"),
        ("github_advisories_extract.json", ADVISORIES_DIR, "json"),
    ):
        folder_dir = data_dir / "raw" / "automated_watch" / folder
        folder_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            FIXTURES_DIR / fixture, folder_dir / f"{FIRST_COLLECTION}.{extension}"
        )
    write_tldr_page(data_dir, "tldr_ai", FIRST_COLLECTION, TLDR_AI_PAGE)
    write_ranking(data_dir, FIRST_COLLECTION, RANKING["rows"])
    write_clip(
        data_dir,
        FIRST_COLLECTION,
        "article",
        with_tags(fixture_text(ARTICLE), "llm", "agents"),
    )
    write_extract(data_dir, FIRST_COLLECTION, zotero_extract)


def read_rows(data_dir, database_url):
    """Every table of the base, each row in the order of its key, each id replaced by its rank and
    each foreign key by the rank of its target: two engines that wrote the same rows give the same
    list, whatever ids each one gave."""
    connection = (
        sqlite3.connect(data_dir / "k-b.sqlite")
        if database_url is None
        else psycopg.connect(database_url)
    )
    try:
        tables = {
            table: read_table(connection, table, key)
            for table, key in TABLE_KEYS.items()
        }
    finally:
        connection.close()
    rank_by_id = {
        table: {row[key]: rank for rank, row in enumerate(rows)}
        for table, (key, rows) in tables.items()
        if key is not None
    }
    return {
        table: [
            {
                column: replace_id(table, column, key, value, rank_by_id)
                for column, value in row.items()
            }
            for row in rows
        ]
        for table, (key, rows) in tables.items()
    }


def read_table(connection, table, key):
    """The rows of a table as dictionaries, in the order of its key, or of all its columns."""
    columns = [row[1] for row in COLUMNS_BY_TABLE[table]]
    order = key or ", ".join(columns)
    # Names of schema.sql only: nothing from outside enters the statement.
    cursor = connection.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order}"  # noqa: S608
    )
    return key, [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def replace_id(table, column, key, value, rank_by_id):
    if value is None:
        return None
    if column == key:
        return rank_by_id[table][value]
    referenced_table = REFERENCED_TABLE_BY_COLUMN.get((table, column))
    if referenced_table is None:
        return value
    return rank_by_id[referenced_table][value]


def read_columns_by_table():
    """The columns of each table, read from a base schema.sql creates."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(DATABASE_SCRIPTS.joinpath("schema.sql").read_text())
        return {
            table: connection.execute(f"PRAGMA table_info({table})").fetchall()
            for table in TABLE_KEYS
        }
    finally:
        connection.close()


COLUMNS_BY_TABLE = read_columns_by_table()


def read_journals(data_dir):
    return {
        path.name: path.read_text()
        for path in sorted((data_dir / "journals").glob("import-journal-*.jsonl"))
    }


def import_on_both(monkeypatch, capsys, engines, now):
    """kb import on each engine at the same time; each prints the same summary, writes the same
    journals and leaves the same rows."""
    results = []
    for data_dir, database_url in engines.items():
        capsys.readouterr()
        exit_code = run_kb(monkeypatch, data_dir, database_url, "import", now)
        results.append(
            (
                exit_code,
                capsys.readouterr().out,
                read_journals(data_dir),
                read_rows(data_dir, database_url),
            )
        )
    sqlite_result, postgresql_result = results
    assert sqlite_result[0] == ExitCode.SUCCEEDED
    assert postgresql_result == sqlite_result
    return postgresql_result[3]


def test_kb_create_db_then_kb_import_write_the_same_rows_on_postgresql_as_on_sqlite(
    monkeypatch, capsys, engines, zotero_dir, run_on_zotero_library
):
    for data_dir, database_url in engines.items():
        assert (
            run_kb(monkeypatch, data_dir, database_url, "create-db")
            == ExitCode.SUCCEEDED
        )
    first_extract = extract_of(zotero_dir)
    for data_dir in engines:
        write_first_collection(data_dir, first_extract)

    first_rows = import_on_both(monkeypatch, capsys, engines, IMPORTS_AT[0])

    # A newer catalog without a CVE, and a newer extract without a document and one highlight.
    delete_in_zotero(
        run_on_zotero_library, zotero_dir, SECOND_DOCUMENT, FIRST_PAGE_HIGHLIGHT
    )
    second_extract = extract_of(zotero_dir)
    for data_dir in engines:
        write_collection(
            data_dir,
            CISA_KEV_DIR,
            SECOND_COLLECTION,
            kev_catalog(without=(WITHDRAWN_CVE_ID,)),
        )
        write_extract(data_dir, SECOND_COLLECTION, second_extract)
    second_rows = import_on_both(monkeypatch, capsys, engines, IMPORTS_AT[1])

    # A newer extract whose documents have no highlight left: the list of highlights present is
    # empty, and every highlight is withdrawn.
    delete_in_zotero(run_on_zotero_library, zotero_dir, THIRD_PAGE_HIGHLIGHT)
    third_extract = extract_of(zotero_dir)
    for data_dir in engines:
        write_extract(data_dir, THIRD_COLLECTION, third_extract)
    third_rows = import_on_both(monkeypatch, capsys, engines, IMPORTS_AT[2])

    # Four years later, the purges of kb import delete the watch past its duration.
    last_rows = import_on_both(monkeypatch, capsys, engines, IMPORTS_AT[3])

    # The scenario did what it says, on both engines.
    assert {row["kind"] for row in first_rows["item"]} == {
        "paper",
        "vulnerability",
        "release",
        "advisory",
        "newsletter_article",
        "zotero_entry",
        "clip",
    }
    assert first_rows["trend"] and first_rows["item_has_tag"]
    assert [
        row["cve_id"]
        for row in second_rows["vulnerability"]
        if row["withdrawn_at"] is not None
    ] == [WITHDRAWN_CVE_ID]
    assert any(row["withdrawn_at"] for row in second_rows["zotero_entry"])
    assert any(row["withdrawn_at"] for row in second_rows["highlight"])
    assert not any(row["withdrawn_at"] is None for row in third_rows["highlight"])
    assert {row["kind"] for row in last_rows["item"]} == {
        "vulnerability",
        "zotero_entry",
        "clip",
    }
    assert last_rows["trend"] == []


def test_a_foreign_key_postgresql_refuses_stops_the_import_writes_nothing_and_logs_no_row(
    monkeypatch, capsys, postgresql_base, tmp_path
):
    database_url = postgresql_base.value
    assert (
        run_kb(monkeypatch, tmp_path, database_url, "create-db") == ExitCode.SUCCEEDED
    )
    folder_dir = tmp_path / "raw" / "automated_watch" / CISA_KEV_DIR
    folder_dir.mkdir(parents=True)
    shutil.copyfile(
        FIXTURES_DIR / "cisa_kev_extract.csv", folder_dir / f"{FIRST_COLLECTION}.csv"
    )
    rows_before = read_rows(tmp_path, database_url)
    write_vulnerability = writing.WRITER_BY_KIND["vulnerability"]

    # A writer that points its item at a raw file the base does not have: not due to the entry,
    # it is not a rejection (an error of the system).
    def write_with_an_unknown_raw_file(connection, item, raw_data_id):
        return write_vulnerability(connection, item, raw_data_id + 1_000)

    monkeypatch.setitem(
        writing.WRITER_BY_KIND, "vulnerability", write_with_an_unknown_raw_file
    )
    capsys.readouterr()

    exit_code = run_kb(monkeypatch, tmp_path, database_url, "import", IMPORTS_AT[0])

    log = capsys.readouterr().err
    assert exit_code == ExitCode.FAILED
    assert "ForeignKeyViolation 23503" in log
    # The DETAIL of PostgreSQL quotes the row refused: never in the log.
    assert "DETAIL" not in log
    assert "Key (" not in log
    assert read_rows(tmp_path, database_url) == rows_before
    assert read_journals(tmp_path) == {}
