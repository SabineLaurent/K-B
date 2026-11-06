"""The SQL of the purge: the watch past its duration, the references nothing cites any more, the
tracked repositories no longer tracked, and the rows of the registry whose raw file is gone
(docs/registre-traitements.md, steps 2 and 3)."""

from typing import NamedTuple

from k_b.database.engine import Connection

SELECT_SOURCES = "SELECT id, source_code, acquisition_mode FROM source ORDER BY id"

# The items of a source collected before the bound: read once, then deleted by id.
SELECT_EXPIRED_ITEM_IDS = """
SELECT item.id FROM item JOIN raw_data ON raw_data.id = item.raw_data_id
WHERE raw_data.source_id = :source_id AND raw_data.collected_at < :bound
"""

# No cascade goes to the subtypes: the rows of the three of the watch go before their items. A
# vulnerability has none here: CISA KEV is a state catalog, never purged, and the foreign key of
# vulnerability refuses the purge of its item (the purge fails closed).
DELETE_RELEASE_OF_ITEM = "DELETE FROM release WHERE item_id = ?"
DELETE_ADVISORY_OF_ITEM = "DELETE FROM advisory WHERE item_id = ?"
DELETE_NEWSLETTER_ARTICLE_OF_ITEM = "DELETE FROM newsletter_article WHERE item_id = ?"

# A paper becomes a reference, its arXiv identifier alone, authors gone (the CHECK of
# publication empties the five columns together): one still cited keeps it, the others go with
# DELETE_UNCITED_PUBLICATIONS.
EMPTY_PAPER_OF_ITEM = """
UPDATE publication SET item_id = NULL, title = NULL, summary = NULL, authors = NULL,
    submitted_at = NULL, revised_at = NULL
WHERE item_id = ?
"""

# Its links to tags and its highlights go by cascade (schema.sql).
DELETE_ITEM = "DELETE FROM item WHERE id = ?"

# A trend row expires with the collection of its file, not the end of its window (decision of
# Sabine of 2026-11-04).
DELETE_EXPIRED_TRENDS = """
DELETE FROM trend WHERE raw_data_id IN (
    SELECT id FROM raw_data WHERE source_id = :source_id AND collected_at < :bound
)
"""

DELETE_UNCITED_PUBLICATIONS = """
DELETE FROM publication
WHERE item_id IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM newsletter_article
        WHERE newsletter_article.publication_id = publication.id
    )
    AND NOT EXISTS (
        SELECT 1 FROM zotero_entry WHERE zotero_entry.publication_id = publication.id
    )
"""

DELETE_UNCITED_VULNERABILITIES = """
DELETE FROM vulnerability
WHERE item_id IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM advisory WHERE advisory.vulnerability_id = vulnerability.id
    )
"""

SELECT_TRACKED_REPOSITORIES_WITHOUT_RELEASE = """
SELECT id, repository_name FROM tracked_repository
WHERE NOT EXISTS (
    SELECT 1 FROM release WHERE release.tracked_repository_id = tracked_repository.id
)
"""

# The condition again: a release imported meanwhile keeps its repository.
DELETE_TRACKED_REPOSITORY_WITHOUT_RELEASE = """
DELETE FROM tracked_repository
WHERE id = ?
    AND NOT EXISTS (
        SELECT 1 FROM release WHERE release.tracked_repository_id = tracked_repository.id
    )
"""

SELECT_UNCITED_RAW_DATA = """
SELECT id, source_id, raw_file_path, collected_at FROM raw_data
WHERE NOT EXISTS (SELECT 1 FROM item WHERE item.raw_data_id = raw_data.id)
    AND NOT EXISTS (SELECT 1 FROM trend WHERE trend.raw_data_id = raw_data.id)
"""

SELECT_LAST_COLLECTION_OF_EACH_SOURCE = """
SELECT source_id, max(collected_at) FROM raw_data GROUP BY source_id
"""

# The conditions again: an item or a trend row imported meanwhile keeps the row.
DELETE_UNCITED_RAW_DATA = """
DELETE FROM raw_data
WHERE id = ?
    AND NOT EXISTS (SELECT 1 FROM item WHERE item.raw_data_id = raw_data.id)
    AND NOT EXISTS (SELECT 1 FROM trend WHERE trend.raw_data_id = raw_data.id)
"""


class SourceRow(NamedTuple):
    """A source of the base and its acquisition mode."""

    id: int
    source_code: str
    acquisition_mode: str


class TrackedRepositoryRow(NamedTuple):
    """A tracked repository of the base."""

    id: int
    repository_name: str


class RawDataRow(NamedTuple):
    """A row of the registry of the raw files imported."""

    id: int
    source_id: int
    raw_file_path: str
    collected_at: str


def read_sources(connection: Connection) -> list[SourceRow]:
    """The sources of the base, with their acquisition mode."""
    return [SourceRow(*row) for row in connection.execute(SELECT_SOURCES)]


def delete_expired_items(connection: Connection, source_id: int, bound: str) -> int:
    """Delete the items of a source collected before the bound, with their subtypes; a paper
    keeps its arXiv identifier as a reference. Return how many items."""
    item_ids = [
        (item_id,)
        for (item_id,) in connection.execute(
            SELECT_EXPIRED_ITEM_IDS, {"source_id": source_id, "bound": bound}
        )
    ]
    for statement in (
        DELETE_RELEASE_OF_ITEM,
        DELETE_ADVISORY_OF_ITEM,
        DELETE_NEWSLETTER_ARTICLE_OF_ITEM,
        EMPTY_PAPER_OF_ITEM,
    ):
        connection.executemany(statement, item_ids)
    return connection.executemany(DELETE_ITEM, item_ids).rowcount


def delete_expired_trends(connection: Connection, source_id: int, bound: str) -> int:
    """Delete the trend rows of a source whose file was collected before the bound; return how
    many."""
    return connection.execute(
        DELETE_EXPIRED_TRENDS, {"source_id": source_id, "bound": bound}
    ).rowcount


def delete_uncited_references(connection: Connection) -> int:
    """Delete the papers and the CVE without item that nothing cites any more; return how many."""
    return (
        connection.execute(DELETE_UNCITED_PUBLICATIONS).rowcount
        + connection.execute(DELETE_UNCITED_VULNERABILITIES).rowcount
    )


def read_tracked_repositories_without_release(
    connection: Connection,
) -> list[TrackedRepositoryRow]:
    """The tracked repositories no release cites."""
    return [
        TrackedRepositoryRow(*row)
        for row in connection.execute(SELECT_TRACKED_REPOSITORIES_WITHOUT_RELEASE)
    ]


def delete_tracked_repository_without_release(
    connection: Connection, repository_id: int
) -> int:
    """Delete a tracked repository if no release cites it; return 1 if deleted, else 0."""
    return connection.execute(
        DELETE_TRACKED_REPOSITORY_WITHOUT_RELEASE, (repository_id,)
    ).rowcount


def read_uncited_raw_data(connection: Connection) -> list[RawDataRow]:
    """The rows of the registry that no item and no trend row cites."""
    return [RawDataRow(*row) for row in connection.execute(SELECT_UNCITED_RAW_DATA)]


def read_last_collection_of_each_source(
    connection: Connection,
) -> dict[int, str]:
    """The latest collection the registry holds, by source id."""
    return {
        source_id: str(collected_at)
        for source_id, collected_at in connection.execute(
            SELECT_LAST_COLLECTION_OF_EACH_SOURCE
        )
    }


def delete_uncited_raw_data(connection: Connection, raw_data_id: int) -> int:
    """Delete a row of the registry if nothing cites it; return 1 if deleted, else 0."""
    return connection.execute(DELETE_UNCITED_RAW_DATA, (raw_data_id,)).rowcount
