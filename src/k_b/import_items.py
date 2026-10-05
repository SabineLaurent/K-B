"""Import the raw files into the items database (docs/specs-collecte.md, step 4).

Read, merge, then write the base in one transaction: an error in the base writes nothing there.
The log is written after the base, whole or not at all. Run again on the same raw, the import
gives the same base and the same log.
"""

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from k_b.database import connect_database
from k_b.items import Item
from k_b.merge import Discard, merge_items
from k_b.raw_items import Rejection, read_raw_items

# The date format the CHECK constraints of schema.sql accept.
DATABASE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Every field of an item but its identifier is rewritten when the item is imported again:
# a newer arXiv revision replaces the paper, under the same item_id.
UPSERT_ITEM = """
INSERT INTO item (
    source_code, source_item_id, title, url, published_at, revised_at, saved_at, summary,
    collection_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source_code, source_item_id) DO UPDATE SET
    title = excluded.title,
    url = excluded.url,
    published_at = excluded.published_at,
    revised_at = excluded.revised_at,
    saved_at = excluded.saved_at,
    summary = excluded.summary,
    collection_id = excluded.collection_id
RETURNING item_id
"""


class MissingDatabaseError(FileNotFoundError):
    pass


class ImportSummary(NamedTuple):
    item_count: int
    discard_count: int
    rejection_count: int


def import_items(raw_dir: Path, database_path: Path, log_path: Path) -> ImportSummary:
    """Write the merged items of the raw files into the base, then the log of what was left out.

    The base must exist: connecting to a missing file would create an empty one.
    """
    if not database_path.is_file():
        raise MissingDatabaseError(f"{database_path} does not exist")
    reading = read_raw_items(raw_dir)
    merged = merge_items(reading.items)
    connection = connect_database(database_path)
    try:
        # The context manager commits on success and rolls back on any error.
        with connection:
            for item in merged.items:
                write_item(connection, item)
            delete_orphan_authors(connection)
    finally:
        connection.close()
    write_import_log(log_path, reading.rejections, merged.discards)
    return ImportSummary(len(merged.items), len(merged.discards), len(reading.rejections))


def write_item(connection: sqlite3.Connection, item: Item) -> None:
    collection_id = write_collection(connection, item.collected_at, item.raw_file_path)
    (item_id,) = connection.execute(
        UPSERT_ITEM,
        (
            item.source_code,
            item.source_item_id,
            item.title,
            item.url,
            format_date(item.published_at),
            format_date(item.revised_at),
            format_date(item.saved_at),
            item.summary,
            collection_id,
        ),
    ).fetchone()
    write_authors(connection, item_id, item.authors)
    if item.repository_name is not None:
        connection.execute(
            "INSERT INTO repository (item_id, repository_name) VALUES (?, ?)"
            " ON CONFLICT (item_id) DO UPDATE SET repository_name = excluded.repository_name",
            (item_id, item.repository_name),
        )
    if item.is_vulnerability:
        connection.execute(
            "INSERT INTO vulnerability (item_id, cve) VALUES (?, ?)"
            " ON CONFLICT (item_id) DO UPDATE SET cve = excluded.cve",
            (item_id, item.cve),
        )


def write_collection(
    connection: sqlite3.Connection, collected_at: datetime, raw_file_path: str
) -> int:
    connection.execute(
        "INSERT INTO collection (collected_at, raw_file_path) VALUES (?, ?)"
        " ON CONFLICT (raw_file_path) DO NOTHING",
        (format_date(collected_at), raw_file_path),
    )
    (collection_id,) = connection.execute(
        "SELECT collection_id FROM collection WHERE raw_file_path = ?", (raw_file_path,)
    ).fetchone()
    return collection_id


def write_authors(connection: sqlite3.Connection, item_id: int, authors: tuple[str, ...]) -> None:
    """The authors of the item, in their order; a name repeated in the list is kept once.

    The base links an author to an item once (primary key item_id, author_id): a repeated name
    keeps its first position.
    """
    connection.execute("DELETE FROM item_author WHERE item_id = ?", (item_id,))
    for position, name in enumerate(dict.fromkeys(authors), start=1):
        connection.execute(
            "INSERT INTO author (name) VALUES (?) ON CONFLICT (name) DO NOTHING",
            (name,),
        )
        (author_id,) = connection.execute(
            "SELECT author_id FROM author WHERE name = ?", (name,)
        ).fetchone()
        connection.execute(
            "INSERT INTO item_author (item_id, author_id, position) VALUES (?, ?, ?)",
            (item_id, author_id, position),
        )


def delete_orphan_authors(connection: sqlite3.Connection) -> None:
    """An author whose items have all changed authors is personal data without use: deleted."""
    connection.execute(
        "DELETE FROM author WHERE author_id NOT IN (SELECT author_id FROM item_author)"
    )


def format_date(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(UTC).strftime(DATABASE_DATE_FORMAT)


def write_import_log(log_path: Path, rejections: list[Rejection], discards: list[Discard]) -> None:
    """One JSON line per rejection, then per duplicate removed; the file is rewritten each time.

    Written to a temporary file, then renamed over the log: a failed write leaves the previous
    log whole, and no temporary file behind.
    """
    lines = [
        {
            "kind": "rejection",
            "raw_file_path": rejection.raw_file_path,
            "reason": rejection.reason,
        }
        for rejection in rejections
    ] + [
        {
            "kind": "discard",
            "rule": discard.rule,
            "source_code": discard.item.source_code,
            "source_item_id": discard.item.source_item_id,
            "url": discard.item.url,
            "raw_file_path": discard.item.raw_file_path,
            "kept_url": discard.kept_url,
        }
        for discard in discards
    ]
    temporary_path = log_path.with_name(log_path.name + ".tmp")
    try:
        temporary_path.write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
        )
        os.replace(temporary_path, log_path)
    except BaseException:
        # BaseException: Ctrl-C during the write must not leave the temporary file either.
        temporary_path.unlink(missing_ok=True)
        raise
