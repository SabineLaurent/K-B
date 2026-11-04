"""The purge of the base: the watch past its duration, the references nothing cites any more and
the tracked repositories no longer tracked (docs/registre-traitements.md, step 2)."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.database.connection import connect_database
from k_b.database.creation import create_database
from k_b.purge.base import BasePurgeCount, purge_expired_rows

ITEMS_DATABASE_SCRIPT = Path(__file__).parents[1] / "fixtures" / "items_database.sql"
STATE_CATALOG_SOURCE_CODES = frozenset({"zotero", "cisa_kev"})
TRACKED_REPOSITORY_NAMES = ("anthropics/claude-code",)
# Three years after the collections of 2026-10-05 (arXiv, CISA KEV, the releases, the
# advisories, Zotero), before those of 2026-10-11 (TLDR, GH Archive) and 2026-10-17 (a clip).
AFTER_THE_FIRST_COLLECTIONS = datetime(2029, 10, 8, tzinfo=UTC)
# Long after every collection of the test base.
AFTER_EVERY_COLLECTION = datetime(2099, 1, 1, tzinfo=UTC)
# Before any duration ends.
BEFORE_ANY_DURATION_ENDS = datetime(2026, 11, 4, tzinfo=UTC)


@pytest.fixture
def database_path(tmp_path):
    """A base of its own, the test base of the readers: every table, as the collection fills it."""
    path = tmp_path / "k-b.sqlite"
    create_database(path)
    connection = connect_database(path)
    try:
        connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
    finally:
        connection.close()
    return path


def fetch_column(database_path, query, parameters=()):
    connection = sqlite3.connect(database_path)
    try:
        return [row[0] for row in connection.execute(query, parameters)]
    finally:
        connection.close()


def execute(database_path, statement, parameters=()):
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            connection.execute(statement, parameters)
    finally:
        connection.close()


def dump(database_path):
    connection = sqlite3.connect(database_path)
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def purge(
    database_path, imported_at, tracked_repository_names=TRACKED_REPOSITORY_NAMES
):
    return purge_expired_rows(
        database_path, imported_at, STATE_CATALOG_SOURCE_CODES, tracked_repository_names
    )


def test_the_watch_collected_more_than_three_years_ago_leaves_with_its_subtypes(
    database_path,
):
    count = purge(database_path, AFTER_THE_FIRST_COLLECTIONS)

    # Left: the CISA KEV catalog (3 to 5), TLDR (11 to 13), Zotero (14 to 16) and the clip (18).
    assert fetch_column(database_path, "SELECT id FROM item ORDER BY id") == [
        3,
        4,
        5,
        11,
        12,
        13,
        14,
        15,
        16,
        18,
    ]
    assert fetch_column(database_path, "SELECT count(*) FROM release") == [0]
    assert fetch_column(database_path, "SELECT count(*) FROM advisory") == [0]
    # The two papers had no other citation: their rows are gone, authors with them; the two
    # references Zotero cites stay.
    assert fetch_column(
        database_path, "SELECT arxiv_id FROM publication ORDER BY arxiv_id"
    ) == ["2609.00001", "2609.00002"]
    # The CVE only advisory 17 cited is gone; the three of the catalog stay.
    assert fetch_column(
        database_path, "SELECT cve_id FROM vulnerability ORDER BY cve_id"
    ) == ["CVE-2020-29583", "CVE-2026-86950", "CVE-2026-88772"]
    assert fetch_column(database_path, "SELECT count(*) FROM trend") == [7]
    assert count == BasePurgeCount(
        item_count=8, trend_count=0, reference_count=3, tracked_repository_count=0
    )


@pytest.mark.parametrize(
    "citation",
    [
        (
            "UPDATE zotero_entry SET publication_id = (SELECT id FROM publication"
            " WHERE arxiv_id = '2609.31282') WHERE item_id = 16"
        ),
        (
            "UPDATE newsletter_article SET publication_id = (SELECT id FROM publication"
            " WHERE arxiv_id = '2609.31282') WHERE item_id = 11"
        ),
    ],
)
def test_a_paper_still_cited_keeps_only_its_arxiv_identifier(database_path, citation):
    execute(database_path, citation)

    purge(database_path, AFTER_THE_FIRST_COLLECTIONS)

    connection = sqlite3.connect(database_path)
    row = connection.execute(
        "SELECT item_id, title, summary, authors, submitted_at, revised_at FROM publication"
        " WHERE arxiv_id = '2609.31282'"
    ).fetchone()
    connection.close()
    assert row == (None, None, None, None, None, None)


def test_the_state_catalogs_and_the_library_are_kept_without_limit(database_path):
    count = purge(database_path, AFTER_EVERY_COLLECTION)

    assert fetch_column(database_path, "SELECT id FROM item ORDER BY id") == [
        3,
        4,
        5,
        14,
        15,
        16,
        18,
    ]
    assert fetch_column(database_path, "SELECT count(*) FROM highlight") == [3]
    assert fetch_column(database_path, "SELECT count(*) FROM trend") == [0]
    assert count.item_count == 11
    assert count.trend_count == 7


@pytest.mark.parametrize(
    ("imported_at", "trend_count"),
    [
        # Three years after the end of both windows (2026-10-09 and 2026-10-10), before the
        # collection of their file (2026-10-11T09:30:00Z): the duration counts from the
        # collection.
        (datetime(2029, 10, 10, 12, tzinfo=UTC), 7),
        # The bound itself is kept.
        (datetime(2029, 10, 11, 9, 30, tzinfo=UTC), 7),
        # A second after.
        (datetime(2029, 10, 11, 9, 30, 1, tzinfo=UTC), 0),
    ],
)
def test_a_trend_row_leaves_three_years_after_the_collection_of_its_file(
    database_path, imported_at, trend_count
):
    purge(database_path, imported_at)

    assert fetch_column(database_path, "SELECT count(*) FROM trend") == [trend_count]


@pytest.mark.parametrize(
    ("imported_at", "tracked_repository_names", "repository_count"),
    [
        # Out of the list, its releases purged: gone.
        (AFTER_THE_FIRST_COLLECTIONS, (), 0),
        # Still in the list, whatever the case: kept.
        (AFTER_THE_FIRST_COLLECTIONS, ("Anthropics/Claude-Code",), 1),
        # Out of the list, its releases still in the base: kept.
        (BEFORE_ANY_DURATION_ENDS, (), 1),
    ],
)
def test_a_tracked_repository_leaves_once_out_of_the_list_and_without_release(
    database_path, imported_at, tracked_repository_names, repository_count
):
    count = purge(database_path, imported_at, tracked_repository_names)

    assert fetch_column(database_path, "SELECT count(*) FROM tracked_repository") == [
        repository_count
    ]
    assert count.tracked_repository_count == 1 - repository_count


def test_a_purge_before_any_duration_ends_changes_nothing(database_path):
    before = dump(database_path)

    count = purge(database_path, BEFORE_ANY_DURATION_ENDS)

    assert dump(database_path) == before
    assert count == BasePurgeCount(0, 0, 0, 0)


def test_an_expired_item_of_a_state_catalog_fails_the_purge_and_changes_nothing(
    database_path,
):
    """A vulnerability item never expires, CISA KEV being a state catalog: given without it, the
    foreign key of vulnerability refuses the purge, whole."""
    before = dump(database_path)

    with pytest.raises(sqlite3.IntegrityError):
        purge_expired_rows(
            database_path,
            AFTER_THE_FIRST_COLLECTIONS,
            frozenset({"zotero"}),
            TRACKED_REPOSITORY_NAMES,
        )

    assert dump(database_path) == before


def test_the_log_gives_numbers_never_a_name(database_path, caplog):
    caplog.set_level(logging.INFO)

    purge(database_path, AFTER_THE_FIRST_COLLECTIONS, ())

    assert (
        "base purge: 8 items, 0 trend rows, 3 references, 1 tracked repositories deleted"
        in caplog.messages
    )
    assert "claude-code" not in caplog.text
    assert "2609." not in caplog.text
