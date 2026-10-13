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

A ranking of GH Archive is not made of items: its rows go to the trend table, in the same
transaction, and its rule is a news feed applied to the whole window. A Zotero entry is a state
catalog, as CISA KEV, and so is each of its highlights (decision of 2026-10-13).

Only exact duplicates are found: the same identifier within its source (a replay, collections
that overlap). The same content under another identifier is not found, a written limit without
a content fingerprint: for TLDR, another URL or another edition (decision of 2026-10-12); for
Zotero, another key, though two entries of the same arXiv paper point to the same publication
(decision of 2026-10-13; docs/specs-collecte.md).
"""

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, NamedTuple

from k_b.config import TrackedRepository
from k_b.database.connection import connect_database
from k_b.database.reading import read_raw_file_paths
from k_b.items import Item, ItemKind, TrendRow
from k_b.merge import normalize_item
from k_b.raw_items import (
    RawFile,
    RawReading,
    Rejection,
    TrendFile,
    TrendReading,
    reject,
)
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

# B1 of 2026-10-13: the paper a Zotero entry is, created with its arXiv reference alone when
# arXiv has not given it, as a CVE an advisory cites.
INSERT_CITED_PUBLICATION = """
INSERT INTO publication (arxiv_id) VALUES (?) ON CONFLICT (arxiv_id) DO NOTHING
"""

# State catalog (Zotero), as UPSERT_VULNERABILITY: a known entry takes the version of an extract
# collected after the latest one imported, if its content differs or if it was withdrawn;
# revised_at is then the date of that collection, and withdrawn_at is emptied. An entry only an
# extract older than the latest one brings is absent from the latest one: :withdrawn_at is then
# the collection of the latest one.
UPSERT_ZOTERO_ENTRY = """
INSERT INTO zotero_entry (
    item_id, kind, zotero_key, item_type, title, url, saved_at, publication_id, withdrawn_at
) VALUES (
    :item_id, 'zotero_entry', :zotero_key, :item_type, :title, :url, :saved_at,
    :publication_id, :withdrawn_at
)
ON CONFLICT (zotero_key) DO UPDATE SET
    item_type = excluded.item_type,
    title = excluded.title,
    url = excluded.url,
    saved_at = excluded.saved_at,
    publication_id = excluded.publication_id,
    revised_at = :collected_at,
    withdrawn_at = NULL
WHERE :is_after_latest_catalog
    AND (zotero_entry.withdrawn_at IS NOT NULL
        OR (zotero_entry.item_type, zotero_entry.title, zotero_entry.url,
            zotero_entry.saved_at, zotero_entry.publication_id)
        IS NOT (excluded.item_type, excluded.title, excluded.url, excluded.saved_at,
            excluded.publication_id))
RETURNING id
"""

# State catalog (Zotero), the same rule for each highlight of an entry.
UPSERT_HIGHLIGHT = """
INSERT INTO highlight (zotero_key, text, comment, highlighted_at, item_id, withdrawn_at)
VALUES (:zotero_key, :text, :comment, :highlighted_at, :item_id, :withdrawn_at)
ON CONFLICT (zotero_key) DO UPDATE SET
    text = excluded.text,
    comment = excluded.comment,
    highlighted_at = excluded.highlighted_at,
    item_id = excluded.item_id,
    revised_at = :collected_at,
    withdrawn_at = NULL
WHERE :is_after_latest_catalog
    AND (highlight.withdrawn_at IS NOT NULL
        OR (highlight.text, highlight.comment, highlight.highlighted_at, highlight.item_id)
        IS NOT (excluded.text, excluded.comment, excluded.highlighted_at,
            excluded.item_id))
RETURNING highlight_id
"""

# State catalog (Zotero): an entry or a highlight absent from an extract collected after the
# latest one imported is withdrawn at that collection, never removed; the first absence keeps
# its date.
WITHDRAW_ABSENT_ZOTERO_ENTRIES = """
UPDATE zotero_entry SET withdrawn_at = :collected_at
WHERE withdrawn_at IS NULL
    AND zotero_key NOT IN (SELECT value FROM json_each(:present_keys))
"""

WITHDRAW_ABSENT_HIGHLIGHTS = """
UPDATE highlight SET withdrawn_at = :collected_at
WHERE withdrawn_at IS NULL
    AND zotero_key NOT IN (SELECT value FROM json_each(:present_keys))
"""

# News feed (releases, advisories, TLDR articles): the item is created only if its subtype is
# not known yet, and the first version seen is kept. The subtype needs its item first: no ON
# CONFLICT can come before the item; its UNIQUE constraint stays the safety net.
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

# A TLDR article is known by its natural key: its edition, the day of the edition, its rank.
INSERT_ITEM_OF_NEW_NEWSLETTER_ARTICLE = """
INSERT INTO item (kind, raw_data_id)
SELECT 'newsletter_article', :raw_data_id WHERE NOT EXISTS (
    SELECT 1 FROM newsletter_article
    WHERE edition = :edition AND edition_date = :edition_date AND rank = :rank
)
RETURNING id
"""

SELECT_NEWSLETTER_ARTICLE_ITEM = """
SELECT item_id FROM newsletter_article
WHERE edition = :edition AND edition_date = :edition_date AND rank = :rank
"""

# News feed, by window (GH Archive): the first ranking seen of a window is kept whole. A row is
# written only if no other raw file has brought its window: the rows of the file being written
# share its raw_data_id, and none is left out. The same file read again meets the UNIQUE key.
INSERT_TREND_OF_NEW_WINDOW = """
INSERT INTO trend (
    raw_data_id, window_end, repository_id, repository_name, stars_gained, forks_gained
)
SELECT :raw_data_id, :window_end, :repository_id, :repository_name, :stars_gained,
    :forks_gained
WHERE NOT EXISTS (
    SELECT 1 FROM trend WHERE window_end = :window_end AND raw_data_id <> :raw_data_id
)
ON CONFLICT (window_end, repository_id) DO NOTHING
RETURNING id
"""

# Every row of a window comes from one raw file: any of them gives its collection.
SELECT_TREND_WINDOW_COLLECTED_AT = """
SELECT raw_data.collected_at FROM trend
JOIN raw_data ON raw_data.id = trend.raw_data_id
WHERE trend.window_end = ?
LIMIT 1
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


# publication_id stays empty: the paper an article cites is not looked for yet.
INSERT_NEWSLETTER_ARTICLE = """
INSERT INTO newsletter_article (
    item_id, kind, edition, edition_date, rank, title, summary, url
) VALUES (
    :item_id, 'newsletter_article', :edition, :edition_date, :rank, :title, :summary, :url
)
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


# The rule of a window of a ranking left out: the one of a news feed.
TREND_DISCARD_RULE: DiscardRule = "already_seen"


class Discard(NamedTuple):
    rule: DiscardRule
    item: Item
    # The date of the base the item was compared with, in the format of the base.
    compared_with: str


class TrendDiscard(NamedTuple):
    """A window of a ranking left out: another raw file brought it first."""

    raw_file: RawFile
    window_end: date
    # The collection of the ranking kept, in the format of the base.
    compared_with: str


class ImportSummary(NamedTuple):
    item_count: int
    # The items and the windows of a ranking left out.
    discard_count: int
    rejection_count: int
    # The raw files opened, rankings included.
    read_count: int
    withdrawn_count: int
    # The rows written to the trend table.
    trend_count: int


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
    trend_reading: TrendReading,
    database_path: Path,
    log_path: Path,
    imported_at: datetime,
    tracked_repositories: Sequence[TrackedRepository],
) -> ImportSummary:
    """Write the tracked repositories, each file read with its items or its ranking into the
    base, then the log of what was left out, all in one transaction.

    The files of items and the rankings are written in one sequence, in collection order: a
    base rebuilt registers them in the order the imports did.

    The log is written before the commit: a file registered is not read again, its log must
    not be lost. A commit that fails, or an interruption, removes the log written.
    """
    check_database_exists(database_path)
    rejections = [*reading.rejections, *trend_reading.rejections]
    written_count = 0
    withdrawn_count = 0
    trend_count = 0
    discards = []
    trend_discards = []
    connection = connect_database(database_path)
    try:
        try:
            write_tracked_repositories(connection, tracked_repositories)
            for file_read in list_files_in_collection_order(reading, trend_reading):
                if isinstance(file_read, TrendFile):
                    written, left_out = write_trend_file(connection, file_read)
                    trend_count += written
                    trend_discards.extend(left_out)
                    continue
                raw_file = file_read
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
                ) + withdraw_absent_zotero_rows(connection, raw_file, raw_data_id)
            # Checked once the base holds the write lock: two imports of the same second
            # cannot both find no log.
            check_log_absent(log_path)
            try:
                write_import_log(
                    log_path, imported_at, rejections, discards, trend_discards
                )
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
        len(discards) + len(trend_discards),
        len(rejections),
        reading.read_count + trend_reading.read_count,
        withdrawn_count,
        trend_count,
    )


def list_files_in_collection_order(
    reading: RawReading, trend_reading: TrendReading
) -> list[RawFile | TrendFile]:
    """The files of items and the rankings, oldest collection first; at the same collection,
    the files of items first, in their reading order (the sort is stable)."""

    def read_collected_at(file_read: RawFile | TrendFile) -> datetime:
        if isinstance(file_read, TrendFile):
            return file_read.raw_file.collected_at
        return file_read.collected_at

    return sorted([*reading.files, *trend_reading.files], key=read_collected_at)


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


def write_newsletter_article(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The TLDR item and its article, unless the article is known: the first seen is kept."""
    natural_key = {
        "edition": item.edition,
        "edition_date": format_date(item.published_at),
        "rank": item.rank,
    }
    row = connection.execute(
        INSERT_ITEM_OF_NEW_NEWSLETTER_ARTICLE,
        {"raw_data_id": raw_data_id} | natural_key,
    ).fetchone()
    if row is None:
        (known_item_id,) = connection.execute(
            SELECT_NEWSLETTER_ARTICLE_ITEM, natural_key
        ).fetchone()
        return Discard(
            "already_seen", item, read_item_collected_at(connection, known_item_id)
        )
    connection.execute(
        INSERT_NEWSLETTER_ARTICLE,
        {
            "item_id": row[0],
            "title": item.title,
            "summary": item.summary,
            "url": item.url,
        }
        | natural_key,
    )
    return None


def write_zotero_entry(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The Zotero item, its entry and its highlights, found by their Zotero keys.

    The entry counts as written if its row or one of its highlights was: a highlight changed
    is a new version of the entry, whose item then points to this raw data.
    """
    row = connection.execute(
        "SELECT item_id FROM zotero_entry WHERE zotero_key = ?", (item.source_item_id,)
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
        insert_item(connection, "zotero_entry", raw_data_id)
        if known_item_id is None
        else known_item_id
    )
    catalog = {
        "collected_at": format_date(item.collected_at),
        "is_after_latest_catalog": is_after_latest_catalog,
        # Without a latest catalog, is_after_latest_catalog is NULL: nothing to compare.
        "withdrawn_at": None
        if is_after_latest_catalog or latest_collected_at is None
        else latest_collected_at,
    }
    entry_written = connection.execute(
        UPSERT_ZOTERO_ENTRY,
        {
            "item_id": item_id,
            "zotero_key": item.source_item_id,
            "item_type": item.item_type,
            "title": item.title,
            "url": item.url,
            "saved_at": format_date(item.saved_at),
            "publication_id": write_cited_publication(connection, item.arxiv_id),
        }
        | catalog,
    ).fetchone()
    # A list, not a generator: every highlight is written, not only up to the first written.
    highlights_written = [
        connection.execute(
            UPSERT_HIGHLIGHT,
            {
                "zotero_key": highlight.zotero_key,
                "text": highlight.text,
                "comment": highlight.comment,
                "highlighted_at": format_date(highlight.highlighted_at),
                "item_id": item_id,
            }
            | catalog,
        ).fetchone()
        for highlight in item.highlights
    ]
    if entry_written is None and not any(highlights_written):
        # The base wrote nothing; the rule names which of its two conditions failed.
        if is_after_latest_catalog:
            return Discard(
                "unchanged", item, read_item_collected_at(connection, item_id)
            )
        return Discard("no_newer_version", item, latest_collected_at)
    # An extract imported late writes only what it alone brings, withdrawn: not a version.
    if known_item_id is not None and is_after_latest_catalog:
        point_item_at_raw_data(connection, known_item_id, raw_data_id)
    return None


def write_cited_publication(
    connection: sqlite3.Connection, arxiv_id: str | None
) -> int | None:
    """The publication of arxiv_id, created without its arXiv columns if absent."""
    if arxiv_id is None:
        return None
    connection.execute(INSERT_CITED_PUBLICATION, (arxiv_id,))
    (publication_id,) = connection.execute(
        "SELECT id FROM publication WHERE arxiv_id = ?", (arxiv_id,)
    ).fetchone()
    return int(publication_id)


def write_trend_file(
    connection: sqlite3.Connection, trend_file: TrendFile
) -> tuple[int, list[TrendDiscard]]:
    """Register the ranking and write its rows; return how many were written, and each window
    the base left out."""
    raw_data_id = write_raw_data(connection, trend_file.raw_file)
    written_count = 0
    # A dict keeps the windows left out once each, in the order of the rows.
    windows_left_out: dict[date, None] = {}
    for row in trend_file.rows:
        if write_trend(connection, row, raw_data_id):
            written_count += 1
        else:
            windows_left_out[row.window_end] = None
    discards = [
        TrendDiscard(
            trend_file.raw_file,
            window_end,
            read_trend_window_collected_at(connection, window_end),
        )
        for window_end in windows_left_out
    ]
    return written_count, discards


def write_trend(
    connection: sqlite3.Connection, row: TrendRow, raw_data_id: int
) -> bool:
    """Write the row of the raw data raw_data_id, unless another raw file brought its window:
    the first ranking seen is kept. Return whether the base wrote it."""
    written = connection.execute(
        INSERT_TREND_OF_NEW_WINDOW,
        {
            "raw_data_id": raw_data_id,
            "window_end": format_day(row.window_end),
            "repository_id": row.repository_id,
            "repository_name": row.repository_name,
            "stars_gained": row.stars_gained,
            "forks_gained": row.forks_gained,
        },
    ).fetchone()
    return written is not None


def read_trend_window_collected_at(
    connection: sqlite3.Connection, window_end: date
) -> str:
    (collected_at,) = connection.execute(
        SELECT_TREND_WINDOW_COLLECTED_AT, (format_day(window_end),)
    ).fetchone()
    return str(collected_at)


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
    if not is_after_latest_catalog(connection, raw_file, raw_data_id):
        return 0
    return connection.execute(
        WITHDRAW_ABSENT_VULNERABILITIES,
        {
            "collected_at": format_date(raw_file.collected_at),
            "present_cve_ids": json.dumps(present_cve_ids),
        },
    ).rowcount


def withdraw_absent_zotero_rows(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> int:
    """Withdraw the entries and the highlights an extract collected after the latest one
    imported no longer lists; return how many.

    The same conditions as for a catalog of CISA KEV: an extract with a rejected entry, or
    without entry, withdraws nothing. The highlights are compared with every highlight of the
    extract: the last one of the library deleted in Zotero is withdrawn too.
    """
    entries = [item for item in raw_file.items if item.kind == "zotero_entry"]
    if not entries or raw_file.rejection_count:
        return 0
    if not is_after_latest_catalog(connection, raw_file, raw_data_id):
        return 0
    collected_at = format_date(raw_file.collected_at)
    entry_keys = [entry.source_item_id for entry in entries]
    highlight_keys = [
        highlight.zotero_key for entry in entries for highlight in entry.highlights
    ]
    withdrawn_entries = connection.execute(
        WITHDRAW_ABSENT_ZOTERO_ENTRIES,
        {"collected_at": collected_at, "present_keys": json.dumps(entry_keys)},
    ).rowcount
    withdrawn_highlights = connection.execute(
        WITHDRAW_ABSENT_HIGHLIGHTS,
        {"collected_at": collected_at, "present_keys": json.dumps(highlight_keys)},
    ).rowcount
    return withdrawn_entries + withdrawn_highlights


def is_after_latest_catalog(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> bool:
    """Whether raw_file was collected after the latest catalog of its source imported."""
    _, is_after = connection.execute(
        SELECT_LATEST_CATALOG,
        {
            "source_code": raw_file.source_code,
            "raw_data_id": raw_data_id,
            # No item: only the other files of the source are compared.
            "item_id": None,
            "collected_at": format_date(raw_file.collected_at),
        },
    ).fetchone()
    return bool(is_after)


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
    "newsletter_article": write_newsletter_article,
    "zotero_entry": write_zotero_entry,
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


def format_day(day: date) -> str:
    """A day is written at midnight UTC (docs/stockage.md), in the format of the base.

    isoformat always writes the year on 4 digits; strftime leaves it to the C library.
    """
    return f"{day.isoformat()}T00:00:00Z"


def check_log_absent(log_path: Path) -> None:
    """The log of an import is never rewritten: one already at log_path stops the import."""
    if log_path.exists():
        raise ImportLogExistsError(f"{log_path} already exists")


def write_import_log(
    log_path: Path,
    imported_at: datetime,
    rejections: list[Rejection],
    discards: list[Discard],
    trend_discards: list[TrendDiscard],
) -> None:
    """One JSON line per rejection, then per item left out, then per window of a ranking left
    out, each dated by its import.

    A window is named by its last day, in the field that names an item: one form of line. No
    repository is named: its name holds the login of its owner.
    """
    logged_at = format_date(imported_at)
    lines = (
        [
            {
                "imported_at": logged_at,
                "kind": "rejection",
                "raw_file_path": rejection.raw_file_path,
                "reason": rejection.reason,
            }
            for rejection in rejections
        ]
        + [
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
        + [
            {
                "imported_at": logged_at,
                "kind": "discard",
                "rule": TREND_DISCARD_RULE,
                "source_code": discard.raw_file.source_code,
                "source_item_id": discard.window_end.isoformat(),
                "raw_file_path": discard.raw_file.raw_file_path,
                COMPARED_FIELD_BY_RULE[TREND_DISCARD_RULE]: discard.compared_with,
            }
            for discard in trend_discards
        ]
    )
    write_file_atomically(
        log_path,
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines).encode(),
    )
