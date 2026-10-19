"""Write a clip: the latest version of a URL is kept, a clip whose content changed is written
again, revised_at dated (decision of Sabine of 2026-10-19)."""

import sqlite3
from typing import NamedTuple

from k_b.database.dates import format_date
from k_b.database.writers import shared_rows
from k_b.database.writers.discard import Discard
from k_b.items import Item

# News feed, as INSERT_ITEM_OF_NEW_RELEASE (release_writer.py). A clip is known by its natural
# key: its URL, without its utm_* parameters.
INSERT_ITEM_OF_NEW_CLIP = """
INSERT INTO item (kind, raw_data_id)
SELECT 'clip', :raw_data_id WHERE NOT EXISTS (SELECT 1 FROM clip WHERE url = :url)
RETURNING id
"""

INSERT_CLIP = """
INSERT INTO clip (item_id, kind, url, title, body, saved_at, published_at)
VALUES (:item_id, 'clip', :url, :title, :body, :saved_at, :published_at)
"""

# The clip of the URL, its content, and whether the file being imported was collected before
# the raw file its item points to. The dates are compared as text (database/dates.py).
SELECT_KNOWN_CLIP = """
SELECT clip.item_id, clip.title, clip.body, clip.saved_at, clip.published_at,
    raw_data.collected_at, :collected_at < raw_data.collected_at
FROM clip
JOIN item ON item.id = clip.item_id
JOIN raw_data ON raw_data.id = item.raw_data_id
WHERE clip.url = :url
"""

UPDATE_CLIP = """
UPDATE clip
SET title = :title, body = :body, saved_at = :saved_at, published_at = :published_at,
    revised_at = :revised_at
WHERE item_id = :item_id
"""


class ClipContent(NamedTuple):
    """What the base keeps of a clip, in the format of the base: a change of it is a new
    version. A property the base does not keep (author, description) is not compared."""

    title: str
    # Required of a clip by the item (REQUIRED_FIELDS_BY_KIND, items.py), typed as the item.
    body: str | None
    saved_at: str | None
    published_at: str | None


def write(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The item and its clip; a clip of a URL already known is written again if it changed."""
    content = ClipContent(
        item.title,
        item.summary,
        format_date(item.saved_at),
        format_date(item.published_at),
    )
    row = connection.execute(
        INSERT_ITEM_OF_NEW_CLIP, {"raw_data_id": raw_data_id, "url": item.url}
    ).fetchone()
    if row is None:
        return write_known_clip(connection, item, raw_data_id, content)
    connection.execute(
        INSERT_CLIP, {"item_id": row[0], "url": item.url} | content._asdict()
    )
    return None


def write_known_clip(
    connection: sqlite3.Connection, item: Item, raw_data_id: int, content: ClipContent
) -> Discard | None:
    """The known clip of the URL takes content, unless it is the same or the file was collected
    before the raw file of the clip. Two files of a URL in one collection: the second in page
    name order writes over the first.

    The item points to the newest raw file of its content, a copy of the same content
    included: a file collected before it is older than the content kept.
    """
    collected_at = format_date(item.collected_at)
    (
        known_item_id,
        known_title,
        known_body,
        known_saved_at,
        known_published_at,
        known_collected_at,
        is_file_before,
    ) = connection.execute(
        SELECT_KNOWN_CLIP, {"url": item.url, "collected_at": collected_at}
    ).fetchone()
    known_content = ClipContent(
        title=known_title,
        body=known_body,
        saved_at=known_saved_at,
        published_at=known_published_at,
    )
    if known_content == content:
        if not is_file_before:
            shared_rows.point_item_at_raw_data(connection, known_item_id, raw_data_id)
        return Discard("already_seen", item, known_collected_at)
    if is_file_before:
        return Discard("no_newer_version", item, known_collected_at)
    connection.execute(
        UPDATE_CLIP,
        content._asdict() | {"item_id": known_item_id, "revised_at": collected_at},
    )
    shared_rows.point_item_at_raw_data(connection, known_item_id, raw_data_id)
    return None
