"""Write a clip: a news feed, the first version seen of a URL is kept (decision of Sabine of
2026-10-17: the clips are not changed once kept)."""

import sqlite3

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

SELECT_CLIP_ITEM = "SELECT item_id FROM clip WHERE url = :url"

INSERT_CLIP = """
INSERT INTO clip (item_id, kind, url, title, body, saved_at, published_at)
VALUES (:item_id, 'clip', :url, :title, :body, :saved_at, :published_at)
"""


def write(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """The item and its clip, unless a clip of the same URL is known: the first seen is kept."""
    row = connection.execute(
        INSERT_ITEM_OF_NEW_CLIP, {"raw_data_id": raw_data_id, "url": item.url}
    ).fetchone()
    if row is None:
        (known_item_id,) = connection.execute(
            SELECT_CLIP_ITEM, {"url": item.url}
        ).fetchone()
        return Discard(
            "already_seen",
            item,
            shared_rows.read_item_collected_at(connection, known_item_id),
        )
    connection.execute(
        INSERT_CLIP,
        {
            "item_id": row[0],
            "url": item.url,
            "title": item.title,
            "body": item.summary,
            "saved_at": format_date(item.saved_at),
            "published_at": format_date(item.published_at),
        },
    )
    return None
