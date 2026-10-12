import csv
import io
import json
import shutil
import sqlite3

import pytest
from test_items import (
    COLLECTED_AT,
    RAW_FILE_PATH,
    advisory_fields,
    item_fields,
    release_fields,
    text_of_length,
    vulnerability_fields,
)
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
from k_b.items import (
    MAX_COUNT_BY_KIND,
    MAX_ELEMENT_LENGTH_BY_KIND,
    MAX_LENGTH_BY_KIND,
    Item,
)
from k_b.source_contract import SourceKind, SourceReader
from k_b.source_kinds import SOURCE_KINDS
from k_b.sources.tracked_repositories import TRACKED_REPOSITORIES

FIRST_PAPER_ID = "2609.31282"
FIRST_CVE_ID = "CVE-2026-86950"
FIRST_RELEASE_ID = 401174143
ADVISORY_WITH_TWO_PACKAGES = "GHSA-gr75-jv2w-4656"
AUTOMATED_WATCH = "automated_watch"
CISA_KEV_DIR = "cisa_kev"
RELEASES_DIR = "github_releases_anthropics_claude_code"
ADVISORIES_DIR = "github_advisories_pip"
ARXIV_DIR = "arxiv_cscr_x_csai"
FIRST_COLLECTION = "2026-10-05T093000Z"
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


def run_import(data_dir, tracked_repositories=TRACKED_REPOSITORIES):
    return import_items(
        data_dir / "raw",
        data_dir / "k-b.sqlite",
        data_dir / "import-log.jsonl",
        SOURCE_KINDS,
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


def read_log(data_dir):
    return [
        json.loads(line)
        for line in (data_dir / "import-log.jsonl").read_text().splitlines()
    ]


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


def kev_catalog(ransomware_use_of_first_cve="Unknown"):
    """The recorded catalog, with knownRansomwareCampaignUse of its first CVE as given."""
    rows = list(
        csv.DictReader(io.StringIO((FIXTURES_DIR / "cisa_kev_extract.csv").read_text()))
    )
    rows[0]["knownRansomwareCampaignUse"] = ransomware_use_of_first_cve
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
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


def test_a_zotero_extract_is_not_read_into_the_database(data_dir):
    # Zotero has no reader yet: its extracts, under raw/selected_library/, are left alone.
    extract_dir = data_dir / "raw" / "selected_library" / "zotero"
    extract_dir.mkdir(parents=True)
    (extract_dir / "2026-10-11T120000Z.json").write_text(
        '[{"key": "AAAAAAA1", "highlights": [{"key": "ANNOTAA1"}]}]'
    )

    summary = run_import(data_dir)

    assert summary.item_count == 3 + 4 + 3 + 3
    assert summary.rejection_count == 0
    assert count_rows(data_dir, "SELECT count(*) FROM highlight") == 0
    assert count_rows(data_dir, "SELECT count(*) FROM raw_data") == 4


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


def test_an_import_run_again_gives_the_same_database_and_logs_every_item_as_a_discard(
    data_dir,
):
    # Two catalogs that differ: the older one must not be written over the newer.
    newer_catalog = write_collection(
        data_dir, CISA_KEV_DIR, "2026-10-06T093000Z", kev_catalog("Known")
    )
    first = run_import(data_dir)
    first_tables = dump_database(data_dir)

    second = run_import(data_dir)

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


def convert_line_to_newsletter_article(line, collected_at, raw_file_path):
    return Item(
        source_code="tldr",
        source_item_id=line,
        kind="newsletter_article",
        title=line,
        url=f"https://example.com/{line}",
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
                lambda raw: raw.decode().splitlines(),
                convert_line_to_newsletter_article,
            ),
        )
    ]

    with pytest.raises(KindWithoutTableError, match="newsletter_article"):
        import_items(
            tmp_path / "raw",
            tmp_path / "k-b.sqlite",
            tmp_path / "import-log.jsonl",
            kinds,
            TRACKED_REPOSITORIES,
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
    assert count_rows(data_dir, "SELECT count(*) FROM item") == 3 + 4 + 3 + 3
    assert (data_dir / "import-log.jsonl").read_text() == previous_log
    assert not (data_dir / "import-log.jsonl.tmp").exists()


def text_at_its_maximum(kind, field, maximum):
    """A text of the maximum length that names its kind and its field: no two columns hold
    the same, so a writer that takes one field for another is seen."""
    if field == "cve":
        return text_of_length(field, maximum)
    prefix = {"url": "https://", "source_item_id": "GHSA-" * (kind == "advisory")}.get(
        field, ""
    )
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
    builders = [item_fields, vulnerability_fields, release_fields, advisory_fields]
    kinds = [
        SourceKind(
            "fake", (), SourceReader(lambda raw: builders, build_item_at_its_maximums)
        )
    ]

    summary = import_items(
        tmp_path / "raw",
        tmp_path / "k-b.sqlite",
        tmp_path / "import-log.jsonl",
        kinds,
        TRACKED_REPOSITORIES,
    )

    assert summary == (4, 0, 0)
    paper, vulnerability, release, advisory = (
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
