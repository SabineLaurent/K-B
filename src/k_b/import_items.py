"""Import the raw files not imported yet into the items database (docs/specs-collecte.md,
step 4).

The registry of the files already imported is raw_data, read before the raw. The files read,
their items and the log of the import are then written in one transaction: an error writes
nothing in the base, and leaves no log. A file registered is not read again, except by a
rebuild of the base.

The base removes the duplicates. The writer of each kind holds, in its SQL, the rule of the
nature of its source: a news feed keeps the first version seen; a state catalog keeps the
version of its latest collection; a feed with revisions keeps the newest revision. An item left
out is returned with its rule and the date it was compared with, then written to the log. Run
again on the same raw, the import gives the same base.

Only exact duplicates are found: the same identifier within its source (a replay, collections
that overlap). The same content under another identifier (another URL, another Zotero key) is
left to #57 and #138.
"""

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NamedTuple

from k_b.config import TrackedRepository
from k_b.database.connection import connect_database
from k_b.database.reading import read_raw_file_paths
from k_b.items import Item, ItemKind
from k_b.merge import normalize_item
from k_b.raw_items import RawFile, RawReading, Rejection, reject
from k_b.raw_store import find_stream, write_file_atomically

# The date format the CHECK constraints of schema.sql accept.
DATABASE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The dates of the base are compared as text: the format of its CHECK constraints keeps the
# order of the text the order of time.

# Feed with revisions (arXiv): a paper seen again rewrites its arXiv columns, under the same
# item, only with a newer revision. A paper cited before arXiv gave it takes its first version.
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
WHERE publication.item_id IS NULL OR excluded.revised_at > publication.revised_at
RETURNING id
"""

# State catalog: the collection of the latest catalog of the source already imported, and
# whether the file being imported was collected after it. That file is left out, unless it
# brought the version in the base: a replay, which the registry prevents since #106, kept for
# a base of before it, or for two imports at once.
SELECT_LATEST_CATALOG = """
SELECT max(raw_data.collected_at), :collected_at > max(raw_data.collected_at) FROM raw_data
JOIN source ON source.id = raw_data.source_id
WHERE source.source_code = :source_code
    AND (raw_data.id <> :raw_data_id
        OR raw_data.id = (SELECT raw_data_id FROM item WHERE id = :item_id))
"""

# State catalog (CISA KEV): a known row takes the version of a catalog collected after the
# latest one imported, if its content differs or if it was withdrawn; revised_at is then the
# date of that collection, and withdrawn_at is emptied. A CVE an advisory created takes its
# first KEV row: not a revision. A CVE only a catalog older than the latest one brings is
# absent from the latest one: :withdrawn_at is then the collection of the latest one.
UPSERT_VULNERABILITY = """
INSERT INTO vulnerability (
    cve_id, item_id, name, description, vendor, product, date_added, ransomware_use,
    withdrawn_at
) VALUES (
    :cve_id, :item_id, :name, :description, :vendor, :product, :date_added, :ransomware_use,
    :withdrawn_at
)
ON CONFLICT (cve_id) DO UPDATE SET
    item_id = excluded.item_id,
    name = excluded.name,
    description = excluded.description,
    vendor = excluded.vendor,
    product = excluded.product,
    date_added = excluded.date_added,
    ransomware_use = excluded.ransomware_use,
    revised_at = iif(vulnerability.item_id IS NULL, NULL, :collected_at),
    withdrawn_at = excluded.withdrawn_at
WHERE vulnerability.item_id IS NULL
    OR (:is_after_latest_catalog
        AND (vulnerability.withdrawn_at IS NOT NULL
            OR (vulnerability.name, vulnerability.description, vulnerability.vendor,
                vulnerability.product, vulnerability.date_added,
                vulnerability.ransomware_use)
            IS NOT (excluded.name, excluded.description, excluded.vendor,
                excluded.product, excluded.date_added, excluded.ransomware_use)))
RETURNING id
"""

# State catalog (CISA KEV): a CVE of a KEV item absent from a catalog collected after the
# latest one imported is withdrawn at that collection; the first absence keeps its date.
WITHDRAW_ABSENT_VULNERABILITIES = """
UPDATE vulnerability SET withdrawn_at = :collected_at
WHERE item_id IS NOT NULL
    AND withdrawn_at IS NULL
    AND cve_id NOT IN (SELECT value FROM json_each(:present_cve_ids))
"""

# News feed (releases, advisories): the item is created only if its subtype is not known yet,
# and the first version seen is kept. The subtype needs its item first: no ON CONFLICT can come
# before the item; its UNIQUE constraint stays the safety net.
INSERT_ITEM_OF_NEW_RELEASE = """
INSERT INTO item (kind, raw_data_id)
SELECT 'release', ? WHERE NOT EXISTS (SELECT 1 FROM release WHERE release_id = ?)
RETURNING id
"""

INSERT_ITEM_OF_NEW_ADVISORY = """
INSERT INTO item (kind, raw_data_id)
SELECT 'advisory', ? WHERE NOT EXISTS (SELECT 1 FROM advisory WHERE ghsa_id = ?)
RETURNING id
"""

SELECT_ITEM_COLLECTED_AT = """
SELECT raw_data.collected_at FROM item
JOIN raw_data ON raw_data.id = item.raw_data_id
WHERE item.id = ?
"""


# The list of the code is the source of truth: a repository seen again takes its values.
UPSERT_TRACKED_REPOSITORY = """
INSERT INTO tracked_repository (repository_name, ecosystem, packages) VALUES (?, ?, ?)
ON CONFLICT (repository_name) DO UPDATE SET
    repository_name = excluded.repository_name,
    ecosystem = excluded.ecosystem,
    packages = excluded.packages
"""

INSERT_RELEASE = """
INSERT INTO release (
    item_id, kind, tracked_repository_id, release_id, tag_name, name, body, published_at, url
) VALUES (?, 'release', ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_ADVISORY = """
INSERT INTO advisory (
    item_id, kind, ghsa_id, vulnerability_id, summary, published_at, url, packages
) VALUES (?, 'advisory', ?, ?, ?, ?, ?, ?)
"""


class MissingDatabaseError(FileNotFoundError):
    pass


class ImportLogExistsError(FileExistsError):
    """The log of this second is already written: the log of an import is never rewritten."""


class UnknownSourceError(LookupError):
    """An item's source_code has no row in the source table of the base."""


class KindWithoutTableError(LookupError):
    """An item's kind has no table in the base yet: the import refuses it."""


# Why an item was left out, as the base observed it.
DiscardRule = Literal[
    "already_seen", "unchanged", "no_newer_version", "revision_not_newer"
]

# The date each rule compared the item with, named by where that date comes from.
COMPARED_FIELD_BY_RULE: dict[DiscardRule, str] = {
    # The collection of the version kept.
    "already_seen": "compared_with_collected_at",
    # The collection of the version kept, the only one compared with the content.
    "unchanged": "compared_with_collected_at",
    # The collection of the latest catalog of the source already imported.
    "no_newer_version": "compared_with_collected_at",
    # The arXiv revision of the version kept.
    "revision_not_newer": "compared_with_revised_at",
}


class Discard(NamedTuple):
    rule: DiscardRule
    item: Item
    # The date of the base the item was compared with, in the format of the base.
    compared_with: str


class ImportSummary(NamedTuple):
    item_count: int
    discard_count: int
    rejection_count: int
    read_count: int
    withdrawn_count: int


def check_database_exists(database_path: Path) -> None:
    """Connecting to a missing file would create an empty base."""
    if not database_path.is_file():
        raise MissingDatabaseError(f"{database_path} does not exist")


def read_imported_paths(database_path: Path) -> frozenset[str]:
    """The raw files already imported, from the registry of the base."""
    check_database_exists(database_path)
    connection = connect_database(database_path)
    try:
        return read_raw_file_paths(connection)
    finally:
        connection.close()


def import_items(
    reading: RawReading,
    database_path: Path,
    log_path: Path,
    imported_at: datetime,
    tracked_repositories: Sequence[TrackedRepository],
) -> ImportSummary:
    """Write the tracked repositories, each file read and its items into the base, then the
    log of what was left out, all in one transaction.

    The log is written before the commit: a file registered is not read again, its log must
    not be lost. A commit that fails, or an interruption, removes the log written.
    """
    check_database_exists(database_path)
    rejections = list(reading.rejections)
    written_count = 0
    withdrawn_count = 0
    discards = []
    connection = connect_database(database_path)
    try:
        try:
            write_tracked_repositories(connection, tracked_repositories)
            for raw_file in reading.files:
                items, untracked = reject_untracked_releases(
                    raw_file.items, tracked_repositories
                )
                rejections.extend(untracked)
                raw_data_id = write_raw_data(connection, raw_file)
                for item in map(normalize_item, items):
                    discard = write_item(connection, item, raw_data_id)
                    if discard is None:
                        written_count += 1
                    else:
                        discards.append(discard)
                withdrawn_count += withdraw_absent_vulnerabilities(
                    connection, raw_file, raw_data_id
                )
            # Checked once the base holds the write lock: two imports of the same second
            # cannot both find no log.
            check_log_absent(log_path)
            try:
                write_import_log(log_path, imported_at, rejections, discards)
                connection.commit()
            except BaseException:
                # The log at log_path can only be this import's: it was absent above.
                log_path.unlink(missing_ok=True)
                raise
        except BaseException:
            # BaseException: Ctrl-C must not leave half an import either.
            connection.rollback()
            raise
    finally:
        connection.close()
    return ImportSummary(
        written_count,
        len(discards),
        len(rejections),
        reading.read_count,
        withdrawn_count,
    )


def reject_untracked_releases(
    items: list[Item], tracked_repositories: Sequence[TrackedRepository]
) -> tuple[list[Item], list[Rejection]]:
    """The items without the releases of a repository out of the list, each one rejected.

    The import goes on, as for an entry refused when read. Their file is registered: only a
    rebuild of the base reads them again.
    """
    tracked_names = {repository.name.lower() for repository in tracked_repositories}
    kept = []
    rejections = []
    for item in items:
        if (
            # A release always has its repository (items.py): str() only satisfies the typing.
            item.kind == "release"
            and str(item.repository_name).lower() not in tracked_names
        ):
            rejections.append(
                reject(
                    item.raw_file_path,
                    f"repository not in the tracked list: {item.repository_name}",
                )
            )
        else:
            kept.append(item)
    return kept, rejections


def write_tracked_repositories(
    connection: sqlite3.Connection, tracked_repositories: Sequence[TrackedRepository]
) -> None:
    connection.executemany(
        UPSERT_TRACKED_REPOSITORY,
        [
            (
                repository.name,
                repository.ecosystem,
                json.dumps(repository.packages, ensure_ascii=False),
            )
            for repository in tracked_repositories
        ],
    )


def write_item(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """Write the item of the raw data raw_data_id, or return why the base left it out."""
    write_kind = WRITER_BY_KIND.get(item.kind)
    if write_kind is None:
        raise KindWithoutTableError(f"kind without a table in the base: {item.kind}")
    return write_kind(connection, item, raw_data_id)


def write_paper(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The arXiv item and its publication, found by its arXiv identifier."""
    row = connection.execute(
        "SELECT item_id, revised_at FROM publication WHERE arxiv_id = ?",
        (item.source_item_id,),
    ).fetchone()
    known_item_id, known_revised_at = row if row else (None, None)
    item_id = (
        insert_item(connection, "paper", raw_data_id)
        if known_item_id is None
        else known_item_id
    )
    written = connection.execute(
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
    ).fetchone()
    if written is None:
        # Left out only for a known arXiv item, whose revised_at the CHECK fills.
        return Discard("revision_not_newer", item, str(known_revised_at))
    if known_item_id is not None:
        point_item_at_raw_data(connection, known_item_id, raw_data_id)
    return None


def write_vulnerability(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The CISA KEV item and its vulnerability, found by its CVE."""
    row = connection.execute(
        "SELECT item_id FROM vulnerability WHERE cve_id = ?", (item.cve,)
    ).fetchone()
    known_item_id = row[0] if row else None
    latest_collected_at, is_after_latest_catalog = connection.execute(
        SELECT_LATEST_CATALOG,
        {
            "source_code": item.source_code,
            "raw_data_id": raw_data_id,
            "item_id": known_item_id,
            "collected_at": format_date(item.collected_at),
        },
    ).fetchone()
    item_id = (
        insert_item(connection, "vulnerability", raw_data_id)
        if known_item_id is None
        else known_item_id
    )
    written = connection.execute(
        UPSERT_VULNERABILITY,
        {
            "cve_id": item.cve,
            "item_id": item_id,
            "name": item.title,
            "description": item.summary,
            "vendor": item.vendor,
            "product": item.product,
            "date_added": format_date(item.published_at),
            "ransomware_use": item.ransomware_use,
            "collected_at": format_date(item.collected_at),
            "is_after_latest_catalog": is_after_latest_catalog,
            # Without a latest catalog, is_after_latest_catalog is NULL: nothing to compare.
            "withdrawn_at": None
            if is_after_latest_catalog or latest_collected_at is None
            else latest_collected_at,
        },
    ).fetchone()
    if written is None:
        # The base wrote nothing; the rule names which of its two conditions failed.
        if is_after_latest_catalog:
            return Discard(
                "unchanged", item, read_item_collected_at(connection, item_id)
            )
        return Discard("no_newer_version", item, latest_collected_at)
    if known_item_id is not None:
        point_item_at_raw_data(connection, known_item_id, raw_data_id)
    return None


def write_release(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The GitHub item and its release, unless the release is known: the first seen is kept."""
    release_id = int(item.source_item_id)
    row = connection.execute(
        INSERT_ITEM_OF_NEW_RELEASE, (raw_data_id, release_id)
    ).fetchone()
    if row is None:
        (known_item_id,) = connection.execute(
            "SELECT item_id FROM release WHERE release_id = ?", (release_id,)
        ).fetchone()
        return Discard(
            "already_seen", item, read_item_collected_at(connection, known_item_id)
        )
    # The releases of a repository out of the list were rejected before the import.
    (tracked_repository_id,) = connection.execute(
        "SELECT id FROM tracked_repository WHERE repository_name = ?",
        (item.repository_name,),
    ).fetchone()
    connection.execute(
        INSERT_RELEASE,
        (
            row[0],
            tracked_repository_id,
            release_id,
            item.tag_name,
            item.release_name,
            item.summary,
            format_date(item.published_at),
            item.url,
        ),
    )
    return None


def write_advisory(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The GitHub item and its advisory, unless the advisory is known: the first seen is kept.

    The CVE it cites is created without its KEV columns if no source has cited it yet.
    """
    row = connection.execute(
        INSERT_ITEM_OF_NEW_ADVISORY, (raw_data_id, item.source_item_id)
    ).fetchone()
    if row is None:
        (known_item_id,) = connection.execute(
            "SELECT item_id FROM advisory WHERE ghsa_id = ?", (item.source_item_id,)
        ).fetchone()
        return Discard(
            "already_seen", item, read_item_collected_at(connection, known_item_id)
        )
    vulnerability_id = None
    if item.cve is not None:
        connection.execute(
            "INSERT INTO vulnerability (cve_id) VALUES (?) ON CONFLICT (cve_id) DO NOTHING",
            (item.cve,),
        )
        (vulnerability_id,) = connection.execute(
            "SELECT id FROM vulnerability WHERE cve_id = ?", (item.cve,)
        ).fetchone()
    connection.execute(
        INSERT_ADVISORY,
        (
            row[0],
            item.source_item_id,
            vulnerability_id,
            item.title,
            format_date(item.published_at),
            item.url,
            json.dumps(list(item.package_names), ensure_ascii=False),
        ),
    )
    return None


def withdraw_absent_vulnerabilities(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> int:
    """Withdraw the CVE a catalog collected after the latest one imported no longer lists;
    return how many.

    Only a file of vulnerabilities, all of its entries read: a rejected row is in the catalog,
    not absent from it. A CVE written or left out is in the catalog alike. The item withdrawn
    keeps the raw data of its version: an absence is not a version.
    """
    present_cve_ids = [
        item.cve
        for item in raw_file.items
        if item.kind == "vulnerability" and item.cve is not None
    ]
    if not present_cve_ids or raw_file.rejection_count:
        return 0
    _, is_after_latest_catalog = connection.execute(
        SELECT_LATEST_CATALOG,
        {
            "source_code": raw_file.source_code,
            "raw_data_id": raw_data_id,
            # No item: only the other files of the source are compared.
            "item_id": None,
            "collected_at": format_date(raw_file.collected_at),
        },
    ).fetchone()
    if not is_after_latest_catalog:
        return 0
    return connection.execute(
        WITHDRAW_ABSENT_VULNERABILITIES,
        {
            "collected_at": format_date(raw_file.collected_at),
            "present_cve_ids": json.dumps(present_cve_ids),
        },
    ).rowcount


def insert_item(
    connection: sqlite3.Connection, kind: ItemKind, raw_data_id: int
) -> int:
    (item_id,) = connection.execute(
        "INSERT INTO item (kind, raw_data_id) VALUES (?, ?) RETURNING id",
        (kind, raw_data_id),
    ).fetchone()
    return int(item_id)


def point_item_at_raw_data(
    connection: sqlite3.Connection, item_id: int, raw_data_id: int
) -> None:
    """A known item now points to the raw data of its current version."""
    connection.execute(
        "UPDATE item SET raw_data_id = ? WHERE id = ?", (raw_data_id, item_id)
    )


def read_item_collected_at(connection: sqlite3.Connection, item_id: int) -> str:
    (collected_at,) = connection.execute(
        SELECT_ITEM_COLLECTED_AT, (item_id,)
    ).fetchone()
    return str(collected_at)


# The kinds that have a table in the base, each with its writer.
WRITER_BY_KIND: dict[str, Callable[[sqlite3.Connection, Item, int], Discard | None]] = {
    "paper": write_paper,
    "vulnerability": write_vulnerability,
    "release": write_release,
    "advisory": write_advisory,
}


def write_raw_data(connection: sqlite3.Connection, raw_file: RawFile) -> int:
    """Register the file read, even without item: the next import does not read it again."""
    source_row = connection.execute(
        "SELECT id FROM source WHERE source_code = ?", (raw_file.source_code,)
    ).fetchone()
    if source_row is None:
        raise UnknownSourceError(
            f"source_code not in the source table: {raw_file.source_code}"
        )
    connection.execute(
        "INSERT INTO raw_data (source_id, raw_file_path, stream, collected_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT (raw_file_path) DO NOTHING",
        (
            source_row[0],
            raw_file.raw_file_path,
            find_stream(raw_file.raw_file_path),
            format_date(raw_file.collected_at),
        ),
    )
    (raw_data_id,) = connection.execute(
        "SELECT id FROM raw_data WHERE raw_file_path = ?", (raw_file.raw_file_path,)
    ).fetchone()
    return int(raw_data_id)


def format_date(moment: datetime | None) -> str | None:
    return (
        None
        if moment is None
        else moment.astimezone(UTC).strftime(DATABASE_DATE_FORMAT)
    )


def check_log_absent(log_path: Path) -> None:
    """The log of an import is never rewritten: one already at log_path stops the import."""
    if log_path.exists():
        raise ImportLogExistsError(f"{log_path} already exists")


def write_import_log(
    log_path: Path,
    imported_at: datetime,
    rejections: list[Rejection],
    discards: list[Discard],
) -> None:
    """One JSON line per rejection, then per item left out, each dated by its import."""
    logged_at = format_date(imported_at)
    lines = [
        {
            "imported_at": logged_at,
            "kind": "rejection",
            "raw_file_path": rejection.raw_file_path,
            "reason": rejection.reason,
        }
        for rejection in rejections
    ] + [
        {
            "imported_at": logged_at,
            "kind": "discard",
            "rule": discard.rule,
            "source_code": discard.item.source_code,
            "source_item_id": discard.item.source_item_id,
            "raw_file_path": discard.item.raw_file_path,
            COMPARED_FIELD_BY_RULE[discard.rule]: discard.compared_with,
        }
        for discard in discards
    ]
    write_file_atomically(
        log_path,
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines).encode(),
    )
