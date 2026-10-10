"""Import the raw files into the items database (docs/specs-collecte.md, step 4).

Read, merge, then write the base in one transaction: an error in the base writes nothing there.
The log is written after the base, whole or not at all. Run again on the same raw, the import
gives the same base and the same log.
"""

import json
import os
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from k_b.database.connection import connect_database
from k_b.items import Item, ItemKind
from k_b.merge import Discard, merge_items
from k_b.raw_items import Rejection, read_raw_items
from k_b.raw_store import find_stream
from k_b.source_contract import SourceKind

# The date format the CHECK constraints of schema.sql accept.
DATABASE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# A paper seen again (a newer arXiv revision) rewrites its arXiv columns, under the same item.
UPSERT_PUBLICATION = """
INSERT INTO publication (arxiv_id, item_id, title, summary, authors, submitted_at, revised_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (arxiv_id) DO UPDATE SET
    item_id = excluded.item_id,
    title = excluded.title,
    summary = excluded.summary,
    authors = excluded.authors,
    submitted_at = excluded.submitted_at,
    revised_at = excluded.revised_at
"""

# revised_at and withdrawn_at are left as they are: their rules are #105 and #106.
UPSERT_VULNERABILITY = """
INSERT INTO vulnerability (
    cve_id, item_id, name, description, vendor, product, date_added, ransomware_use
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (cve_id) DO UPDATE SET
    item_id = excluded.item_id,
    name = excluded.name,
    description = excluded.description,
    vendor = excluded.vendor,
    product = excluded.product,
    date_added = excluded.date_added,
    ransomware_use = excluded.ransomware_use
"""


class MissingDatabaseError(FileNotFoundError):
    pass


class UnknownSourceError(LookupError):
    """An item's source_code has no row in the source table of the base."""


class KindWithoutTableError(LookupError):
    """An item's kind has no table in the base yet: the import refuses it."""


class ImportSummary(NamedTuple):
    item_count: int
    discard_count: int
    rejection_count: int


def import_items(
    raw_dir: Path,
    database_path: Path,
    log_path: Path,
    kinds: Sequence[SourceKind],
) -> ImportSummary:
    """Write the merged items of the raw files into the base, then the log of what was left out.

    The base must exist: connecting to a missing file would create an empty one.
    """
    if not database_path.is_file():
        raise MissingDatabaseError(f"{database_path} does not exist")
    reading = read_raw_items(raw_dir, kinds)
    merged = merge_items(reading.items)
    connection = connect_database(database_path)
    try:
        # The context manager commits on success and rolls back on any error.
        with connection:
            for item in merged.items:
                write_item(connection, item)
    finally:
        connection.close()
    write_import_log(log_path, reading.rejections, merged.discards)
    return ImportSummary(
        len(merged.items), len(merged.discards), len(reading.rejections)
    )


def write_item(connection: sqlite3.Connection, item: Item) -> None:
    write_kind = WRITER_BY_KIND.get(item.kind)
    if write_kind is None:
        raise KindWithoutTableError(f"kind without a table in the base: {item.kind}")
    raw_data_id = write_raw_data(
        connection, item.source_code, item.collected_at, item.raw_file_path
    )
    write_kind(connection, item, raw_data_id)


def write_paper(connection: sqlite3.Connection, item: Item, raw_data_id: int) -> None:
    """The arXiv item and its publication, found by its arXiv identifier."""
    row = connection.execute(
        "SELECT item_id FROM publication WHERE arxiv_id = ?", (item.source_item_id,)
    ).fetchone()
    item_id = upsert_item(connection, "paper", raw_data_id, row and row[0])
    connection.execute(
        UPSERT_PUBLICATION,
        (
            item.source_item_id,
            item_id,
            item.title,
            item.summary,
            json.dumps(list(item.authors), ensure_ascii=False),
            format_date(item.published_at),
            format_date(item.revised_at),
        ),
    )


def write_vulnerability(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> None:
    """The CISA KEV item and its vulnerability, found by its CVE."""
    row = connection.execute(
        "SELECT item_id FROM vulnerability WHERE cve_id = ?", (item.cve,)
    ).fetchone()
    item_id = upsert_item(connection, "vulnerability", raw_data_id, row and row[0])
    connection.execute(
        UPSERT_VULNERABILITY,
        (
            item.cve,
            item_id,
            item.title,
            item.summary,
            item.vendor,
            item.product,
            format_date(item.published_at),
            item.ransomware_use,
        ),
    )


def upsert_item(
    connection: sqlite3.Connection,
    kind: ItemKind,
    raw_data_id: int,
    item_id: int | None,
) -> int:
    """A new item, or the known one pointed at the raw data of its current version."""
    if item_id is None:
        (new_item_id,) = connection.execute(
            "INSERT INTO item (kind, raw_data_id) VALUES (?, ?) RETURNING id",
            (kind, raw_data_id),
        ).fetchone()
        return int(new_item_id)
    connection.execute(
        "UPDATE item SET raw_data_id = ? WHERE id = ?", (raw_data_id, item_id)
    )
    return item_id


# The kinds that have a table in the base, each with its writer.
WRITER_BY_KIND: dict[str, Callable[[sqlite3.Connection, Item, int], None]] = {
    "paper": write_paper,
    "vulnerability": write_vulnerability,
}


def write_raw_data(
    connection: sqlite3.Connection,
    source_code: str,
    collected_at: datetime,
    raw_file_path: str,
) -> int:
    source_row = connection.execute(
        "SELECT id FROM source WHERE source_code = ?", (source_code,)
    ).fetchone()
    if source_row is None:
        raise UnknownSourceError(f"source_code not in the source table: {source_code}")
    connection.execute(
        "INSERT INTO raw_data (source_id, raw_file_path, stream, collected_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT (raw_file_path) DO NOTHING",
        (
            source_row[0],
            raw_file_path,
            find_stream(raw_file_path),
            format_date(collected_at),
        ),
    )
    (raw_data_id,) = connection.execute(
        "SELECT id FROM raw_data WHERE raw_file_path = ?", (raw_file_path,)
    ).fetchone()
    return int(raw_data_id)


def format_date(moment: datetime | None) -> str | None:
    return (
        None
        if moment is None
        else moment.astimezone(UTC).strftime(DATABASE_DATE_FORMAT)
    )


def write_import_log(
    log_path: Path, rejections: list[Rejection], discards: list[Discard]
) -> None:
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
