import re
import sqlite3

import pytest

from k_b.config import RETENTION_YEARS_BY_ACQUISITION_MODE
from k_b.database.creation import DATABASE_SCRIPTS

EXPECTED_TABLES = {
    "source",
    "raw_data",
    "item",
    "author",
    "item_author",
    "highlight",
    "repository",
    "star_gain",
    "vulnerability",
}


@pytest.fixture
def database():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(DATABASE_SCRIPTS.joinpath("schema.sql").read_text())
    connection.executescript(DATABASE_SCRIPTS.joinpath("seed_sources.sql").read_text())
    yield connection
    connection.close()


def test_the_schema_and_the_sources_load_with_every_expected_table(database):
    tables = {
        name
        for (name,) in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert tables == EXPECTED_TABLES
    assert database.execute("SELECT count(*) FROM source").fetchone() == (7,)


def test_each_acquisition_mode_of_the_schema_has_a_retention_in_the_config():
    schema = DATABASE_SCRIPTS.joinpath("schema.sql").read_text()
    (allowed_values,) = re.findall(r"acquisition_mode IN \(([^)]*)\)", schema)

    assert set(re.findall(r"'(\w+)'", allowed_values)) == set(
        RETENTION_YEARS_BY_ACQUISITION_MODE
    )


def test_an_acquisition_mode_outside_the_list_is_refused(database):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            "INSERT INTO source (source_code, label, source_type, acquisition_mode)"
            " VALUES ('rss', 'RSS', 'web_service', 'archive')"
        )


def test_each_seeded_source_has_its_acquisition_mode(database):
    modes = dict(database.execute("SELECT source_code, acquisition_mode FROM source"))

    assert modes == {
        "github": "watch",
        "arxiv": "watch",
        "cisa_kev": "watch",
        "clipper": "library",
        "tldr": "watch",
        "zotero": "library",
        "gh_archive": "watch",
    }


def test_a_raw_data_of_an_unknown_source_is_refused(database):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        database.execute(
            "INSERT INTO raw_data (source_id, raw_file_path, stream, collected_at)"
            " VALUES (99, 'automated_watch/rss/x.xml', 'rss', '2026-10-05T09:30:00Z')"
        )


def insert_vulnerability(database, item_id, url):
    database.execute(
        "INSERT INTO item (item_id, source_code, source_item_id, title, url, raw_data_id)"
        " VALUES (?, ?, ?, ?, ?, 1)",
        (
            item_id,
            "github" if item_id == 1 else "cisa_kev",
            f"id-{item_id}",
            "A title",
            url,
        ),
    )
    database.execute(
        "INSERT INTO vulnerability (item_id, cve) VALUES (?, 'CVE-2026-48775')",
        (item_id,),
    )


def test_two_sources_can_share_a_cve(database):
    database.execute(
        "INSERT INTO raw_data (id, source_id, raw_file_path, stream, collected_at)"
        " VALUES (1, 1, 'automated_watch/x/2026-10-05T093000Z.json', 'x',"
        " '2026-10-05T09:30:00Z')"
    )

    insert_vulnerability(
        database, 1, "https://github.com/advisories/GHSA-fjqc-hq36-qh5p"
    )
    insert_vulnerability(database, 2, "https://nvd.nist.gov/vuln/detail/CVE-2026-48775")

    assert database.execute(
        "SELECT count(*) FROM vulnerability WHERE cve = 'CVE-2026-48775'"
    ).fetchone() == (2,)


def test_a_cve_is_found_through_its_index(database):
    plan = database.execute(
        "EXPLAIN QUERY PLAN SELECT item_id FROM vulnerability WHERE cve = 'CVE-2026-48775'"
    ).fetchall()

    assert "vulnerability_cve" in str(plan)
