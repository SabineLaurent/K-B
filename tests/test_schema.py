import sqlite3
from importlib.resources import files

import pytest

DATABASE_SCRIPTS = files("k_b.database")
EXPECTED_TABLES = {
    "source",
    "collection",
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


def insert_vulnerability(database, item_id, url):
    database.execute(
        "INSERT INTO item (item_id, source_code, source_item_id, title, url, collection_id)"
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
        "INSERT INTO collection (collection_id, collected_at, raw_file_path)"
        " VALUES (1, '2026-10-05T09:30:00Z', 'automated_watch/x/2026-10-05T093000Z.json')"
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
