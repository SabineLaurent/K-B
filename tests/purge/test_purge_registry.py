"""The purge of the registry: a row of raw_data whose raw file is gone and that nothing in the base
cites any more; the last catalog of a state catalog stays, read as such by the import."""

import logging
import shutil
import sqlite3
from pathlib import Path

import pytest

from k_b.database.creation import create_database
from k_b.database.engine import connect_database
from k_b.etl.raw_store import RawStore
from k_b.purge.registry import purge_registry

ITEMS_DATABASE_SCRIPT = Path(__file__).parents[1] / "fixtures" / "items_database.sql"
STATE_CATALOG_SOURCE_CODES = frozenset({"zotero", "cisa_kev"})
ARXIV_PATH = "automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"
RELEASES_PATH = (
    "automated_watch/github_releases_anthropics_claude_code/2026-10-05T093000Z.json"
)
ADVISORIES_PATH = "automated_watch/github_advisories_pip/2026-10-05T093000Z.json"


@pytest.fixture
def data_dir(tmp_path):
    """The test base of the readers, the items of three raw files gone as a purge leaves them, and
    a raw/ folder without any of their files."""
    create_database(tmp_path / "k-b.sqlite")
    connection = connect_database(tmp_path / "k-b.sqlite")
    try:
        connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
        with connection:
            # The papers, the releases and the advisories of 2026-10-05, as step 2 leaves them.
            for statement in (
                "DELETE FROM release",
                "DELETE FROM advisory",
                (
                    "UPDATE publication SET item_id = NULL, title = NULL, summary = NULL,"
                    " authors = NULL, submitted_at = NULL, revised_at = NULL"
                    " WHERE item_id IS NOT NULL"
                ),
                "DELETE FROM item WHERE kind IN ('paper', 'release', 'advisory')",
            ):
                connection.execute(statement)
    finally:
        connection.close()
    (tmp_path / "raw/automated_watch").mkdir(parents=True)
    (tmp_path / "raw/selected_library").mkdir()
    return tmp_path


def fetch_paths(data_dir):
    connection = sqlite3.connect(data_dir / "k-b.sqlite")
    try:
        return {
            row[0] for row in connection.execute("SELECT raw_file_path FROM raw_data")
        }
    finally:
        connection.close()


def add_raw_data(data_dir, source_code, raw_file_path, collected_at):
    connection = sqlite3.connect(data_dir / "k-b.sqlite")
    try:
        with connection:
            connection.execute(
                "INSERT INTO raw_data (source_id, raw_file_path, stream, collected_at)"
                " SELECT id, ?, ?, ? FROM source WHERE source_code = ?",
                (raw_file_path, source_code, collected_at, source_code),
            )
    finally:
        connection.close()


def purge(data_dir):
    return purge_registry(
        data_dir / "k-b.sqlite", RawStore(data_dir), STATE_CATALOG_SOURCE_CODES
    )


def test_a_row_whose_file_is_gone_and_that_nothing_cites_is_deleted(data_dir):
    present = data_dir / "raw" / ADVISORIES_PATH
    present.parent.mkdir()
    present.write_bytes(b"[]")
    before = fetch_paths(data_dir)

    assert purge(data_dir) == 2
    assert fetch_paths(data_dir) == before - {ARXIV_PATH, RELEASES_PATH}


def test_a_row_still_cited_stays_without_its_file(data_dir):
    """The rows of CISA KEV, of the two TLDR pages, of Zotero, of GH Archive (cited by trend) and
    of the clip."""
    purge(data_dir)

    assert len(fetch_paths(data_dir)) == 6


def test_the_last_catalog_of_a_state_catalog_stays_without_its_file(data_dir):
    """Its items point to an older catalog when it changed none of them; the import reads the
    latest catalog collected from the registry (catalog.py)."""
    older = "automated_watch/cisa_kev/2026-10-04T093000Z.csv"
    last = "automated_watch/cisa_kev/2026-10-06T093000Z.csv"
    add_raw_data(data_dir, "cisa_kev", older, "2026-10-04T09:30:00Z")
    add_raw_data(data_dir, "cisa_kev", last, "2026-10-06T09:30:00Z")

    purge(data_dir)

    paths = fetch_paths(data_dir)
    assert last in paths
    assert older not in paths


@pytest.mark.parametrize("missing", ["raw/automated_watch", "raw"])
def test_without_its_acquisition_folder_no_row_of_it_is_deleted(data_dir, missing):
    """A volume not mounted would make every file of it look gone: they would be imported again
    once it is back."""
    shutil.rmtree(data_dir / missing)
    before = fetch_paths(data_dir)

    assert purge(data_dir) == 0
    assert fetch_paths(data_dir) == before


def test_the_log_gives_numbers_never_a_name(data_dir, caplog):
    caplog.set_level(logging.INFO)

    purge(data_dir)

    assert "registry purge: 3 rows deleted" in caplog.messages
    assert "claude_code" not in caplog.text


@pytest.mark.parametrize(
    "refused_path",
    [
        "selected_library/clipping/2026-10-05T093000Z/a\\b.md",
        "automated_watch/../../outside.json",
        "",
    ],
)
def test_a_row_whose_path_the_store_refuses_stays_and_the_others_go(
    data_dir, refused_path
):
    """A page named by hand with a backslash is imported all the same; a path is otherwise only
    refused in a base written by hand."""
    add_raw_data(data_dir, "arxiv", refused_path, "2026-10-04T09:30:00Z")

    purge(data_dir)

    paths = fetch_paths(data_dir)
    assert refused_path in paths
    assert ARXIV_PATH not in paths
