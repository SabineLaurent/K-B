"""Read the items database.

The list of the items is one query for the data API, kb search and "what's new"
(docs/specs-api.md, "GET /items"): one branch per kind gives its title, summary, date and URL,
and every filter is a bound parameter.
"""

import json
import sqlite3
from collections.abc import Collection
from datetime import datetime, timedelta
from typing import NamedTuple

from k_b.items import (
    ARXIV_ABSTRACT_PAGE_URL,
    NVD_PAGE_URL,
    ItemKind,
    SearchableMode,
    convert_to_utc,
)

SELECT_RAW_FILE_PATHS = "SELECT raw_file_path FROM raw_data"

# One branch per ItemKind; its date is the one the source gives (docs/specs-api.md, "Date,
# titre et résumé par sorte"). A kind without summary gives NULL: its title alone is searched.
# Raw string: SQLite must receive ESCAPE '\'.
SELECT_ITEMS = r"""
SELECT listed.id, listed.kind, listed.title, listed.source_date, listed.url, listed.withdrawn_at
FROM (
    SELECT item.id, item.kind, item.raw_data_id, publication.title AS title,
        publication.summary AS summary, publication.submitted_at AS source_date,
        :arxiv_page_url || publication.arxiv_id AS url, NULL AS withdrawn_at
    FROM item JOIN publication ON publication.item_id = item.id
    UNION ALL
    SELECT item.id, item.kind, item.raw_data_id, vulnerability.name, vulnerability.description,
        vulnerability.date_added, :nvd_page_url || vulnerability.cve_id,
        vulnerability.withdrawn_at
    FROM item JOIN vulnerability ON vulnerability.item_id = item.id
    UNION ALL
    SELECT item.id, item.kind, item.raw_data_id,
        tracked_repository.repository_name || ' '
            || coalesce(nullif(release.name, ''), release.tag_name),
        release.body, release.published_at, release.url, NULL
    FROM item JOIN release ON release.item_id = item.id
        JOIN tracked_repository ON tracked_repository.id = release.tracked_repository_id
    UNION ALL
    SELECT item.id, item.kind, item.raw_data_id, advisory.summary, NULL, advisory.published_at,
        advisory.url, NULL
    FROM item JOIN advisory ON advisory.item_id = item.id
    UNION ALL
    SELECT item.id, item.kind, item.raw_data_id, newsletter_article.title,
        newsletter_article.summary, newsletter_article.edition_date, newsletter_article.url, NULL
    FROM item JOIN newsletter_article ON newsletter_article.item_id = item.id
    UNION ALL
    SELECT item.id, item.kind, item.raw_data_id, zotero_entry.title, NULL, zotero_entry.saved_at,
        zotero_entry.url, zotero_entry.withdrawn_at
    FROM item JOIN zotero_entry ON zotero_entry.item_id = item.id
) AS listed
JOIN raw_data ON raw_data.id = listed.raw_data_id
JOIN source ON source.id = raw_data.source_id
WHERE (:kinds IS NULL OR listed.kind IN (SELECT value FROM json_each(:kinds)))
    AND (:since IS NULL OR listed.source_date >= :since)
    AND (:pattern IS NULL
        OR listed.title LIKE :pattern ESCAPE '\' OR listed.summary LIKE :pattern ESCAPE '\')
    AND (:mode IS NULL OR source.acquisition_mode = :mode)
ORDER BY listed.source_date DESC, listed.id DESC
LIMIT :limit OFFSET :offset
"""

SELECT_HIGHLIGHTS = """
SELECT zotero_key, text, comment, highlighted_at, revised_at, withdrawn_at
FROM highlight
WHERE item_id = ?
ORDER BY highlighted_at, highlight_id
"""


class ListedItem(NamedTuple):
    id: int
    kind: ItemKind
    title: str
    # The date of since, as the base writes it: YYYY-MM-DDTHH:MM:SSZ.
    source_date: str
    # None for a Zotero entry without URL.
    url: str | None
    # The date K-B saw a catalog row withdrawn: a withdrawn row is listed, not left out.
    withdrawn_at: str | None


class ItemPage(NamedTuple):
    items: list[ListedItem]
    # The offset of the next page; None on the last one.
    next_offset: int | None


class StoredHighlight(NamedTuple):
    zotero_key: str
    text: str | None
    comment: str | None
    highlighted_at: str
    revised_at: str | None
    withdrawn_at: str | None


def read_raw_file_paths(connection: sqlite3.Connection) -> frozenset[str]:
    """The raw files already imported: raw_data is their registry, one row per file (#106)."""
    return frozenset(
        str(raw_file_path)
        for (raw_file_path,) in connection.execute(SELECT_RAW_FILE_PATHS)
    )


def read_items(
    connection: sqlite3.Connection,
    *,
    limit: int,
    offset: int = 0,
    kinds: Collection[ItemKind] = (),
    since: datetime | None = None,
    search_text: str | None = None,
    mode: SearchableMode | None = None,
) -> ItemPage:
    """A page of the items, the newest first; no kind given reads every kind.

    The bounds of the data API (docs/specs-api.md) are its own; this refuses only what SQLite
    would misread: a negative LIMIT reads every row.
    """
    if limit < 1:
        raise ValueError(f"limit below 1: {limit}")
    if offset < 0:
        raise ValueError(f"offset below 0: {offset}")
    # One row more than the page tells whether a next page exists, in the same query.
    rows = connection.execute(
        SELECT_ITEMS,
        {
            "arxiv_page_url": ARXIV_ABSTRACT_PAGE_URL,
            "nvd_page_url": NVD_PAGE_URL,
            "kinds": json.dumps(list(kinds)) if kinds else None,
            "since": None if since is None else format_since(since),
            "pattern": None if search_text is None else to_like_pattern(search_text),
            "mode": mode,
            "limit": limit + 1,
            "offset": offset,
        },
    ).fetchall()
    return ItemPage(
        [ListedItem._make(row) for row in rows[:limit]],
        offset + limit if len(rows) > limit else None,
    )


def format_since(since: datetime) -> str:
    """since in UTC, in the format of the base, rounded up to its second: the dates of the base
    are compared as text, to the second (database/dates.py).

    isoformat, not strftime: strftime leaves the width of the year to the C library, and since
    is given by the caller, the year 1 included.
    """
    if since.tzinfo is None:
        raise ValueError("since has no time zone")
    try:
        since_utc = convert_to_utc(since)
        if since_utc.microsecond:
            since_utc = since_utc.replace(microsecond=0) + timedelta(seconds=1)
    except (ValueError, OverflowError):
        raise ValueError("since out of range once in UTC") from None
    return since_utc.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def to_like_pattern(search_text: str) -> str:
    """A LIKE pattern that finds search_text anywhere, % and _ as written (ESCAPE '\\')."""
    if not search_text:
        raise ValueError("search_text is empty")
    escaped = search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def read_highlights(
    connection: sqlite3.Connection, item_id: int
) -> list[StoredHighlight]:
    """The highlights of a Zotero entry, the withdrawn ones included, by date of creation."""
    return [
        StoredHighlight._make(row)
        for row in connection.execute(SELECT_HIGHLIGHTS, (item_id,))
    ]
