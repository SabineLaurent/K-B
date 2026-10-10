import re
import sqlite3
import typing

import pytest

from k_b.config import RETENTION_YEARS_BY_ACQUISITION_MODE
from k_b.database.creation import DATABASE_SCRIPTS
from k_b.items import (
    MAX_COUNT_BY_KIND,
    MAX_LENGTH_BY_KIND,
    ItemKind,
)
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


# The column each bounded field of an item is written to (import_items.py).
COLUMN_BY_KIND_AND_FIELD = {
    ("paper", "source_item_id"): ("publication", "arxiv_id"),
    ("paper", "title"): ("publication", "title"),
    ("paper", "summary"): ("publication", "summary"),
    ("paper", "authors"): ("publication", "authors"),
    ("vulnerability", "cve"): ("vulnerability", "cve_id"),
    ("vulnerability", "title"): ("vulnerability", "name"),
    ("vulnerability", "summary"): ("vulnerability", "description"),
    ("vulnerability", "vendor"): ("vulnerability", "vendor"),
    ("vulnerability", "product"): ("vulnerability", "product"),
    ("release", "tag_name"): ("release", "tag_name"),
    ("release", "release_name"): ("release", "name"),
    ("release", "summary"): ("release", "body"),
    ("release", "url"): ("release", "url"),
    ("advisory", "source_item_id"): ("advisory", "ghsa_id"),
    ("advisory", "cve"): ("vulnerability", "cve_id"),
    ("advisory", "title"): ("advisory", "summary"),
    ("advisory", "url"): ("advisory", "url"),
    ("advisory", "package_names"): ("advisory", "packages"),
}


def read_table_definitions():
    """The definition of each table of schema.sql, without its comments."""
    schema = DATABASE_SCRIPTS.joinpath("schema.sql").read_text()
    statements = "\n".join(line.split("--")[0] for line in schema.splitlines())
    return dict(
        re.findall(r"CREATE TABLE (\w+) \((.*?)\) STRICT;", statements, re.DOTALL)
    )


def read_maximums_of_the_schema(check_pattern):
    return {
        (table, column): int(maximum)
        for table, definition in read_table_definitions().items()
        for column, maximum in re.findall(check_pattern, definition)
    }


def list_maximums_of_the_items(maximum_by_kind):
    """The maximum of each column, as the items hold it; two kinds that fill the same column
    must hold the same."""
    maximums = {}
    for kind, maximum_by_field in maximum_by_kind.items():
        for field, maximum in maximum_by_field.items():
            column = COLUMN_BY_KIND_AND_FIELD[kind, field]
            assert maximums.setdefault(column, maximum) == maximum
    return maximums


def test_each_maximum_length_of_the_items_is_the_check_of_its_column():
    # \b: not the length( inside json_array_length(.
    assert read_maximums_of_the_schema(
        r"\blength\((\w+)\) <= (\d+)"
    ) == list_maximums_of_the_items(MAX_LENGTH_BY_KIND)


def test_each_maximum_count_of_the_items_is_the_check_of_its_column():
    assert read_maximums_of_the_schema(
        r"json_array_length\((\w+)\) <= (\d+)"
    ) == list_maximums_of_the_items(MAX_COUNT_BY_KIND)


DATE = "2026-10-05T09:30:00Z"
# A day that does not exist, in the right form.
INVALID_DATE = "2026-02-30T09:30:00Z"
PAPER_ITEM_ID = 1
RELEASE_ITEM_ID = 2
ADVISORY_ITEM_ID = 3
REPOSITORY_ITEM_ID = 4

# A row every constraint of its table accepts, in a base that holds the rows of filled_database.
# The values are those of tests/fixtures (the collection), the long texts cut short; a new source,
# a highlight and a star gain have no collected example.
VALID_ROW_BY_TABLE = {
    "source": {
        "source_code": "rss",
        "label": "RSS",
        "source_type": "web_service",
        "acquisition_mode": "watch",
    },
    "raw_data": {
        "source_id": 1,
        "raw_file_path": "automated_watch/cisa_kev/2026-10-05T093000Z.csv",
        "stream": "cisa_kev",
        "collected_at": DATE,
    },
    "item": {"kind": "paper", "raw_data_id": 1},
    "publication": {
        "arxiv_id": "2609.31282",
        "item_id": PAPER_ITEM_ID,
        "title": (
            "Resource-Optimized and Energy-Aware Agentic AI Framework Anchored on"
            " Blockchain for Secure Software Supply Chains"
        ),
        "summary": "This paper proposes a blockchain-backed agentic security framework",
        "authors": '["Toqeer Ali Syed", "Asadullah Abdullah Khan"]',
        "submitted_at": "2026-09-25T13:53:50Z",
        "revised_at": "2026-09-25T13:53:50Z",
    },
    "highlight": {
        "zotero_key": "ABCD2345",
        "text": "A highlight",
        "highlighted_at": DATE,
        "item_id": PAPER_ITEM_ID,
    },
    "repository": {
        "item_id": PAPER_ITEM_ID,
        "repository_name": "anthropics/claude-code",
    },
    "star_gain": {
        "item_id": REPOSITORY_ITEM_ID,
        "window_end": DATE,
        "stars_gained": 3,
    },
    "vulnerability": {
        "cve_id": "CVE-2026-86950",
        "item_id": PAPER_ITEM_ID,
        "name": "Apple Multiple Products Out-of-Bounds Write Vulnerability",
        "description": "Apple iOS, macOS, and iPadOS contain an out-of-bounds write",
        "vendor": "Apple",
        "product": "Multiple Products",
        "date_added": "2026-09-29T00:00:00Z",
        "ransomware_use": "Unknown",
    },
    "tracked_repository": {
        "repository_name": "langchain-ai/langchain",
        "ecosystem": "pip",
        "packages": '["langchain"]',
    },
    "release": {
        "item_id": RELEASE_ITEM_ID,
        "kind": "release",
        "tracked_repository_id": 1,
        "release_id": 401174143,
        "tag_name": "v2.1.287",
        "name": "v2.1.287",
        "body": "## What's changed",
        "published_at": "2026-10-01T18:00:22Z",
        "url": "https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
    },
    "advisory": {
        "item_id": ADVISORY_ITEM_ID,
        "kind": "advisory",
        "ghsa_id": "GHSA-fjqc-hq36-qh5p",
        "summary": "LangGraph Checkpoint: Unsafe JSON deserialization in checkpoint loading",
        "published_at": "2026-06-25T18:25:42Z",
        "url": "https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
        "packages": '["langgraph-checkpoint"]',
    },
}


def json_list(count):
    return "[" + ", ".join(['"x"'] * count) + "]"


# One refused value per CHECK of schema.sql: its table, the CHECK as SQLite names it when it
# refuses, and the change that makes a valid row of the table break this CHECK alone.
REFUSED_VALUES = [
    ("source", "source_type IN", {"source_type": "rss_feed"}),
    ("source", "acquisition_mode IN", {"acquisition_mode": "archive"}),
    ("raw_data", "collected_at IS strftime", {"collected_at": INVALID_DATE}),
    ("item", "kind IN", {"kind": "tweet"}),
    ("publication", "length(arxiv_id) <= 20", {"arxiv_id": "2" * 21}),
    ("publication", "length(title) <= 500", {"title": "x" * 501}),
    ("publication", "length(summary) <= 5000", {"summary": "x" * 5_001}),
    ("publication", "json_valid(authors)", {"authors": "[]"}),
    (
        "publication",
        "json_array_length(authors) <= 1000",
        {"authors": json_list(1_001)},
    ),
    ("publication", "submitted_at IS strftime", {"submitted_at": INVALID_DATE}),
    ("publication", "revised_at IS strftime", {"revised_at": INVALID_DATE}),
    ("publication", "(item_id IS NULL) = (title IS NULL)", {"title": None}),
    ("highlight", "highlighted_at IS strftime", {"highlighted_at": INVALID_DATE}),
    ("repository", "repository_name GLOB", {"repository_name": "claude-code"}),
    ("star_gain", "window_end IS strftime", {"window_end": INVALID_DATE}),
    ("star_gain", "stars_gained >= 0", {"stars_gained": -1}),
    ("vulnerability", "cve_id GLOB", {"cve_id": "CVE-26-1"}),
    (
        "vulnerability",
        "length(cve_id) <= 20",
        {"cve_id": "CVE-2026-" + "1" * 12},
    ),
    ("vulnerability", "length(name) <= 500", {"name": "x" * 501}),
    ("vulnerability", "length(description) <= 5000", {"description": "x" * 5_001}),
    ("vulnerability", "length(vendor) <= 200", {"vendor": "x" * 201}),
    ("vulnerability", "length(product) <= 500", {"product": "x" * 501}),
    ("vulnerability", "date_added IS strftime", {"date_added": INVALID_DATE}),
    ("vulnerability", "ransomware_use IN", {"ransomware_use": "Yes"}),
    ("vulnerability", "revised_at IS strftime", {"revised_at": INVALID_DATE}),
    ("vulnerability", "withdrawn_at IS strftime", {"withdrawn_at": INVALID_DATE}),
    ("vulnerability", "(item_id IS NULL) = (name IS NULL)", {"vendor": None}),
    ("tracked_repository", "repository_name GLOB", {"repository_name": "langchain"}),
    ("tracked_repository", "ecosystem IN", {"ecosystem": "cargo"}),
    ("tracked_repository", "json_valid(packages)", {"packages": "[]"}),
    ("release", "kind = 'release'", {"kind": "paper"}),
    ("release", "length(tag_name) > 0", {"tag_name": ""}),
    ("release", "length(tag_name) <= 255", {"tag_name": "x" * 256}),
    ("release", "length(name) <= 255", {"name": "x" * 256}),
    ("release", "length(body) <= 125000", {"body": "x" * 125_001}),
    ("release", "published_at IS strftime", {"published_at": INVALID_DATE}),
    ("release", "url GLOB", {"url": "http://github.com/anthropics/claude-code"}),
    ("release", "length(url) <= 2000", {"url": "https://" + "x" * 1_993}),
    ("advisory", "kind = 'advisory'", {"kind": "paper"}),
    ("advisory", "ghsa_id GLOB", {"ghsa_id": "CVE-2026-48775"}),
    ("advisory", "length(ghsa_id) <= 19", {"ghsa_id": "GHSA-fjqc-hq36-qh5pp"}),
    ("advisory", "length(summary) <= 1024", {"summary": "x" * 1_025}),
    ("advisory", "published_at IS strftime", {"published_at": INVALID_DATE}),
    ("advisory", "url GLOB", {"url": "http://github.com/advisories"}),
    ("advisory", "length(url) <= 2000", {"url": "https://" + "x" * 1_993}),
    ("advisory", "json_valid(packages)", {"packages": "[]"}),
    ("advisory", "json_array_length(packages) <= 100", {"packages": json_list(101)}),
]


@pytest.fixture
def filled_database(database):
    """The base with the rows a valid row of each table points to."""
    insert_row(
        database,
        "raw_data",
        id=1,
        raw_file_path="automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml",
        stream="arxiv_cscr_x_csai",
    )
    for item_id, kind in (
        (PAPER_ITEM_ID, "paper"),
        (RELEASE_ITEM_ID, "release"),
        (ADVISORY_ITEM_ID, "advisory"),
        (REPOSITORY_ITEM_ID, "paper"),
    ):
        insert_row(database, "item", id=item_id, kind=kind)
    insert_row(
        database, "tracked_repository", id=1, repository_name="anthropics/claude-code"
    )
    insert_row(database, "repository", item_id=REPOSITORY_ITEM_ID)
    return database


def insert_row(database, table, **changes):
    row = VALID_ROW_BY_TABLE[table] | changes
    database.execute(
        f"INSERT INTO {table} ({', '.join(row)})"  # noqa: S608 — constants of the tests
        f" VALUES ({', '.join('?' * len(row))})",
        tuple(row.values()),
    )


@pytest.mark.parametrize("table", VALID_ROW_BY_TABLE)
def test_the_valid_row_of_each_table_is_accepted(filled_database, table):
    insert_row(filled_database, table)


@pytest.mark.parametrize("table, check, changes", REFUSED_VALUES)
def test_a_value_each_check_forbids_is_refused(filled_database, table, check, changes):
    with pytest.raises(
        sqlite3.IntegrityError, match=re.escape(f"CHECK constraint failed: {check}")
    ):
        insert_row(filled_database, table, **changes)


def test_each_check_of_the_schema_has_its_refused_value():
    """A CHECK added without its refused value, or two refused values for the same CHECK, fail
    here."""
    definitions = read_table_definitions()
    checks_with_a_refused_value = {(table, check) for table, check, _ in REFUSED_VALUES}

    for table, check in checks_with_a_refused_value:
        assert definitions[table].count(f"CHECK ({check}") == 1, (table, check)
    assert len(checks_with_a_refused_value) == len(REFUSED_VALUES)
    assert len(REFUSED_VALUES) == sum(
        len(re.findall(r"\bCHECK \(", definition))
        for definition in definitions.values()
    )


# The columns the source of truth of a reference table fills: the table CHECK holds one clause
# for each, "filled if and only if item_id is".
COLUMNS_FILLED_WITH_THEIR_ITEM = {
    "publication": ("title", "summary", "authors", "submitted_at", "revised_at"),
    "vulnerability": (
        "name",
        "description",
        "vendor",
        "product",
        "date_added",
        "ransomware_use",
    ),
}
# The columns of vulnerability that may be filled only with item_id, in the last clause.
COLUMNS_ALLOWED_ONLY_WITH_THEIR_ITEM = ("revised_at", "withdrawn_at")


@pytest.mark.parametrize(
    "table, column",
    [
        (table, column)
        for table, columns in COLUMNS_FILLED_WITH_THEIR_ITEM.items()
        for column in columns
    ],
)
def test_a_reference_row_with_its_item_but_without_one_of_its_columns_is_refused(
    filled_database, table, column
):
    with pytest.raises(
        sqlite3.IntegrityError,
        match=re.escape("CHECK constraint failed: (item_id IS NULL) = ("),
    ):
        insert_row(filled_database, table, **{column: None})


@pytest.mark.parametrize("column", COLUMNS_ALLOWED_ONLY_WITH_THEIR_ITEM)
def test_a_vulnerability_without_item_but_with_a_later_date_is_refused(
    filled_database, column
):
    without_item = dict.fromkeys(
        ("item_id", *COLUMNS_FILLED_WITH_THEIR_ITEM["vulnerability"])
    )

    with pytest.raises(
        sqlite3.IntegrityError,
        match=re.escape("CHECK constraint failed: (item_id IS NULL) = ("),
    ):
        insert_row(filled_database, "vulnerability", **without_item, **{column: DATE})


def test_each_clause_of_the_reference_checks_has_its_refused_value():
    """A clause added to these CHECK, or lost, without its refused value fails here."""
    definitions = read_table_definitions()

    for table, columns in COLUMNS_FILLED_WITH_THEIR_ITEM.items():
        assert re.findall(
            r"\(item_id IS NULL\) = \((\w+) IS NULL\)", definitions[table]
        ) == list(columns)
    assert re.findall(
        r"item_id IS NOT NULL OR \((\w+) IS NULL AND (\w+) IS NULL\)",
        definitions["vulnerability"],
    ) == [COLUMNS_ALLOWED_ONLY_WITH_THEIR_ITEM]
