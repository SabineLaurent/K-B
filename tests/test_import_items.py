import json
import shutil
import sqlite3

import pytest

from test_raw_items import FIXTURES_DIR, copy_fixture, write_most_starred_ranking

from k_b import import_items as import_items_module
from k_b.database import connect_database, create_database
from k_b.import_items import MissingDatabaseError, import_items

FIRST_PAPER_ID = "2609.31282"
FIRST_PAPER_AUTHORS = [("Toqeer Ali Syed", 1), ("Asadullah Abdullah Khan", 2)]
AUTHORS_QUERY = (
    "SELECT name, position FROM item_author JOIN author USING (author_id)"
    " JOIN item USING (item_id) WHERE source_item_id = ? ORDER BY position"
)


@pytest.fixture
def data_dir(tmp_path):
    raw_dir = tmp_path / "raw"
    copy_fixture(raw_dir, "arxiv_extract.xml", "arxiv", "xml")
    copy_fixture(raw_dir, "cisa_kev_extract.csv", "cisa_kev", "csv")
    copy_fixture(
        raw_dir,
        "github_releases_extract.json",
        "github_releases_anthropics_claude_code",
        "json",
    )
    copy_fixture(raw_dir, "github_advisories_extract.json", "github_advisories_pip", "json")
    write_most_starred_ranking(raw_dir)
    create_database(tmp_path / "k-b.sqlite")
    return tmp_path


def run_import(data_dir):
    return import_items(data_dir / "raw", data_dir / "k-b.sqlite", data_dir / "import-log.jsonl")


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
    return [json.loads(line) for line in (data_dir / "import-log.jsonl").read_text().splitlines()]


def test_the_raw_files_go_into_the_database(data_dir):
    summary = run_import(data_dir)

    assert summary.item_count == 3 + 4 + 3 + 3 + 100
    assert count_rows(data_dir, "SELECT count(*) FROM item") == summary.item_count
    assert count_rows(data_dir, "SELECT count(*) FROM collection") == 5
    assert count_rows(data_dir, "SELECT count(*) FROM item_author") == 11
    assert count_rows(data_dir, "SELECT count(*) FROM repository") == 100
    assert count_rows(data_dir, "SELECT count(*) FROM vulnerability") == 4 + 3


def test_an_item_points_to_the_raw_file_and_date_of_its_collection(data_dir):
    run_import(data_dir)

    rows = fetch_rows(
        data_dir,
        "SELECT DISTINCT collected_at, raw_file_path FROM item JOIN collection USING (collection_id)"
        " WHERE source_code = 'cisa_kev'",
    )

    assert rows == [("2026-10-05T09:30:00Z", "automation/cisa_kev/2026-10-05T093000Z.csv")]


def test_the_authors_keep_their_order(data_dir):
    run_import(data_dir)

    assert fetch_rows(data_dir, AUTHORS_QUERY, (FIRST_PAPER_ID,)) == FIRST_PAPER_AUTHORS


def test_a_name_repeated_in_the_authors_keeps_its_first_position(data_dir):
    path = data_dir / "raw/automation/arxiv/2026-10-05T093000Z.xml"
    path.write_text(path.read_text().replace("Asadullah Abdullah Khan", "Toqeer Ali Syed"))

    run_import(data_dir)

    assert fetch_rows(data_dir, AUTHORS_QUERY, (FIRST_PAPER_ID,)) == [("Toqeer Ali Syed", 1)]


def test_an_import_run_again_on_the_same_raw_gives_the_same_database_and_log(data_dir):
    run_import(data_dir)
    first_tables = dump_database(data_dir)
    first_log = (data_dir / "import-log.jsonl").read_bytes()

    run_import(data_dir)

    assert dump_database(data_dir) == first_tables
    assert (data_dir / "import-log.jsonl").read_bytes() == first_log


def test_a_new_collection_keeps_the_identifier_of_an_item_already_imported(data_dir):
    run_import(data_dir)
    query = "SELECT item_id FROM item WHERE source_item_id = 'GHSA-fjqc-hq36-qh5p'"
    item_id = count_rows(data_dir, query)
    shutil.copyfile(
        FIXTURES_DIR / "github_advisories_extract.json",
        data_dir / "raw/automation/github_advisories_pip/2026-10-06T093000Z.json",
    )

    run_import(data_dir)

    assert count_rows(data_dir, query) == item_id
    assert count_rows(data_dir, "SELECT count(*) FROM item WHERE source_code = 'github'") == 106


def test_each_duplicate_removed_is_written_to_the_log_with_its_rule(data_dir):
    shutil.copyfile(
        FIXTURES_DIR / "github_advisories_extract.json",
        data_dir / "raw/automation/github_advisories_pip/2026-10-06T093000Z.json",
    )

    summary = run_import(data_dir)

    discards = [line for line in read_log(data_dir) if line["kind"] == "discard"]
    assert summary.discard_count == len(discards) == 3
    assert discards[0] == {
        "kind": "discard",
        "rule": "same_source_id",
        "source_code": "github",
        "source_item_id": "GHSA-fjqc-hq36-qh5p",
        "url": "https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
        "raw_file_path": "automation/github_advisories_pip/2026-10-06T093000Z.json",
        "kept_url": "https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
    }


def test_each_rejected_file_is_written_to_the_log(data_dir):
    (data_dir / "raw/automation/arxiv/2026-10-06T093000Z.xml").write_text("not xml")

    summary = run_import(data_dir)

    rejections = [line for line in read_log(data_dir) if line["kind"] == "rejection"]
    assert summary.rejection_count == len(rejections) == 1
    assert rejections[0]["raw_file_path"] == "automation/arxiv/2026-10-06T093000Z.xml"
    assert rejections[0]["reason"]


def test_an_advisory_without_cve_is_a_vulnerability_without_cve(data_dir):
    path = data_dir / "raw/automation/github_advisories_pip/2026-10-05T093000Z.json"
    advisories = json.loads(path.read_text())
    advisories[0]["cve_id"] = None
    path.write_text(json.dumps(advisories))

    run_import(data_dir)

    assert (
        count_rows(
            data_dir,
            "SELECT count(*) FROM vulnerability JOIN item USING (item_id)"
            " WHERE source_item_id = 'GHSA-fjqc-hq36-qh5p' AND cve IS NULL",
        )
        == 1
    )


def test_a_failed_import_leaves_the_database_and_the_log_unchanged(data_dir):
    connection = connect_database(data_dir / "k-b.sqlite")
    with connection:
        connection.execute(
            "INSERT INTO collection (collected_at, raw_file_path) VALUES (?, ?)",
            ("2026-10-01T00:00:00Z", "automation/other.json"),
        )
        # Same URL as an advisory of the fixture, under another identifier: refused by the base.
        connection.execute(
            "INSERT INTO item (source_code, source_item_id, title, url, collection_id)"
            " VALUES ('github', 'other', 'Other', ?, 1)",
            ("https://github.com/advisories/GHSA-fjqc-hq36-qh5p",),
        )
    connection.close()
    tables_before = dump_database(data_dir)

    with pytest.raises(sqlite3.IntegrityError):
        run_import(data_dir)

    assert dump_database(data_dir) == tables_before
    assert not (data_dir / "import-log.jsonl").exists()


def test_a_missing_database_is_refused_and_not_created(tmp_path):
    with pytest.raises(MissingDatabaseError):
        import_items(tmp_path / "raw", tmp_path / "k-b.sqlite", tmp_path / "import-log.jsonl")

    assert not (tmp_path / "k-b.sqlite").exists()


def test_a_newer_revision_rewrites_the_paper_under_the_same_identifier(data_dir):
    run_import(data_dir)
    query = "SELECT item_id FROM item WHERE source_item_id = ?"
    item_id = fetch_rows(data_dir, query, (FIRST_PAPER_ID,))[0][0]
    revision = (data_dir / "raw/automation/arxiv/2026-10-05T093000Z.xml").read_text()
    revision = revision.replace(
        "<updated>2026-09-25T13:53:50Z</updated>", "<updated>2026-10-02T08:00:00Z</updated>", 1
    ).replace("Asadullah Abdullah Khan", "Another Author")
    (data_dir / "raw/automation/arxiv/2026-10-06T093000Z.xml").write_text(revision)

    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT item_id, revised_at, raw_file_path FROM item JOIN collection USING (collection_id)"
        " WHERE source_item_id = ?",
        (FIRST_PAPER_ID,),
    ) == [(item_id, "2026-10-02T08:00:00Z", "automation/arxiv/2026-10-06T093000Z.xml")]
    assert fetch_rows(data_dir, AUTHORS_QUERY, (FIRST_PAPER_ID,)) == [
        ("Toqeer Ali Syed", 1),
        ("Another Author", 2),
    ]


def test_an_author_left_without_item_is_deleted(data_dir):
    run_import(data_dir)
    path = data_dir / "raw/automation/arxiv/2026-10-05T093000Z.xml"
    path.write_text(path.read_text().replace("Asadullah Abdullah Khan", "Another Author"))

    run_import(data_dir)

    assert (
        fetch_rows(data_dir, "SELECT name FROM author WHERE name = ?", ("Asadullah Abdullah Khan",))
        == []
    )


def test_a_log_that_cannot_be_written_keeps_the_previous_log_whole(data_dir, monkeypatch):
    previous_log = '{"kind": "previous"}\n'
    (data_dir / "import-log.jsonl").write_text(previous_log)

    def fail_to_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(import_items_module.os, "replace", fail_to_replace)

    with pytest.raises(OSError, match="disk full"):
        run_import(data_dir)

    # The base is written first, then the log: the base keeps its import.
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4 + 3 + 3 + 100
    assert (data_dir / "import-log.jsonl").read_text() == previous_log
    assert not (data_dir / "import-log.jsonl.tmp").exists()
