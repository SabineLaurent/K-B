import csv
import io
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from test_items import (
    COLLECTED_AT,
    RAW_FILE_PATH,
    advisory_fields,
    item_fields,
    newsletter_article_fields,
    release_fields,
    text_of_length,
    vulnerability_fields,
)
from test_transform import FIXTURES_DIR, convert_line, copy_fixture

from k_b.database.connection import MissingDatabaseError, connect_database
from k_b.database.creation import create_database
from k_b.database.writers.shared_rows import UnknownSourceError
from k_b.etl import load as import_items_module
from k_b.etl.load import (
    ImportLogExistsError,
    KindWithoutTableError,
    import_items,
    read_imported_paths,
)
from k_b.etl.normalize import normalize_item
from k_b.etl.source_contract import EntryReading, SourceKind, SourceReader
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources.gh_archive import read_trend_files
from k_b.etl.sources.tracked_repositories import TRACKED_REPOSITORIES
from k_b.etl.transform import RawReading, TrendReading, read_raw_items
from k_b.items import (
    MAX_COUNT_BY_KIND,
    MAX_ELEMENT_LENGTH_BY_KIND,
    MAX_LENGTH_BY_KIND,
    Item,
)

FIRST_PAPER_ID = "2609.31282"
FIRST_CVE_ID = "CVE-2026-86950"
# The CVE of the recorded catalog, in its order; the last one is the one withdrawn.
CVE_IDS = (FIRST_CVE_ID, "CVE-2026-88772", "CVE-2026-88771", "CVE-2020-29583")
WITHDRAWN_CVE_ID = "CVE-2020-29583"
# A CVE the recorded advisories cite, absent from the recorded catalog.
ADVISORY_CVE_ID = "CVE-2026-48775"
FIRST_RELEASE_ID = 401174143
ADVISORY_WITH_TWO_PACKAGES = "GHSA-gr75-jv2w-4656"
AUTOMATED_WATCH = "automated_watch"
CISA_KEV_DIR = "cisa_kev"
RELEASES_DIR = "github_releases_anthropics_claude_code"
ADVISORIES_DIR = "github_advisories_pip"
ARXIV_DIR = "arxiv_cscr_x_csai"
FIRST_COLLECTION = "2026-10-05T093000Z"
FIRST_IMPORT_AT = datetime(2026, 10, 12, 15, 49, 3, tzinfo=UTC)
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
    copy_fixture(
        raw_dir,
        "github_releases_extract.json",
        "github_releases_anthropics_claude_code",
        "json",
    )
    copy_fixture(
        raw_dir, "github_advisories_extract.json", "github_advisories_pip", "json"
    )
    create_database(tmp_path / "k-b.sqlite")
    return tmp_path


def log_path_at(data_dir, imported_at):
    return data_dir / f"import-log-{imported_at:%Y-%m-%dT%H%M%SZ}.jsonl"


def list_logs(data_dir):
    return sorted(data_dir.glob("import-log-*.jsonl"))


def run_import(
    data_dir,
    tracked_repositories=TRACKED_REPOSITORIES,
    kinds=SOURCE_KINDS,
    read_again=False,
):
    """kb import, one second after the import before it: each import writes its own log.

    read_again: every raw file is read, as by a base of before #106 that has no registry.
    """
    imported_at = FIRST_IMPORT_AT + timedelta(seconds=len(list_logs(data_dir)))
    database_path = data_dir / "k-b.sqlite"
    imported_paths = frozenset() if read_again else read_imported_paths(database_path)
    return import_items(
        read_raw_items(data_dir / "raw", kinds, imported_paths),
        read_trend_files(data_dir / "raw", imported_paths),
        database_path,
        log_path_at(data_dir, imported_at),
        imported_at,
        tracked_repositories,
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


def read_log_lines(data_dir):
    """The lines of the log of the latest import."""
    return [
        json.loads(line) for line in list_logs(data_dir)[-1].read_text().splitlines()
    ]


def read_log(data_dir):
    """The lines of the latest log, without the time each one carries: a test of its own
    checks it."""
    lines = read_log_lines(data_dir)
    for line in lines:
        del line["imported_at"]
    return lines


def read_discards(data_dir, source_item_id=None):
    return [
        line
        for line in read_log(data_dir)
        if line["kind"] == "discard"
        and source_item_id in (None, line["source_item_id"])
    ]


def write_collection(data_dir, folder, collection, content):
    """A raw file of a later collection, written as its source would."""
    extension = {
        CISA_KEV_DIR: "csv",
        RELEASES_DIR: "json",
        ADVISORIES_DIR: "json",
        ARXIV_DIR: "xml",
    }[folder]
    (data_dir / "raw" / AUTOMATED_WATCH / folder).joinpath(
        f"{collection}.{extension}"
    ).write_text(content)
    return f"{AUTOMATED_WATCH}/{folder}/{collection}.{extension}"


def kev_catalog(ransomware_use_of_first_cve="Unknown", without=(), renamed=None):
    """The recorded catalog, with knownRansomwareCampaignUse of its first CVE as given, each
    CVE of renamed under its new identifier, then the CVE of without left out."""
    rows = list(
        csv.DictReader(io.StringIO((FIXTURES_DIR / "cisa_kev_extract.csv").read_text()))
    )
    columns = list(rows[0])
    rows[0]["knownRansomwareCampaignUse"] = ransomware_use_of_first_cve
    for row in rows:
        row["cveID"] = (renamed or {}).get(row["cveID"], row["cveID"])
    rows = [row for row in rows if row["cveID"] not in without]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


KEV_QUERY = (
    "SELECT vulnerability.item_id, ransomware_use, revised_at, raw_file_path"
    " FROM vulnerability JOIN item ON item.id = vulnerability.item_id"
    " JOIN raw_data ON raw_data.id = item.raw_data_id WHERE cve_id = ?"
)


def test_the_raw_files_go_into_the_database(data_dir):
    summary = run_import(data_dir)

    assert summary.item_count == 3 + 4 + 3 + 3
    assert count_rows(data_dir, "SELECT count(*) FROM item") == summary.item_count
    assert count_rows(data_dir, "SELECT count(*) FROM raw_data") == 4
    assert count_rows(data_dir, "SELECT count(*) FROM publication") == 3
    # The 4 CVE of CISA KEV, and the 3 CVE the advisories cite.
    assert count_rows(data_dir, "SELECT count(*) FROM vulnerability") == 4 + 3
    assert count_rows(data_dir, "SELECT count(*) FROM release") == 3
    assert count_rows(data_dir, "SELECT count(*) FROM advisory") == 3


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


def test_the_tracked_repositories_of_the_code_fill_their_table(data_dir):
    run_import(data_dir)

    rows = fetch_rows(
        data_dir,
        "SELECT repository_name, ecosystem, packages FROM tracked_repository ORDER BY id",
    )
    assert [
        (name, ecosystem, tuple(json.loads(packages)))
        for name, ecosystem, packages in rows
    ] == [
        (repository.name, repository.ecosystem, repository.packages)
        for repository in TRACKED_REPOSITORIES
    ]


def test_a_release_gives_an_item_and_its_release_of_its_tracked_repository(data_dir):
    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT item.kind, release.kind, repository_name, tag_name, name, published_at,"
        " url, substr(body, 1, 17), raw_file_path"
        " FROM release JOIN item ON item.id = release.item_id"
        " JOIN raw_data ON raw_data.id = item.raw_data_id"
        " JOIN tracked_repository ON tracked_repository.id = release.tracked_repository_id"
        " WHERE release_id = ?",
        (FIRST_RELEASE_ID,),
    ) == [
        (
            "release",
            "release",
            "anthropics/claude-code",
            "v2.1.287",
            "v2.1.287",
            "2026-10-01T18:00:22Z",
            "https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
            "## What's changed",
            "automated_watch/github_releases_anthropics_claude_code/2026-10-05T093000Z.json",
        )
    ]


def test_an_advisory_citing_an_absent_cve_creates_it_without_kev_columns(data_dir):
    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT item.kind, cve_id, vulnerability.item_id, name, vendor, date_added,"
        " packages, advisory.url FROM advisory"
        " JOIN item ON item.id = advisory.item_id"
        " JOIN vulnerability ON vulnerability.id = advisory.vulnerability_id"
        " WHERE ghsa_id = ?",
        (ADVISORY_WITH_TWO_PACKAGES,),
    ) == [
        (
            "advisory",
            "CVE-2026-55443",
            None,
            None,
            None,
            None,
            '["langchain", "langchain-anthropic"]',
            f"https://github.com/advisories/{ADVISORY_WITH_TWO_PACKAGES}",
        )
    ]


def test_the_packages_of_an_advisory_are_kept_once_each(data_dir):
    run_import(data_dir)

    ((packages,),) = fetch_rows(
        data_dir,
        "SELECT packages FROM advisory WHERE ghsa_id = 'GHSA-3644-q5cj-c5c7'",
    )
    assert json.loads(packages) == ["langsmith", "langchain-classic", "langchain"]


@pytest.mark.parametrize(
    "advisory_collection", ["2026-10-04T093000Z", "2026-10-06T093000Z"]
)
def test_an_advisory_and_a_kev_row_of_the_same_cve_share_one_vulnerability(
    data_dir, advisory_collection
):
    """The advisory collected before CISA KEV, then after it."""
    advisories = json.loads(
        (FIXTURES_DIR / "github_advisories_extract.json").read_text()
    )
    advisories[0]["cve_id"] = FIRST_CVE_ID
    (data_dir / "raw/automated_watch/github_advisories_pip").joinpath(
        f"{advisory_collection}.json"
    ).write_text(json.dumps([advisories[0]]))
    # The recorded file would give the same advisory with its own CVE: removed.
    (
        data_dir / "raw/automated_watch/github_advisories_pip/2026-10-05T093000Z.json"
    ).unlink()

    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT vulnerability.id = advisory.vulnerability_id, item.kind, vendor"
        " FROM vulnerability JOIN item ON item.id = vulnerability.item_id"
        " JOIN advisory ON advisory.vulnerability_id = vulnerability.id"
        " WHERE cve_id = ?",
        (FIRST_CVE_ID,),
    ) == [(1, "vulnerability", "Apple")]
    assert fetch_rows(data_dir, KEV_QUERY, (FIRST_CVE_ID,))[0][2] is None
    assert (
        count_rows(
            data_dir,
            f"SELECT count(*) FROM vulnerability WHERE cve_id = '{FIRST_CVE_ID}'",  # noqa: S608 — constant
        )
        == 1
    )


def test_a_release_of_a_repository_no_longer_tracked_is_rejected_and_logged(data_dir):
    still_tracked = tuple(
        repository
        for repository in TRACKED_REPOSITORIES
        if repository.name != "anthropics/claude-code"
    )

    summary = run_import(data_dir, still_tracked)

    rejections = [line for line in read_log(data_dir) if line["kind"] == "rejection"]
    assert summary.rejection_count == len(rejections) == 3
    assert rejections[0] == {
        "kind": "rejection",
        "raw_file_path": (
            "automated_watch/github_releases_anthropics_claude_code/2026-10-05T093000Z.json"
        ),
        "reason": "repository not in the tracked list: anthropics/claude-code",
    }
    assert summary.item_count == 3 + 4 + 3
    assert count_rows(data_dir, "SELECT count(*) FROM release") == 0


def test_a_second_import_without_new_raw_reads_nothing_and_changes_nothing(data_dir):
    first = run_import(data_dir)
    tables = dump_database(data_dir)

    second = run_import(data_dir)

    assert first.read_count == 4
    assert second == (0, 0, 0, 0, 0, 0)
    assert dump_database(data_dir) == tables
    assert read_log(data_dir) == []


def test_raw_files_read_again_give_the_same_database_and_log_every_item_as_a_discard(
    data_dir,
):
    # A base of before #106 reads every file again: the base still removes the duplicates.
    # Two catalogs that differ: the older one must not be written over the newer.
    newer_catalog = write_collection(
        data_dir, CISA_KEV_DIR, "2026-10-06T093000Z", kev_catalog("Known")
    )
    first = run_import(data_dir)
    first_tables = dump_database(data_dir)

    second = run_import(data_dir, read_again=True)

    assert dump_database(data_dir) == first_tables
    assert second.item_count == 0
    discards = read_discards(data_dir)
    assert (
        second.discard_count == len(discards) == first.item_count + first.discard_count
    )
    rules_by_file = {}
    for line in discards:
        rules_by_file.setdefault(line["raw_file_path"], set()).add(line["rule"])
    assert rules_by_file == {
        f"{AUTOMATED_WATCH}/{ARXIV_DIR}/{FIRST_COLLECTION}.xml": {"revision_not_newer"},
        f"{AUTOMATED_WATCH}/{CISA_KEV_DIR}/{FIRST_COLLECTION}.csv": {
            "no_newer_version"
        },
        # The first CVE has its version in this very catalog; the others, in the older one.
        newer_catalog: {"no_newer_version", "unchanged"},
        f"{AUTOMATED_WATCH}/{RELEASES_DIR}/{FIRST_COLLECTION}.json": {"already_seen"},
        f"{AUTOMATED_WATCH}/{ADVISORIES_DIR}/{FIRST_COLLECTION}.json": {"already_seen"},
    }


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
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4 + 3 + 3


def test_a_release_seen_again_keeps_its_first_collection_and_is_logged_already_seen(
    data_dir,
):
    releases = json.loads((FIXTURES_DIR / "github_releases_extract.json").read_text())
    releases[0]["body"] = "Edited after the first collection."
    again = write_collection(
        data_dir, RELEASES_DIR, "2026-10-06T093000Z", json.dumps(releases)
    )

    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT substr(body, 1, 17), raw_file_path FROM release"
        " JOIN item ON item.id = release.item_id"
        " JOIN raw_data ON raw_data.id = item.raw_data_id WHERE release_id = ?",
        (FIRST_RELEASE_ID,),
    ) == [
        (
            "## What's changed",
            f"{AUTOMATED_WATCH}/{RELEASES_DIR}/{FIRST_COLLECTION}.json",
        )
    ]
    assert count_rows(data_dir, "SELECT count(*) FROM release") == 3
    assert read_discards(data_dir, str(FIRST_RELEASE_ID)) == [
        {
            "kind": "discard",
            "rule": "already_seen",
            "source_code": "github",
            "source_item_id": str(FIRST_RELEASE_ID),
            "raw_file_path": again,
            "compared_with_collected_at": "2026-10-05T09:30:00Z",
        }
    ]


def test_an_advisory_seen_again_keeps_its_first_collection_and_is_logged_already_seen(
    data_dir,
):
    advisories = json.loads(
        (FIXTURES_DIR / "github_advisories_extract.json").read_text()
    )
    ghsa_id = advisories[0]["ghsa_id"]
    first_summary = advisories[0]["summary"]
    advisories[0]["summary"] = "Edited after the first collection."
    again = write_collection(
        data_dir, ADVISORIES_DIR, "2026-10-06T093000Z", json.dumps(advisories)
    )

    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT summary, raw_file_path FROM advisory"
        " JOIN item ON item.id = advisory.item_id"
        " JOIN raw_data ON raw_data.id = item.raw_data_id WHERE ghsa_id = ?",
        (ghsa_id,),
    ) == [
        (
            first_summary,
            f"{AUTOMATED_WATCH}/{ADVISORIES_DIR}/{FIRST_COLLECTION}.json",
        )
    ]
    assert count_rows(data_dir, "SELECT count(*) FROM advisory") == 3
    assert read_discards(data_dir, ghsa_id) == [
        {
            "kind": "discard",
            "rule": "already_seen",
            "source_code": "github",
            "source_item_id": ghsa_id,
            "raw_file_path": again,
            "compared_with_collected_at": "2026-10-05T09:30:00Z",
        }
    ]


def test_two_advisories_of_the_same_cve_are_both_kept_and_share_one_vulnerability(
    data_dir,
):
    advisories = json.loads(
        (FIXTURES_DIR / "github_advisories_extract.json").read_text()
    )
    advisories[1]["cve_id"] = advisories[0]["cve_id"]
    write_collection(data_dir, ADVISORIES_DIR, FIRST_COLLECTION, json.dumps(advisories))

    run_import(data_dir)

    assert fetch_rows(
        data_dir,
        "SELECT count(*), count(DISTINCT vulnerability_id) FROM advisory"
        " JOIN vulnerability ON vulnerability.id = advisory.vulnerability_id"
        " WHERE cve_id = ?",
        (advisories[0]["cve_id"],),
    ) == [(2, 1)]
    assert read_discards(data_dir) == []


def test_a_modified_kev_row_replaces_the_previous_one_and_dates_revised_at(data_dir):
    run_import(data_dir)
    ((item_id, _, _, _),) = fetch_rows(data_dir, KEV_QUERY, (FIRST_CVE_ID,))
    newer = write_collection(
        data_dir, CISA_KEV_DIR, "2026-10-06T093000Z", kev_catalog("Known")
    )

    run_import(data_dir)

    assert fetch_rows(data_dir, KEV_QUERY, (FIRST_CVE_ID,)) == [
        (item_id, "Known", "2026-10-06T09:30:00Z", newer)
    ]
    assert all(
        line["raw_file_path"] != newer for line in read_discards(data_dir, FIRST_CVE_ID)
    )


def test_an_identical_kev_row_of_a_newer_catalog_changes_nothing_and_is_logged_unchanged(
    data_dir,
):
    newer = write_collection(
        data_dir, CISA_KEV_DIR, "2026-10-06T093000Z", kev_catalog()
    )

    summary = run_import(data_dir)

    assert fetch_rows(data_dir, KEV_QUERY, (FIRST_CVE_ID,))[0][1:] == (
        "Unknown",
        None,
        f"{AUTOMATED_WATCH}/{CISA_KEV_DIR}/{FIRST_COLLECTION}.csv",
    )
    discards = read_discards(data_dir)
    assert summary.discard_count == len(discards) == 4
    assert discards[0] == {
        "kind": "discard",
        "rule": "unchanged",
        "source_code": "cisa_kev",
        "source_item_id": FIRST_CVE_ID,
        "raw_file_path": newer,
        "compared_with_collected_at": "2026-10-05T09:30:00Z",
    }


def test_a_kev_row_of_an_older_catalog_changes_nothing_and_is_logged_no_newer_version(
    data_dir,
):
    run_import(data_dir)
    # A file left unimported, older than the catalog already imported.
    older = write_collection(
        data_dir, CISA_KEV_DIR, "2026-10-04T093000Z", kev_catalog("Known")
    )

    run_import(data_dir)

    assert fetch_rows(data_dir, KEV_QUERY, (FIRST_CVE_ID,))[0][1:] == (
        "Unknown",
        None,
        f"{AUTOMATED_WATCH}/{CISA_KEV_DIR}/{FIRST_COLLECTION}.csv",
    )
    assert [
        line
        for line in read_discards(data_dir, FIRST_CVE_ID)
        if line["raw_file_path"] == older
    ] == [
        {
            "kind": "discard",
            "rule": "no_newer_version",
            "source_code": "cisa_kev",
            "source_item_id": FIRST_CVE_ID,
            "raw_file_path": older,
            "compared_with_collected_at": "2026-10-05T09:30:00Z",
        }
    ]


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


def test_an_invalid_release_is_written_to_the_log_and_the_others_are_imported(
    data_dir,
):
    releases = json.loads((FIXTURES_DIR / "github_releases_extract.json").read_text())
    releases[1]["tag_name"] = None
    raw_file_path = write_collection(
        data_dir, RELEASES_DIR, "2026-10-06T093000Z", json.dumps(releases)
    )

    run_import(data_dir)

    rejections = [line for line in read_log(data_dir) if line["kind"] == "rejection"]
    assert rejections == [
        {
            "kind": "rejection",
            "raw_file_path": raw_file_path,
            "reason": "release 1 (id 400266224): tag_name is not a string",
        }
    ]
    assert count_rows(data_dir, "SELECT count(*) FROM release") == 3


def test_a_failed_import_leaves_the_database_and_the_log_unchanged(
    data_dir, monkeypatch
):
    tables_before = dump_database(data_dir)

    # The papers come first, in folder order: they are written, then the system fails on a
    # vulnerability. An error of the system is not due to the entry: it stops the import.
    def fail_on_vulnerability(connection, item, raw_data_id):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setitem(
        import_items_module.WRITER_BY_KIND, "vulnerability", fail_on_vulnerability
    )

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        run_import(data_dir)

    assert dump_database(data_dir) == tables_before
    assert list_logs(data_dir) == []


def refuse_in_the_base(monkeypatch, source_item_id, **changes):
    """The item of source_item_id reaches its writer with changes the item would refuse: they
    are made after its validation, as by an item that let them through (conventions.md, rule
    4); the base is the safety net behind it."""

    def normalize_then_change(item):
        normalized_item = normalize_item(item)
        if normalized_item.source_item_id != source_item_id:
            return normalized_item
        return normalized_item.model_copy(update=changes)

    monkeypatch.setattr(import_items_module, "normalize_item", normalize_then_change)


RELEASES_PATH = f"{AUTOMATED_WATCH}/{RELEASES_DIR}/{FIRST_COLLECTION}.json"
CISA_KEV_PATH = f"{AUTOMATED_WATCH}/{CISA_KEV_DIR}/{FIRST_COLLECTION}.csv"
ARXIV_PATH = f"{AUTOMATED_WATCH}/{ARXIV_DIR}/{FIRST_COLLECTION}.xml"
# CVE-2026-86950 in Arabic-Indic digits: Python's \d accepts them, the GLOB of the base does not.
CVE_ID_IN_ARABIC_INDIC_DIGITS = "CVE-2026-٨٦٩٥٠"


# The four cases of PR #131 (docs/2026-10-11-revue-homogeneite.md): each one written to the
# base, the error it raises is one of an entry.
@pytest.mark.parametrize(
    ("source_item_id", "changes", "raw_file_path", "reason", "value"),
    [
        (
            str(FIRST_RELEASE_ID),
            {"source_item_id": str(2**63)},
            RELEASES_PATH,
            "release '401174143' refused by the base: OverflowError: Python int too large"
            " to convert to SQLite INTEGER",
            str(2**63),
        ),
        (
            FIRST_CVE_ID,
            {"cve": CVE_ID_IN_ARABIC_INDIC_DIGITS},
            CISA_KEV_PATH,
            "vulnerability 'CVE-2026-86950' refused by the base: SQLITE_CONSTRAINT_CHECK:"
            " CHECK constraint failed: cve_id GLOB"
            " 'CVE-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*'",
            "٨",
        ),
        (
            FIRST_PAPER_ID,
            {"title": "Lone \ud800 surrogate"},
            ARXIV_PATH,
            "paper '2609.31282' refused by the base: UnicodeEncodeError: surrogates not"
            " allowed at position 5",
            "Lone",
        ),
        (
            "400266224",
            {"tag_name": "\x00v1.0.0"},
            RELEASES_PATH,
            "release '400266224' refused by the base: SQLITE_CONSTRAINT_CHECK: CHECK"
            " constraint failed: length(tag_name) > 0",
            "v1.0.0",
        ),
    ],
)
def test_an_item_the_base_refuses_is_rejected_and_logged_and_the_others_are_imported(
    data_dir, monkeypatch, source_item_id, changes, raw_file_path, reason, value
):
    refuse_in_the_base(monkeypatch, source_item_id, **changes)

    summary = run_import(data_dir)

    rejections = [line for line in read_log(data_dir) if line["kind"] == "rejection"]
    assert rejections == [
        {"kind": "rejection", "raw_file_path": raw_file_path, "reason": reason}
    ]
    assert value not in rejections[0]["reason"]
    assert summary.rejection_count == 1
    # The other items are written; the item refused is not counted, and leaves no row.
    assert summary.item_count == count_rows(data_dir, "SELECT count(*) FROM item") > 0
    assert (
        count_rows(
            data_dir,
            "SELECT count(*) FROM item WHERE id NOT IN (SELECT item_id FROM publication"
            " WHERE item_id IS NOT NULL UNION SELECT item_id FROM vulnerability"
            " WHERE item_id IS NOT NULL UNION SELECT item_id FROM release"
            " UNION SELECT item_id FROM advisory)",
        )
        == 0
    )
    assert raw_file_path in registered_paths(data_dir)


def test_an_item_of_a_kind_without_writer_is_refused_and_nothing_written(
    tmp_path, monkeypatch
):
    # Every kind has its writer: one is removed, as for a kind added before its table.
    monkeypatch.delitem(import_items_module.WRITER_BY_KIND, "newsletter_article")
    source_dir = tmp_path / "raw" / "automated_watch" / "fake"
    source_dir.mkdir(parents=True)
    (source_dir / "2026-10-05T093000Z.txt").write_text("v1.0\n")
    create_database(tmp_path / "k-b.sqlite")
    kinds = [
        SourceKind(
            "fake",
            (),
            SourceReader(
                "tldr",
                lambda raw: EntryReading(raw.decode().splitlines(), []),
                convert_line,
            ),
        )
    ]

    with pytest.raises(KindWithoutTableError, match="newsletter_article"):
        run_import(tmp_path, kinds=kinds)

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
        read_imported_paths(tmp_path / "k-b.sqlite")
    with pytest.raises(MissingDatabaseError):
        import_items(
            RawReading([], [], 0),
            TrendReading([], [], 0),
            tmp_path / "k-b.sqlite",
            log_path_at(tmp_path, FIRST_IMPORT_AT),
            FIRST_IMPORT_AT,
            TRACKED_REPOSITORIES,
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
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4 + 3 + 3


@pytest.mark.parametrize("last_revision", ["older", "equal"])
def test_an_arxiv_revision_not_newer_is_discarded_as_revision_not_newer(
    data_dir, last_revision
):
    recorded = (FIXTURES_DIR / "arxiv_extract.xml").read_text()
    revision = recorded.replace(
        "<updated>2026-09-25T13:53:50Z</updated>",
        "<updated>2026-10-02T08:00:00Z</updated>",
        1,
    )
    newer = write_collection(data_dir, ARXIV_DIR, "2026-10-06T093000Z", revision)
    last = write_collection(
        data_dir,
        ARXIV_DIR,
        "2026-10-07T093000Z",
        recorded if last_revision == "older" else revision,
    )

    run_import(data_dir)

    ((_, _, raw_file_path, _, _, _, revised_at),) = fetch_rows(
        data_dir, PAPER_QUERY, (FIRST_PAPER_ID,)
    )
    assert (raw_file_path, revised_at) == (newer, "2026-10-02T08:00:00Z")
    assert [
        line
        for line in read_discards(data_dir, FIRST_PAPER_ID)
        if line["raw_file_path"] == last
    ] == [
        {
            "kind": "discard",
            "rule": "revision_not_newer",
            "source_code": "arxiv",
            "source_item_id": FIRST_PAPER_ID,
            "raw_file_path": last,
            "compared_with_revised_at": "2026-10-02T08:00:00Z",
        }
    ]


def test_a_log_that_cannot_be_written_leaves_the_database_unchanged(
    data_dir, monkeypatch
):
    tables_before = dump_database(data_dir)

    def fail_to_write(path, content):
        raise OSError("disk full")

    monkeypatch.setattr("k_b.etl.import_log.write_file_atomically", fail_to_write)

    with pytest.raises(OSError, match="disk full"):
        run_import(data_dir)

    # The log is written before the commit: no file is registered, all are read again.
    assert dump_database(data_dir) == tables_before
    assert list_logs(data_dir) == []


class CommitFailingConnection(sqlite3.Connection):
    def commit(self):
        raise sqlite3.OperationalError("disk I/O error")


def test_a_commit_that_fails_leaves_neither_the_import_nor_its_log(
    data_dir, monkeypatch
):
    tables_before = dump_database(data_dir)

    def connect_with_failing_commit(database_path):
        connection = sqlite3.connect(database_path, factory=CommitFailingConnection)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    monkeypatch.setattr(
        import_items_module, "connect_database", connect_with_failing_commit
    )

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        run_import(data_dir)

    assert dump_database(data_dir) == tables_before
    assert list_logs(data_dir) == []


def test_a_ctrl_c_after_the_log_is_written_leaves_neither_the_import_nor_its_log(
    data_dir, monkeypatch
):
    tables_before = dump_database(data_dir)
    write_import_log = import_items_module.write_import_log

    def write_then_interrupt(*arguments):
        write_import_log(*arguments)
        raise KeyboardInterrupt

    monkeypatch.setattr(import_items_module, "write_import_log", write_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        run_import(data_dir)

    assert dump_database(data_dir) == tables_before
    assert list_logs(data_dir) == []


def text_at_its_maximum(kind, field, maximum):
    """A text of the maximum length that names its kind and its field: no two columns hold
    the same, so a writer that takes one field for another is seen."""
    if field in ("cve", "edition") or (kind, field) == ("advisory", "source_item_id"):
        return text_of_length(field, maximum, kind)
    prefix = {"url": "https://"}.get(field, "")
    repeated = f"{kind}.{field}-" * maximum
    return (prefix + repeated)[:maximum]


def build_item_at_its_maximums(build_fields, collected_at, raw_file_path):
    """An item of the kind of build_fields, each bounded text and list at its maximum."""
    kind = build_fields()["kind"]
    fields = {
        field: text_at_its_maximum(kind, field, maximum)
        for field, maximum in MAX_LENGTH_BY_KIND[kind].items()
    }
    for field, maximum_count in MAX_COUNT_BY_KIND.get(kind, {}).items():
        fields[field] = ("x" * MAX_ELEMENT_LENGTH_BY_KIND[kind][field],) * maximum_count
    return Item(
        **build_fields(collected_at=collected_at, raw_file_path=raw_file_path, **fields)
    )


def test_an_item_with_every_text_and_list_at_its_maximum_goes_into_the_database(
    tmp_path,
):
    source_dir = tmp_path / "raw" / "automated_watch" / "fake"
    source_dir.mkdir(parents=True)
    (source_dir / "2026-10-05T093000Z.txt").write_text("")
    create_database(tmp_path / "k-b.sqlite")
    builders = [
        item_fields,
        vulnerability_fields,
        release_fields,
        advisory_fields,
        newsletter_article_fields,
    ]
    kinds = [
        SourceKind(
            "fake",
            (),
            SourceReader(
                "arxiv",
                lambda raw: EntryReading(builders, []),
                build_item_at_its_maximums,
            ),
        )
    ]

    summary = run_import(tmp_path, kinds=kinds)

    assert summary == (5, 0, 0, 1, 0, 0)
    paper, vulnerability, release, advisory, newsletter_article = (
        build_item_at_its_maximums(build_fields, COLLECTED_AT, RAW_FILE_PATH)
        for build_fields in builders
    )
    assert fetch_rows(
        tmp_path, "SELECT arxiv_id, title, summary, authors FROM publication"
    ) == [
        (
            paper.source_item_id,
            paper.title,
            paper.summary,
            json.dumps(list(paper.authors)),
        )
    ]
    assert fetch_rows(
        tmp_path, "SELECT cve_id, name, description, vendor, product FROM vulnerability"
    ) == [
        (
            vulnerability.cve,
            vulnerability.title,
            vulnerability.summary,
            vulnerability.vendor,
            vulnerability.product,
        )
    ]
    assert fetch_rows(tmp_path, "SELECT tag_name, name, body, url FROM release") == [
        (release.tag_name, release.release_name, release.summary, release.url)
    ]
    assert fetch_rows(
        tmp_path, "SELECT ghsa_id, summary, url, packages FROM advisory"
    ) == [
        (
            advisory.source_item_id,
            advisory.title,
            advisory.url,
            json.dumps(list(advisory.package_names)),
        )
    ]
    assert fetch_rows(
        tmp_path, "SELECT edition, title, summary, url FROM newsletter_article"
    ) == [
        (
            newsletter_article.edition,
            newsletter_article.title,
            newsletter_article.summary,
            newsletter_article.url,
        )
    ]


def registered_paths(data_dir):
    return {
        path for (path,) in fetch_rows(data_dir, "SELECT raw_file_path FROM raw_data")
    }


def test_a_file_read_without_item_is_registered_and_not_read_again(data_dir):
    empty = write_collection(
        data_dir, CISA_KEV_DIR, "2026-10-06T093000Z", kev_catalog(without=CVE_IDS)
    )

    first = run_import(data_dir)
    second = run_import(data_dir)

    assert empty in registered_paths(data_dir)
    assert (first.read_count, second.read_count) == (5, 0)
    # A catalog without any row is not a catalog that withdrew every CVE.
    assert first.withdrawn_count == 0


def test_a_file_read_with_a_rejected_entry_is_registered_and_not_read_again(data_dir):
    catalog = kev_catalog()
    assert (
        catalog.count("Citrix NetScaler Improper Input Validation Vulnerability") == 1
    )
    with_rejection = write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-06T093000Z",
        catalog.replace("Citrix NetScaler Improper Input Validation Vulnerability", ""),
    )

    first = run_import(data_dir)
    second = run_import(data_dir)

    assert with_rejection in registered_paths(data_dir)
    assert first.rejection_count == 1
    assert (second.read_count, second.rejection_count) == (0, 0)


def test_an_unreadable_file_and_a_file_without_reader_are_not_registered(data_dir):
    unreadable = write_collection(data_dir, ARXIV_DIR, "2026-10-06T093000Z", "not xml")
    copy_fixture(
        data_dir / "raw",
        "github_most_starred_extract.json",
        "github_most_starred",
        "json",
    )

    run_import(data_dir)
    second = run_import(data_dir)

    assert unreadable not in registered_paths(data_dir)
    assert all("github_most_starred" not in path for path in registered_paths(data_dir))
    # The unreadable file is read and rejected at each import (decision of 2026-10-12).
    assert (second.read_count, second.rejection_count) == (1, 1)


def test_only_a_new_raw_file_is_read_and_the_log_of_the_first_import_stays_whole(
    data_dir,
):
    run_import(data_dir)
    (first_log,) = list_logs(data_dir)
    first_log_content = first_log.read_bytes()
    write_collection(data_dir, CISA_KEV_DIR, "2026-10-06T093000Z", kev_catalog("Known"))

    second = run_import(data_dir)

    assert second.read_count == 1
    assert second.item_count == 1
    assert len(list_logs(data_dir)) == 2
    assert first_log.read_bytes() == first_log_content


def test_a_log_of_the_same_second_stops_the_import_before_the_database(data_dir):
    log_path = log_path_at(data_dir, FIRST_IMPORT_AT)
    log_path.write_text("earlier import\n")
    tables_before = dump_database(data_dir)
    database_path = data_dir / "k-b.sqlite"
    reading = read_raw_items(
        data_dir / "raw", SOURCE_KINDS, read_imported_paths(database_path)
    )

    with pytest.raises(ImportLogExistsError):
        import_items(
            reading,
            TrendReading([], [], 0),
            database_path,
            log_path,
            FIRST_IMPORT_AT,
            TRACKED_REPOSITORIES,
        )

    assert dump_database(data_dir) == tables_before
    assert log_path.read_text() == "earlier import\n"


def test_each_line_of_the_log_carries_the_time_of_its_import(data_dir):
    write_collection(data_dir, ARXIV_DIR, "2026-10-06T093000Z", "not xml")
    releases = (FIXTURES_DIR / "github_releases_extract.json").read_text()
    write_collection(data_dir, RELEASES_DIR, "2026-10-06T093000Z", releases)

    run_import(data_dir)

    lines = read_log_lines(data_dir)
    assert {line["kind"] for line in lines} == {"rejection", "discard"}
    assert {line["imported_at"] for line in lines} == {"2026-10-12T15:49:03Z"}
    assert all(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", line["imported_at"])
        for line in lines
    )


WITHDRAWAL_QUERY = (
    "SELECT withdrawn_at, revised_at, raw_file_path"
    " FROM vulnerability JOIN item ON item.id = vulnerability.item_id"
    " JOIN raw_data ON raw_data.id = item.raw_data_id WHERE cve_id = ?"
)
WITHDRAWN_COUNT_QUERY = (
    "SELECT count(*) FROM vulnerability WHERE withdrawn_at IS NOT NULL"
)


def test_a_kev_row_absent_from_a_newer_catalog_is_withdrawn_at_its_collection(
    data_dir,
):
    run_import(data_dir)
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-06T093000Z",
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )

    summary = run_import(data_dir)

    assert summary.withdrawn_count == 1
    # The item keeps the file of its version: an absence is not a version.
    assert fetch_rows(data_dir, WITHDRAWAL_QUERY, (WITHDRAWN_CVE_ID,)) == [
        (
            "2026-10-06T09:30:00Z",
            None,
            f"{AUTOMATED_WATCH}/{CISA_KEV_DIR}/{FIRST_COLLECTION}.csv",
        )
    ]
    # The rows present, though not written (unchanged), are not withdrawn.
    assert count_rows(data_dir, WITHDRAWN_COUNT_QUERY) == 1
    assert {line["rule"] for line in read_discards(data_dir)} == {"unchanged"}


def test_a_withdrawn_kev_row_back_in_a_newer_catalog_is_written_again_and_dated(
    data_dir,
):
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-06T093000Z",
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )
    run_import(data_dir)
    query = "SELECT item_id FROM vulnerability WHERE cve_id = ?"
    ((item_id,),) = fetch_rows(data_dir, query, (WITHDRAWN_CVE_ID,))
    back = write_collection(data_dir, CISA_KEV_DIR, "2026-10-07T093000Z", kev_catalog())

    summary = run_import(data_dir)

    # Its content is the same: only its return is written.
    assert summary.item_count == 1
    assert fetch_rows(data_dir, query, (WITHDRAWN_CVE_ID,)) == [(item_id,)]
    assert fetch_rows(data_dir, WITHDRAWAL_QUERY, (WITHDRAWN_CVE_ID,)) == [
        (None, "2026-10-07T09:30:00Z", back)
    ]


def test_a_kev_row_absent_from_two_catalogs_keeps_the_date_of_the_first(data_dir):
    for collection in ("2026-10-06T093000Z", "2026-10-07T093000Z"):
        write_collection(
            data_dir,
            CISA_KEV_DIR,
            collection,
            kev_catalog(without=(WITHDRAWN_CVE_ID,)),
        )

    run_import(data_dir)

    assert fetch_rows(data_dir, WITHDRAWAL_QUERY, (WITHDRAWN_CVE_ID,))[0][0] == (
        "2026-10-06T09:30:00Z"
    )


def test_a_catalog_with_a_rejected_row_withdraws_nothing(data_dir):
    run_import(data_dir)
    catalog = kev_catalog(without=(WITHDRAWN_CVE_ID,))
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-06T093000Z",
        catalog.replace("Citrix NetScaler Improper Input Validation Vulnerability", ""),
    )

    summary = run_import(data_dir)

    # A rejected row is in the catalog, not absent from it.
    assert (summary.rejection_count, summary.withdrawn_count) == (1, 0)
    assert count_rows(data_dir, WITHDRAWN_COUNT_QUERY) == 0


def test_a_catalog_with_a_row_the_base_refuses_withdraws_nothing(data_dir, monkeypatch):
    run_import(data_dir)
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-06T093000Z",
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )
    refuse_in_the_base(monkeypatch, FIRST_CVE_ID, cve=CVE_ID_IN_ARABIC_INDIC_DIGITS)

    summary = run_import(data_dir)

    # A row the base refuses is in the catalog, as a row rejected when read.
    assert (summary.rejection_count, summary.withdrawn_count) == (1, 0)
    assert count_rows(data_dir, WITHDRAWN_COUNT_QUERY) == 0


def test_a_catalog_older_than_the_latest_imported_withdraws_nothing(data_dir):
    run_import(data_dir)
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-04T093000Z",
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )

    summary = run_import(data_dir)

    assert summary.withdrawn_count == 0
    assert count_rows(data_dir, WITHDRAWN_COUNT_QUERY) == 0


def test_a_cve_only_an_older_catalog_brings_is_written_withdrawn_at_the_latest_catalog(
    data_dir,
):
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        FIRST_COLLECTION,
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )
    run_import(data_dir)
    late = write_collection(data_dir, CISA_KEV_DIR, "2026-10-04T093000Z", kev_catalog())

    run_import(data_dir)

    # The latest catalog does not list it: it is withdrawn, as a rebuild would find it.
    assert fetch_rows(data_dir, WITHDRAWAL_QUERY, (WITHDRAWN_CVE_ID,)) == [
        ("2026-10-05T09:30:00Z", None, late)
    ]


def test_a_cve_of_an_advisory_an_older_catalog_fills_is_written_withdrawn(data_dir):
    run_import(data_dir)
    late = write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-04T093000Z",
        kev_catalog(renamed={WITHDRAWN_CVE_ID: ADVISORY_CVE_ID}),
    )

    run_import(data_dir)

    assert fetch_rows(data_dir, WITHDRAWAL_QUERY, (ADVISORY_CVE_ID,)) == [
        ("2026-10-05T09:30:00Z", None, late)
    ]


def rebuild_database(data_dir):
    """Delete the base, create it, and import every raw file: kb create-db, kb import."""
    for suffix in ("", "-wal", "-shm"):
        (data_dir / f"k-b.sqlite{suffix}").unlink(missing_ok=True)
    create_database(data_dir / "k-b.sqlite")
    run_import(data_dir)


def test_a_rebuilt_database_equals_the_one_kept_import_after_import(data_dir):
    run_import(data_dir)
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-06T093000Z",
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )
    run_import(data_dir)
    write_collection(data_dir, CISA_KEV_DIR, "2026-10-07T093000Z", kev_catalog("Known"))
    run_import(data_dir)
    kept = dump_database(data_dir)

    rebuild_database(data_dir)

    assert dump_database(data_dir) == kept


KEV_CONTENT_QUERY = (
    "SELECT cve_id, name, description, vendor, product, date_added, ransomware_use,"
    " withdrawn_at IS NOT NULL FROM vulnerability ORDER BY cve_id"
)


def test_a_rebuilt_database_has_the_content_and_withdrawals_of_one_kept_with_a_late_catalog(
    data_dir, tmp_path_factory
):
    first_catalog = (
        data_dir / "raw" / AUTOMATED_WATCH / CISA_KEV_DIR / (f"{FIRST_COLLECTION}.csv")
    )
    set_aside = tmp_path_factory.mktemp("set_aside") / first_catalog.name
    shutil.move(first_catalog, set_aside)
    write_collection(
        data_dir,
        CISA_KEV_DIR,
        "2026-10-07T093000Z",
        kev_catalog(without=(WITHDRAWN_CVE_ID,)),
    )
    run_import(data_dir)
    # The first catalog comes late: imported after a newer one.
    shutil.move(set_aside, first_catalog)
    run_import(data_dir)
    kept = fetch_rows(data_dir, KEV_CONTENT_QUERY)

    rebuild_database(data_dir)

    assert fetch_rows(data_dir, KEV_CONTENT_QUERY) == kept
    assert (WITHDRAWN_CVE_ID, True) in [(row[0], bool(row[-1])) for row in kept]


# A reduced extract of the TLDR AI page of 2026-10-07, as collected on 2026-10-11: a sponsored
# entry, three articles, a job offer of TLDR.
TLDR_AI_PAGE = (FIXTURES_DIR / "tldr_ai_extract.html").read_text()
TLDR_FIRST_COLLECTION = "2026-10-11T153130Z"
TLDR_SECOND_COLLECTION = "2026-10-12T153130Z"
MISTRAL_ARTICLE_ID = "ai/2026-10-07#2"
MISTRAL_TITLE = "Mistral Large 4 (9 minute read)"
MISTRAL_SUMMARY = (
    "Mistral Large 4 is a one-trillion-parameter multimodal model positioned as a"
    " European alternative to leading closed and open AI systems."
)
NEWSLETTER_ARTICLE_QUERY = (
    "SELECT edition, edition_date, rank, title, summary, url, publication_id,"
    " item.kind, raw_file_path FROM newsletter_article"
    " JOIN item ON item.id = newsletter_article.item_id"
    " JOIN raw_data ON raw_data.id = item.raw_data_id"
    " ORDER BY edition, edition_date, rank"
)


def write_tldr_page(data_dir, folder, collection, page):
    """The page of 2026-10-07 of an edition folder, in a collection."""
    pages_dir = data_dir / "raw" / AUTOMATED_WATCH / folder / collection
    pages_dir.mkdir(parents=True)
    (pages_dir / "2026-10-07.html").write_text(page)
    return f"{AUTOMATED_WATCH}/{folder}/{collection}/2026-10-07.html"


@pytest.fixture
def tldr_data_dir(tmp_path):
    create_database(tmp_path / "k-b.sqlite")
    write_tldr_page(tmp_path, "tldr_ai", TLDR_FIRST_COLLECTION, TLDR_AI_PAGE)
    return tmp_path


def test_a_tldr_page_gives_an_item_and_its_newsletter_article_per_article(
    tldr_data_dir,
):
    first_page = f"{AUTOMATED_WATCH}/tldr_ai/{TLDR_FIRST_COLLECTION}/2026-10-07.html"

    summary = run_import(tldr_data_dir)

    assert summary == (3, 0, 0, 1, 0, 0)
    rows = fetch_rows(tldr_data_dir, NEWSLETTER_ARTICLE_QUERY)
    assert rows[0] == (
        "ai",
        "2026-10-07T00:00:00Z",
        2,
        MISTRAL_TITLE,
        MISTRAL_SUMMARY,
        "https://mistral.ai/news/mistral-large-4/",
        None,
        "newsletter_article",
        first_page,
    )
    # The ranks count the sponsored entry (1) and leave out the job offer (5); the utm_*
    # parameters are removed, the others kept; no publication is cited yet.
    assert [(row[2], row[5], row[6]) for row in rows] == [
        (2, "https://mistral.ai/news/mistral-large-4/", None),
        (3, "https://openai.com/index/sharing-ai-progress-in-mathematics/", None),
        (
            4,
            (
                "https://www.nytimes.com/2026/10/06/science/"
                "china-ai-research-recruitment.html"
                "?unlocked_article_code=1.G1E.vzNX.LAgmpYtxdpWb&smid=url-share"
            ),
            None,
        ),
    ]
    assert fetch_rows(tldr_data_dir, "SELECT stream, raw_file_path FROM raw_data") == [
        ("tldr_ai", first_page)
    ]


def test_an_article_seen_again_keeps_its_first_collection_and_is_logged_already_seen(
    tldr_data_dir,
):
    run_import(tldr_data_dir)
    rows_of_the_first_import = fetch_rows(tldr_data_dir, NEWSLETTER_ARTICLE_QUERY)
    # The day of the last collection is collected again: the same page, edited since.
    edited_page = TLDR_AI_PAGE.replace(
        MISTRAL_TITLE, "Mistral Large 4, edited"
    ).replace(MISTRAL_SUMMARY, "Edited after the first collection.")
    assert edited_page.count("dited") == 2
    again = write_tldr_page(
        tldr_data_dir, "tldr_ai", TLDR_SECOND_COLLECTION, edited_page
    )

    second = run_import(tldr_data_dir)

    assert second == (0, 3, 0, 1, 0, 0)
    assert fetch_rows(tldr_data_dir, NEWSLETTER_ARTICLE_QUERY) == (
        rows_of_the_first_import
    )
    assert rows_of_the_first_import[0][3:5] == (MISTRAL_TITLE, MISTRAL_SUMMARY)
    assert again in registered_paths(tldr_data_dir)
    assert read_discards(tldr_data_dir, MISTRAL_ARTICLE_ID) == [
        {
            "kind": "discard",
            "rule": "already_seen",
            "source_code": "tldr",
            "source_item_id": MISTRAL_ARTICLE_ID,
            "raw_file_path": again,
            "compared_with_collected_at": "2026-10-11T15:31:30Z",
        }
    ]


def test_the_same_article_summarized_by_two_editions_is_kept_twice(tldr_data_dir):
    # The same page under the folder of another edition: every URL is seen twice.
    write_tldr_page(tldr_data_dir, "tldr_dev", TLDR_FIRST_COLLECTION, TLDR_AI_PAGE)

    summary = run_import(tldr_data_dir)

    assert summary == (6, 0, 0, 2, 0, 0)
    assert fetch_rows(
        tldr_data_dir,
        "SELECT edition, count(*), count(DISTINCT url) FROM newsletter_article"
        " GROUP BY edition ORDER BY edition",
    ) == [("ai", 3, 3), ("dev", 3, 3)]
    assert (
        count_rows(tldr_data_dir, "SELECT count(DISTINCT url) FROM newsletter_article")
        == 3
    )


def test_a_tldr_page_without_edition_title_is_rejected_and_not_registered(
    tldr_data_dir,
):
    landing_page = write_tldr_page(
        tldr_data_dir,
        "tldr_ai",
        TLDR_SECOND_COLLECTION,
        TLDR_AI_PAGE.replace("TLDR AI 2026-10-07</h1>", "Keep up with AI</h1>"),
    )

    summary = run_import(tldr_data_dir)

    assert (summary.item_count, summary.rejection_count) == (3, 1)
    assert landing_page not in registered_paths(tldr_data_dir)
    assert read_log(tldr_data_dir) == [
        {
            "kind": "rejection",
            "raw_file_path": landing_page,
            "reason": "ValueError: first h1 is not an edition title with its date: "
            "'Keep up with AI'",
        }
    ]


# A reduced extract of the GH Archive ranking collected on 2026-10-11: 5 of the 48 rows of the
# window ending on 2026-10-10.
RANKING = json.loads((FIXTURES_DIR / "gh_archive_extract.json").read_text())
GH_ARCHIVE_DIR = "gh_archive"
RANKING_COLLECTION = "2026-10-11T153130Z"
RANKING_COLLECTED_AT = "2026-10-11T15:31:30Z"
LATER_COLLECTION = "2026-10-12T021500Z"
WINDOW_END = "2026-10-10"
NEXT_WINDOW_END = "2026-10-11"
TREND_QUERY = (
    "SELECT window_end, repository_id, repository_name, stars_gained, forks_gained,"
    " raw_file_path FROM trend JOIN raw_data ON raw_data.id = trend.raw_data_id"
    " ORDER BY window_end, trend.id"
)


def write_ranking(data_dir, collection, rows, window_ends=(WINDOW_END,)):
    """A raw result of GH Archive, written as its collection would."""
    source_dir = data_dir / "raw" / AUTOMATED_WATCH / GH_ARCHIVE_DIR
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / f"{collection}.json").write_text(
        json.dumps({"window_ends": list(window_ends), "rows": rows})
    )
    return f"{AUTOMATED_WATCH}/{GH_ARCHIVE_DIR}/{collection}.json"


def rows_of_window(window_end, stars_gained=None):
    """The rows of the fixture, moved to a window, with other stars if given."""
    return [
        row
        | {"window_end": window_end}
        | ({} if stars_gained is None else {"stars_gained": stars_gained})
        for row in RANKING["rows"]
    ]


@pytest.fixture
def trend_data_dir(tmp_path):
    create_database(tmp_path / "k-b.sqlite")
    write_ranking(tmp_path, RANKING_COLLECTION, RANKING["rows"])
    return tmp_path


def test_a_ranking_gives_a_trend_row_per_repository_of_its_window_and_no_item(
    trend_data_dir,
):
    raw_file_path = f"{AUTOMATED_WATCH}/{GH_ARCHIVE_DIR}/{RANKING_COLLECTION}.json"

    summary = run_import(trend_data_dir)

    # The 5 rows share one window: the file being written leaves none of its own rows out.
    assert summary == (0, 0, 0, 1, 0, 5)
    assert fetch_rows(trend_data_dir, TREND_QUERY) == [
        (
            "2026-10-10T00:00:00Z",
            row["repository_id"],
            row["repository_name"],
            row["stars_gained"],
            row["forks_gained"],
            raw_file_path,
        )
        for row in RANKING["rows"]
    ]
    assert fetch_rows(
        trend_data_dir,
        "SELECT source_code, stream, collected_at FROM raw_data"
        " JOIN source ON source.id = raw_data.source_id",
    ) == [("gh_archive", "gh_archive", RANKING_COLLECTED_AT)]
    assert count_rows(trend_data_dir, "SELECT count(*) FROM item") == 0
    assert read_log(trend_data_dir) == []


def test_a_second_import_reads_no_ranking_again_and_changes_nothing(trend_data_dir):
    run_import(trend_data_dir)
    tables = dump_database(trend_data_dir)

    second = run_import(trend_data_dir)

    assert second == (0, 0, 0, 0, 0, 0)
    assert dump_database(trend_data_dir) == tables


def test_a_ranking_read_again_changes_nothing_and_its_window_is_logged_already_seen(
    trend_data_dir,
):
    run_import(trend_data_dir)
    tables = dump_database(trend_data_dir)

    second = run_import(trend_data_dir, read_again=True)

    assert second == (0, 1, 0, 1, 0, 0)
    assert dump_database(trend_data_dir) == tables
    assert read_log(trend_data_dir) == [
        {
            "kind": "discard",
            "rule": "already_seen",
            "source_code": "gh_archive",
            "source_item_id": WINDOW_END,
            "raw_file_path": (
                f"{AUTOMATED_WATCH}/{GH_ARCHIVE_DIR}/{RANKING_COLLECTION}.json"
            ),
            "compared_with_collected_at": RANKING_COLLECTED_AT,
        }
    ]


def test_a_window_collected_again_keeps_its_first_ranking_whole_and_is_logged(
    trend_data_dir,
):
    run_import(trend_data_dir)
    first_ranking = fetch_rows(trend_data_dir, TREND_QUERY)
    # Other figures, and a repository the first ranking did not hold: a new key.
    newcomer = RANKING["rows"][0] | {
        "repository_id": 724712,
        "repository_name": "newcomer/repository",
    }
    again = write_ranking(
        trend_data_dir,
        LATER_COLLECTION,
        [*rows_of_window(WINDOW_END, stars_gained=9_999), newcomer],
    )

    second = run_import(trend_data_dir)

    assert second == (0, 1, 0, 1, 0, 0)
    assert fetch_rows(trend_data_dir, TREND_QUERY) == first_ranking
    assert again in registered_paths(trend_data_dir)
    log = list_logs(trend_data_dir)[-1].read_text()
    assert "newcomer" not in log
    assert RANKING["rows"][0]["repository_name"] not in log
    assert read_log(trend_data_dir) == [
        {
            "kind": "discard",
            "rule": "already_seen",
            "source_code": "gh_archive",
            "source_item_id": WINDOW_END,
            "raw_file_path": again,
            "compared_with_collected_at": RANKING_COLLECTED_AT,
        }
    ]


def test_a_ranking_with_a_known_window_and_a_new_one_writes_the_new_one_only(
    trend_data_dir,
):
    run_import(trend_data_dir)
    later = write_ranking(
        trend_data_dir,
        LATER_COLLECTION,
        [
            *rows_of_window(WINDOW_END, stars_gained=9_999),
            *rows_of_window(NEXT_WINDOW_END, stars_gained=7),
        ],
        window_ends=(WINDOW_END, NEXT_WINDOW_END),
    )

    second = run_import(trend_data_dir)

    assert second == (0, 1, 0, 1, 0, 5)
    assert fetch_rows(
        trend_data_dir,
        "SELECT window_end, count(*), max(stars_gained), count(DISTINCT raw_data_id)"
        " FROM trend GROUP BY window_end ORDER BY window_end",
    ) == [("2026-10-10T00:00:00Z", 5, 1087, 1), ("2026-10-11T00:00:00Z", 5, 7, 1)]
    assert [line["source_item_id"] for line in read_discards(trend_data_dir)] == [
        WINDOW_END
    ]
    assert later in registered_paths(trend_data_dir)


def test_two_rankings_of_a_window_in_one_import_keep_the_one_collected_first(
    trend_data_dir,
):
    later = write_ranking(
        trend_data_dir, LATER_COLLECTION, rows_of_window(WINDOW_END, stars_gained=9_999)
    )

    summary = run_import(trend_data_dir)

    assert summary == (0, 1, 0, 2, 0, 5)
    assert {row[3] for row in fetch_rows(trend_data_dir, TREND_QUERY)} == {
        row["stars_gained"] for row in RANKING["rows"]
    }
    assert [line["raw_file_path"] for line in read_discards(trend_data_dir)] == [later]


def test_a_ranking_refused_is_rejected_logged_and_read_again_at_the_next_import(
    trend_data_dir,
):
    refused = write_ranking(
        trend_data_dir,
        LATER_COLLECTION,
        [RANKING["rows"][0] | {"window_end": NEXT_WINDOW_END, "stars_gained": -1}],
        window_ends=(NEXT_WINDOW_END,),
    )

    first = run_import(trend_data_dir)
    second = run_import(trend_data_dir)

    # The ranking of the fixture is written; the refused one is opened by both imports.
    assert first == (0, 0, 1, 2, 0, 5)
    assert second == (0, 0, 1, 1, 0, 0)
    assert refused not in registered_paths(trend_data_dir)
    [rejection] = read_log(trend_data_dir)
    assert (rejection["kind"], rejection["raw_file_path"]) == ("rejection", refused)
    assert rejection["reason"].startswith(
        "TrendsExtractInvalidError: row 0: stars_gained"
    )
    assert count_rows(trend_data_dir, "SELECT count(*) FROM trend") == 5


def run_import_with_a_ranking_row_changed(data_dir, raw_file_path, **changes):
    """kb import, with the last row of the ranking at raw_file_path changed after its
    reading: as by a reader that let the change through (conventions.md, rule 4)."""
    imported_at = FIRST_IMPORT_AT + timedelta(seconds=len(list_logs(data_dir)))
    database_path = data_dir / "k-b.sqlite"
    imported_paths = read_imported_paths(database_path)
    trend_reading = read_trend_files(data_dir / "raw", imported_paths)
    changed_files = [
        trend_file._replace(
            rows=[*trend_file.rows[:-1], trend_file.rows[-1].model_copy(update=changes)]
        )
        if trend_file.raw_file.raw_file_path == raw_file_path
        else trend_file
        for trend_file in trend_reading.files
    ]
    return import_items(
        read_raw_items(data_dir / "raw", SOURCE_KINDS, imported_paths),
        trend_reading._replace(files=changed_files),
        database_path,
        log_path_at(data_dir, imported_at),
        imported_at,
        TRACKED_REPOSITORIES,
    )


def test_a_ranking_with_a_row_the_base_refuses_is_refused_whole_and_read_again(
    trend_data_dir,
):
    refused = write_ranking(
        trend_data_dir,
        LATER_COLLECTION,
        rows_of_window(NEXT_WINDOW_END),
        window_ends=(NEXT_WINDOW_END,),
    )

    first = run_import_with_a_ranking_row_changed(
        trend_data_dir, refused, stars_gained=2**63
    )

    # The ranking of the fixture is written; none of the rows of the refused one is.
    assert first == (0, 0, 1, 2, 0, 5)
    assert refused not in registered_paths(trend_data_dir)
    assert read_log(trend_data_dir) == [
        {
            "kind": "rejection",
            "raw_file_path": refused,
            "reason": "ranking refused by the base: OverflowError: Python int too large"
            " to convert to SQLite INTEGER",
        }
    ]
    assert fetch_rows(trend_data_dir, "SELECT DISTINCT window_end FROM trend") == [
        ("2026-10-10T00:00:00Z",)
    ]

    # Read again by the next import, as an unreadable file: written once it is accepted.
    second = run_import(trend_data_dir)

    assert second == (0, 0, 0, 1, 0, 5)
    assert refused in registered_paths(trend_data_dir)


def test_a_rebuilt_database_with_rankings_equals_the_one_kept_import_after_import(
    data_dir,
):
    # Each import brings a file of items and a ranking: a rebuild reads the four in
    # collection order, as the imports did.
    write_ranking(data_dir, RANKING_COLLECTION, RANKING["rows"])
    run_import(data_dir)
    write_collection(data_dir, CISA_KEV_DIR, "2026-10-12T011500Z", kev_catalog("Known"))
    write_ranking(
        data_dir,
        LATER_COLLECTION,
        rows_of_window(NEXT_WINDOW_END),
        window_ends=(NEXT_WINDOW_END,),
    )
    run_import(data_dir)
    kept = dump_database(data_dir)

    rebuild_database(data_dir)

    assert count_rows(data_dir, "SELECT count(*) FROM trend") == 10
    assert dump_database(data_dir) == kept


def test_a_window_of_the_year_1_is_written_with_a_year_of_four_digits(trend_data_dir):
    # The base refuses a year not written on 4 digits: the day is not formatted by the C
    # library, which does not pad the year on every platform.
    write_ranking(
        trend_data_dir,
        LATER_COLLECTION,
        rows_of_window("0001-01-01"),
        window_ends=("0001-01-01",),
    )

    summary = run_import(trend_data_dir)

    assert summary.trend_count == 10
    assert fetch_rows(
        trend_data_dir, "SELECT DISTINCT window_end FROM trend ORDER BY window_end"
    ) == [("0001-01-01T00:00:00Z",), ("2026-10-10T00:00:00Z",)]
