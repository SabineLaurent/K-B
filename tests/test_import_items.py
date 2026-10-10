import json
import logging
import shutil
import sqlite3

import pytest
from test_raw_items import FIXTURES_DIR, copy_fixture

from k_b import import_items as import_items_module
from k_b.database.connection import connect_database
from k_b.database.creation import create_database
from k_b.import_items import (
    KindWithoutTableError,
    MissingDatabaseError,
    UnknownSourceError,
    import_items,
)
from k_b.items import Item
from k_b.source_contract import SourceKind, SourceReader
from k_b.source_kinds import SOURCE_KINDS

FIRST_PAPER_ID = "2609.31282"
FIRST_CVE_ID = "CVE-2026-86950"
PAPER_QUERY = (
    "SELECT item.id, item.kind, raw_file_path, title, authors, submitted_at, revised_at"
    " FROM publication JOIN item ON item.id = publication.item_id"
    " JOIN raw_data ON raw_data.id = item.raw_data_id WHERE arxiv_id = ?"
)


@pytest.fixture
def data_dir(tmp_path):
    raw_dir = tmp_path / "raw"
    copy_fixture(raw_dir, "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml")
    copy_fixture(raw_dir, "cisa_kev_extract.csv", "cisa_kev", "csv")
    create_database(tmp_path / "k-b.sqlite")
    return tmp_path


def run_import(data_dir):
    return import_items(
        data_dir / "raw",
        data_dir / "k-b.sqlite",
        data_dir / "import-log.jsonl",
        SOURCE_KINDS,
    )


def dump_database(data_dir):
    """Every table, row by row, as SQL text: two equal dumps are two equal bases."""
    connection = connect_database(data_dir / "k-b.sqlite")
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def fetch_rows(data_dir, query, parameters=()):
    connection = connect_database(data_dir / "k-b.sqlite")
    try:
        return connection.execute(query, parameters).fetchall()
    finally:
        connection.close()


def count_rows(data_dir, query):
    return fetch_rows(data_dir, query)[0][0]


def read_log(data_dir):
    return [
        json.loads(line)
        for line in (data_dir / "import-log.jsonl").read_text().splitlines()
    ]


def test_the_raw_files_go_into_the_database(data_dir):
    summary = run_import(data_dir)

    assert summary.item_count == 3 + 4
    assert count_rows(data_dir, "SELECT count(*) FROM item") == summary.item_count
    assert count_rows(data_dir, "SELECT count(*) FROM raw_data") == 2
    assert count_rows(data_dir, "SELECT count(*) FROM publication") == 3
    assert count_rows(data_dir, "SELECT count(*) FROM vulnerability") == 4


def test_an_arxiv_item_gives_an_item_and_its_publication(data_dir):
    run_import(data_dir)

    ((_, kind, raw_file_path, title, authors, submitted_at, revised_at),) = fetch_rows(
        data_dir, PAPER_QUERY, (FIRST_PAPER_ID,)
    )
    assert kind == "paper"
    assert raw_file_path == "automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"
    assert title.startswith("Resource-Optimized and Energy-Aware Agentic AI")
    assert json.loads(authors) == ["Toqeer Ali Syed", "Asadullah Abdullah Khan"]
    assert submitted_at == revised_at == "2026-09-25T13:53:50Z"


def test_a_cisa_row_gives_an_item_and_its_vulnerability(data_dir):
    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT item.kind, name, vendor, product, date_added, ransomware_use,"
        " revised_at, withdrawn_at, substr(description, 1, 25)"
        " FROM vulnerability JOIN item ON item.id = vulnerability.item_id"
        " WHERE cve_id = ?",
        (FIRST_CVE_ID,),
    ) == [
        (
            "vulnerability",
            "Apple Multiple Products Out-of-Bounds Write Vulnerability",
            "Apple",
            "Multiple Products",
            "2026-09-29T00:00:00Z",
            "Unknown",
            None,
            None,
            "Apple iOS, macOS, and iPa",
        )
    ]


def test_an_item_points_to_the_raw_file_and_date_of_its_collection(data_dir):
    run_import(data_dir)

    rows = fetch_rows(
        data_dir,
        "SELECT DISTINCT collected_at, raw_file_path, stream, source.source_code"
        " FROM item JOIN raw_data ON raw_data.id = item.raw_data_id"
        " JOIN source ON source.id = raw_data.source_id"
        " WHERE item.kind = 'vulnerability'",
    )

    assert rows == [
        (
            "2026-10-05T09:30:00Z",
            "automated_watch/cisa_kev/2026-10-05T093000Z.csv",
            "cisa_kev",
            "cisa_kev",
        )
    ]


def test_a_raw_file_of_releases_is_skipped_and_logged(data_dir, caplog):
    copy_fixture(
        data_dir / "raw",
        "github_releases_extract.json",
        "github_releases_anthropics_claude_code",
        "json",
    )

    with caplog.at_level(logging.INFO):
        summary = run_import(data_dir)

    assert summary.item_count == 3 + 4
    assert summary.rejection_count == 0
    assert count_rows(data_dir, "SELECT count(*) FROM raw_data") == 2
    assert (
        "source without a reader, skipped: github_releases_anthropics_claude_code"
        in caplog.text
    )


def test_an_import_run_again_on_the_same_raw_gives_the_same_database_and_log(data_dir):
    run_import(data_dir)
    first_tables = dump_database(data_dir)
    first_log = (data_dir / "import-log.jsonl").read_bytes()

    run_import(data_dir)

    assert dump_database(data_dir) == first_tables
    assert (data_dir / "import-log.jsonl").read_bytes() == first_log


def test_a_new_collection_keeps_the_identifier_of_an_item_already_imported(data_dir):
    run_import(data_dir)
    query = "SELECT item_id FROM vulnerability WHERE cve_id = ?"
    item_id = fetch_rows(data_dir, query, (FIRST_CVE_ID,))[0][0]
    shutil.copyfile(
        FIXTURES_DIR / "cisa_kev_extract.csv",
        data_dir / "raw/automated_watch/cisa_kev/2026-10-06T093000Z.csv",
    )

    run_import(data_dir)

    assert fetch_rows(data_dir, query, (FIRST_CVE_ID,))[0][0] == item_id
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4


def test_each_duplicate_removed_is_written_to_the_log_with_its_rule(data_dir):
    shutil.copyfile(
        FIXTURES_DIR / "cisa_kev_extract.csv",
        data_dir / "raw/automated_watch/cisa_kev/2026-10-06T093000Z.csv",
    )

    summary = run_import(data_dir)

    discards = [line for line in read_log(data_dir) if line["kind"] == "discard"]
    assert summary.discard_count == len(discards) == 4
    assert discards[0] == {
        "kind": "discard",
        "rule": "same_source_id",
        "source_code": "cisa_kev",
        "source_item_id": FIRST_CVE_ID,
        "url": f"https://nvd.nist.gov/vuln/detail/{FIRST_CVE_ID}",
        "raw_file_path": "automated_watch/cisa_kev/2026-10-06T093000Z.csv",
        "kept_url": f"https://nvd.nist.gov/vuln/detail/{FIRST_CVE_ID}",
    }


def test_each_rejected_file_is_written_to_the_log(data_dir):
    (
        data_dir / "raw/automated_watch/arxiv_cscr_x_csai/2026-10-06T093000Z.xml"
    ).write_text("not xml")

    summary = run_import(data_dir)

    rejections = [line for line in read_log(data_dir) if line["kind"] == "rejection"]
    assert summary.rejection_count == len(rejections) == 1
    assert (
        rejections[0]["raw_file_path"]
        == "automated_watch/arxiv_cscr_x_csai/2026-10-06T093000Z.xml"
    )
    assert rejections[0]["reason"]


def test_a_failed_import_leaves_the_database_and_the_log_unchanged(
    data_dir, monkeypatch
):
    tables_before = dump_database(data_dir)

    # The papers come first, in folder order: they are written, then a vulnerability fails.
    def refuse_vulnerability(connection, item, raw_data_id):
        raise sqlite3.IntegrityError("CHECK constraint failed: vulnerability")

    monkeypatch.setitem(
        import_items_module.WRITER_BY_KIND, "vulnerability", refuse_vulnerability
    )

    with pytest.raises(sqlite3.IntegrityError):
        run_import(data_dir)

    assert dump_database(data_dir) == tables_before
    assert not (data_dir / "import-log.jsonl").exists()


def convert_line_to_release(line, collected_at, raw_file_path):
    return Item(
        source_code="github",
        source_item_id=line,
        kind="release",
        title=line,
        url=f"https://github.com/owner/repository/releases/tag/{line}",
        collected_at=collected_at,
        raw_file_path=raw_file_path,
    )


def test_an_item_of_a_kind_without_table_is_refused_and_nothing_written(tmp_path):
    source_dir = tmp_path / "raw" / "automated_watch" / "fake"
    source_dir.mkdir(parents=True)
    (source_dir / "2026-10-05T093000Z.txt").write_text("v1.0\n")
    create_database(tmp_path / "k-b.sqlite")
    kinds = [
        SourceKind(
            "fake",
            (),
            SourceReader(
                lambda raw: raw.decode().splitlines(), convert_line_to_release
            ),
        )
    ]

    with pytest.raises(KindWithoutTableError, match="release"):
        import_items(
            tmp_path / "raw",
            tmp_path / "k-b.sqlite",
            tmp_path / "import-log.jsonl",
            kinds,
        )

    assert count_rows(tmp_path, "SELECT count(*) FROM item") == 0
    assert count_rows(tmp_path, "SELECT count(*) FROM raw_data") == 0


def test_an_item_of_a_source_missing_from_the_database_is_refused(data_dir):
    connection = connect_database(data_dir / "k-b.sqlite")
    with connection:
        connection.execute("DELETE FROM source WHERE source_code = 'cisa_kev'")
    connection.close()

    with pytest.raises(UnknownSourceError, match="cisa_kev"):
        run_import(data_dir)

    assert count_rows(data_dir, "SELECT count(*) FROM item") == 0


def test_a_missing_database_is_refused_and_not_created(tmp_path):
    with pytest.raises(MissingDatabaseError):
        import_items(
            tmp_path / "raw",
            tmp_path / "k-b.sqlite",
            tmp_path / "import-log.jsonl",
            SOURCE_KINDS,
        )

    assert not (tmp_path / "k-b.sqlite").exists()


def test_a_newer_revision_rewrites_the_paper_under_the_same_identifier(data_dir):
    run_import(data_dir)
    item_id = fetch_rows(data_dir, PAPER_QUERY, (FIRST_PAPER_ID,))[0][0]
    revision = (
        data_dir / "raw/automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"
    ).read_text()
    revision = revision.replace(
        "<updated>2026-09-25T13:53:50Z</updated>",
        "<updated>2026-10-02T08:00:00Z</updated>",
        1,
    ).replace("Asadullah Abdullah Khan", "Another Author")
    (
        data_dir / "raw/automated_watch/arxiv_cscr_x_csai/2026-10-06T093000Z.xml"
    ).write_text(revision)

    run_import(data_dir)

    ((new_item_id, _, raw_file_path, _, authors, submitted_at, revised_at),) = (
        fetch_rows(data_dir, PAPER_QUERY, (FIRST_PAPER_ID,))
    )
    assert new_item_id == item_id
    assert raw_file_path == "automated_watch/arxiv_cscr_x_csai/2026-10-06T093000Z.xml"
    assert json.loads(authors) == ["Toqeer Ali Syed", "Another Author"]
    assert (submitted_at, revised_at) == (
        "2026-09-25T13:53:50Z",
        "2026-10-02T08:00:00Z",
    )
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4


def test_a_log_that_cannot_be_written_keeps_the_previous_log_whole(
    data_dir, monkeypatch
):
    previous_log = '{"kind": "previous"}\n'
    (data_dir / "import-log.jsonl").write_text(previous_log)

    def fail_to_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(import_items_module.os, "replace", fail_to_replace)

    with pytest.raises(OSError, match="disk full"):
        run_import(data_dir)

    # The base is written first, then the log: the base keeps its import.
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4
    assert (data_dir / "import-log.jsonl").read_text() == previous_log
    assert not (data_dir / "import-log.jsonl.tmp").exists()
