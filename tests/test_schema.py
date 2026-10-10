import re
import sqlite3
import typing

import pytest

from k_b.config import RETENTION_YEARS_BY_ACQUISITION_MODE
from k_b.database.creation import DATABASE_SCRIPTS
from k_b.items import ItemKind
from k_b.sources.github_advisories import ECOSYSTEMS

EXPECTED_TABLES = {
    "source",
    "raw_data",
    "item",
    "publication",
    "highlight",
    "repository",
    "star_gain",
    "vulnerability",
    "tracked_repository",
    "release",
    "advisory",
}

PAPER_COLUMNS = (
    "title, summary, authors, submitted_at, revised_at",
    (
        "'A title', 'A summary', '[\"Ada Lovelace\"]', '2026-09-25T13:53:50Z',"
        " '2026-09-25T13:53:50Z'"
    ),
)
KEV_COLUMNS = (
    "name, description, vendor, product, date_added, ransomware_use",
    (
        "'A name', 'A description', 'Apple', 'Multiple Products',"
        " '2026-09-29T00:00:00Z', 'Unknown'"
    ),
)


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


@pytest.fixture
def item_id(database):
    database.execute(
        "INSERT INTO raw_data (id, source_id, raw_file_path, stream, collected_at)"
        " VALUES (1, 1, 'automated_watch/x/2026-10-05T093000Z.json', 'x',"
        " '2026-10-05T09:30:00Z')"
    )
    return database.execute(
        "INSERT INTO item (kind, raw_data_id) VALUES ('paper', 1) RETURNING id"
    ).fetchone()[0]


def test_the_kinds_of_the_schema_are_those_of_the_items():
    schema = DATABASE_SCRIPTS.joinpath("schema.sql").read_text()
    (allowed_values,) = re.findall(r"kind IN \(([^)]*)\)", schema)

    assert set(re.findall(r"'(\w+)'", allowed_values)) == set(typing.get_args(ItemKind))


def test_a_kind_outside_the_list_is_refused(database, item_id):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute("INSERT INTO item (kind, raw_data_id) VALUES ('tweet', 1)")


def test_a_publication_and_a_vulnerability_cited_without_their_item_are_accepted(
    database,
):
    database.execute("INSERT INTO publication (arxiv_id) VALUES ('2609.31282')")
    database.execute("INSERT INTO vulnerability (cve_id) VALUES ('CVE-2026-86950')")

    assert database.execute("SELECT count(*) FROM publication").fetchone() == (1,)
    assert database.execute("SELECT count(*) FROM vulnerability").fetchone() == (1,)


def test_a_publication_with_its_item_and_its_arxiv_columns_is_accepted(
    database, item_id
):
    columns, values = PAPER_COLUMNS
    database.execute(
        f"INSERT INTO publication (arxiv_id, item_id, {columns})"  # noqa: S608 — constants
        f" VALUES ('2609.31282', ?, {values})",
        (item_id,),
    )

    assert database.execute("SELECT count(*) FROM publication").fetchone() == (1,)


def test_a_publication_without_item_but_with_a_title_is_refused(database):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            "INSERT INTO publication (arxiv_id, title) VALUES ('2609.31282', 'A title')"
        )


def test_a_publication_with_its_item_but_without_title_is_refused(database, item_id):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            "INSERT INTO publication (arxiv_id, item_id, summary, authors, submitted_at,"
            " revised_at) VALUES ('2609.31282', ?, 'A summary', '[\"Ada Lovelace\"]',"
            " '2026-09-25T13:53:50Z', '2026-09-25T13:53:50Z')",
            (item_id,),
        )


@pytest.mark.parametrize("authors", ["Ada Lovelace", '{"name": "Ada Lovelace"}', "[]"])
def test_authors_that_are_not_a_json_list_of_names_are_refused(
    database, item_id, authors
):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            "INSERT INTO publication (arxiv_id, item_id, title, summary, authors,"
            " submitted_at, revised_at) VALUES ('2609.31282', ?, 'A title', 'A summary',"
            " ?, '2026-09-25T13:53:50Z', '2026-09-25T13:53:50Z')",
            (item_id, authors),
        )


def test_two_publications_cannot_point_to_the_same_item(database, item_id):
    columns, values = PAPER_COLUMNS
    statement = (
        f"INSERT INTO publication (arxiv_id, item_id, {columns})"  # noqa: S608 — constants
        f" VALUES (?, ?, {values})"
    )
    database.execute(statement, ("2609.31282", item_id))

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        database.execute(statement, ("2609.33401", item_id))


def test_a_vulnerability_with_its_item_and_its_kev_columns_is_accepted(
    database, item_id
):
    columns, values = KEV_COLUMNS
    database.execute(
        f"INSERT INTO vulnerability (cve_id, item_id, {columns})"  # noqa: S608 — constants
        f" VALUES ('CVE-2026-86950', ?, {values})",
        (item_id,),
    )

    assert database.execute("SELECT count(*) FROM vulnerability").fetchone() == (1,)


@pytest.mark.parametrize(
    "column, value",
    [("name", "A name"), ("vendor", "Apple"), ("revised_at", "2026-10-05T09:30:00Z")],
)
def test_a_vulnerability_without_item_but_with_a_kev_column_is_refused(
    database, column, value
):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            f"INSERT INTO vulnerability (cve_id, {column})"  # noqa: S608 — test parameters
            " VALUES ('CVE-2026-86950', ?)",
            (value,),
        )


def test_a_vulnerability_with_its_item_but_without_vendor_is_refused(database, item_id):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            "INSERT INTO vulnerability (cve_id, item_id, name, description, product,"
            " date_added, ransomware_use) VALUES ('CVE-2026-86950', ?, 'A name',"
            " 'A description', 'Multiple Products', '2026-09-29T00:00:00Z', 'Unknown')",
            (item_id,),
        )


def test_a_ransomware_use_outside_the_list_is_refused(database, item_id):
    columns, values = KEV_COLUMNS
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            f"INSERT INTO vulnerability (cve_id, item_id, {columns})"  # noqa: S608 — constants
            f" VALUES ('CVE-2026-86950', ?, {values.replace('Unknown', 'Yes')})",
            (item_id,),
        )


def test_a_cve_identifier_is_unique(database):
    database.execute("INSERT INTO vulnerability (cve_id) VALUES ('CVE-2026-86950')")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        database.execute("INSERT INTO vulnerability (cve_id) VALUES ('CVE-2026-86950')")


def test_the_ecosystems_of_the_schema_are_those_of_the_advisories():
    schema = DATABASE_SCRIPTS.joinpath("schema.sql").read_text()
    (allowed_values,) = re.findall(r"ecosystem IN \(([^)]*)\)", schema)

    assert set(re.findall(r"'(\w+)'", allowed_values)) == set(ECOSYSTEMS)


INSERT_TRACKED_REPOSITORY = (
    "INSERT INTO tracked_repository (repository_name, ecosystem, packages)"
    " VALUES (?, ?, ?) RETURNING id"
)


@pytest.fixture
def tracked_repository_id(database):
    return database.execute(
        INSERT_TRACKED_REPOSITORY,
        ("anthropics/claude-code", "npm", '["@anthropic-ai/claude-code"]'),
    ).fetchone()[0]


def test_an_ecosystem_outside_the_list_is_refused(database):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            INSERT_TRACKED_REPOSITORY, ("rust-lang/rust", "cargo", '["rustc"]')
        )


@pytest.mark.parametrize("packages", ["langchain", "[]"])
def test_tracked_packages_that_are_not_a_json_list_are_refused(database, packages):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            INSERT_TRACKED_REPOSITORY, ("langchain-ai/langchain", "pip", packages)
        )


def test_a_tracked_repository_name_is_unique_whatever_its_case(
    database, tracked_repository_id
):
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        database.execute(
            INSERT_TRACKED_REPOSITORY,
            ("Anthropics/Claude-Code", "npm", '["@anthropic-ai/claude-code"]'),
        )


def insert_item(database, kind):
    database.execute(
        "INSERT OR IGNORE INTO raw_data (id, source_id, raw_file_path, stream,"
        " collected_at) VALUES (1, 1, 'automated_watch/x/2026-10-05T093000Z.json',"
        " 'x', '2026-10-05T09:30:00Z')"
    )
    return database.execute(
        "INSERT INTO item (kind, raw_data_id) VALUES (?, 1) RETURNING id", (kind,)
    ).fetchone()[0]


INSERT_RELEASE = (
    "INSERT INTO release (item_id, kind, tracked_repository_id, release_id, tag_name,"
    " name, body, published_at, url) VALUES (?, ?, ?, ?, 'v2.1.287', 'v2.1.287',"
    " '## What''s changed', '2026-10-01T18:00:22Z',"
    " 'https://github.com/anthropics/claude-code/releases/tag/v2.1.287')"
)
INSERT_ADVISORY = (
    "INSERT INTO advisory (item_id, kind, ghsa_id, vulnerability_id, summary,"
    " published_at, url, packages) VALUES (?, ?, ?, ?, 'A summary',"
    " '2026-06-25T18:25:42Z', 'https://github.com/advisories/GHSA-fjqc-hq36-qh5p', ?)"
)


def test_a_release_of_its_tracked_repository_is_accepted(
    database, tracked_repository_id
):
    item_id = insert_item(database, "release")
    database.execute(
        INSERT_RELEASE, (item_id, "release", tracked_repository_id, 401174143)
    )

    assert database.execute("SELECT count(*) FROM release").fetchone() == (1,)


def test_a_release_without_tracked_repository_is_refused(database):
    item_id = insert_item(database, "release")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        database.execute(INSERT_RELEASE, (item_id, "release", 99, 401174143))


def test_a_release_identifier_is_unique(database, tracked_repository_id):
    database.execute(
        INSERT_RELEASE,
        (insert_item(database, "release"), "release", tracked_repository_id, 1),
    )

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        database.execute(
            INSERT_RELEASE,
            (insert_item(database, "release"), "release", tracked_repository_id, 1),
        )


def test_a_release_pointing_to_an_item_of_another_kind_is_refused(
    database, tracked_repository_id
):
    paper_item_id = insert_item(database, "paper")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        database.execute(
            INSERT_RELEASE, (paper_item_id, "release", tracked_repository_id, 1)
        )


@pytest.mark.parametrize("kind", [None, "paper"])
def test_a_release_whose_kind_is_not_release_is_refused(
    database, tracked_repository_id, kind
):
    paper_item_id = insert_item(database, "paper")

    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL|CHECK"):
        database.execute(
            INSERT_RELEASE, (paper_item_id, kind, tracked_repository_id, 1)
        )


def test_an_advisory_without_vulnerability_is_accepted(database):
    item_id = insert_item(database, "advisory")
    database.execute(
        INSERT_ADVISORY,
        (item_id, "advisory", "GHSA-fjqc-hq36-qh5p", None, '["langgraph-checkpoint"]'),
    )

    assert database.execute("SELECT count(*) FROM advisory").fetchone() == (1,)


def test_an_advisory_identifier_is_unique(database):
    parameters = ("advisory", "GHSA-fjqc-hq36-qh5p", None, '["langgraph"]')
    database.execute(INSERT_ADVISORY, (insert_item(database, "advisory"), *parameters))

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        database.execute(
            INSERT_ADVISORY, (insert_item(database, "advisory"), *parameters)
        )


@pytest.mark.parametrize("kind", [None, "paper"])
def test_an_advisory_whose_kind_is_not_advisory_is_refused(database, kind):
    paper_item_id = insert_item(database, "paper")

    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL|CHECK"):
        database.execute(
            INSERT_ADVISORY,
            (paper_item_id, kind, "GHSA-fjqc-hq36-qh5p", None, '["langgraph"]'),
        )


def test_an_advisory_pointing_to_an_item_of_another_kind_is_refused(database):
    paper_item_id = insert_item(database, "paper")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        database.execute(
            INSERT_ADVISORY,
            (paper_item_id, "advisory", "GHSA-fjqc-hq36-qh5p", None, '["langgraph"]'),
        )


@pytest.mark.parametrize("packages", ["langgraph", '{"name": "langgraph"}', "[]"])
def test_advisory_packages_that_are_not_a_json_list_are_refused(database, packages):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        database.execute(
            INSERT_ADVISORY,
            (
                insert_item(database, "advisory"),
                "advisory",
                "GHSA-fjqc-hq36-qh5p",
                None,
                packages,
            ),
        )
