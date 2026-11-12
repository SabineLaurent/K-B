"""The reading gives the same results on PostgreSQL as on SQLite, on the same test base
(tests/fixtures/items_database.sql): every filter of read_items, alone and together, each page, the
detail of each item and the trends (criterion of #418)."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from database.connected_readers import open_connected_readers

from k_b.core.config import DATA_API_QUERY_TIMEOUT_SECONDS
from k_b.database.engine import connect_reader
from k_b.database.reading import (
    DetailBounds,
    read_highlights,
    read_item_detail,
    read_items,
    read_trends,
)

pytestmark = pytest.mark.postgresql

# The calls of read_items compared, each by its arguments.
READ_ITEMS_CALLS = [
    {"limit": 100},
    *(
        {"limit": 100, "kinds": [kind]}
        for kind in (
            "paper",
            "vulnerability",
            "release",
            "advisory",
            "newsletter_article",
            "zotero_entry",
            "clip",
        )
    ),
    {"limit": 100, "kinds": ["paper", "clip"]},
    {"limit": 100, "kinds": ["release", "release"]},
    {"limit": 100, "since": datetime(2026, 10, 1, tzinfo=UTC)},
    {
        "limit": 100,
        "since": datetime(2026, 10, 1, 1, tzinfo=timezone(timedelta(hours=2))),
    },
    {"limit": 100, "since": datetime(2026, 10, 1, 8, 15, 0, 1, tzinfo=UTC)},
    *(
        {"limit": 100, "search_text": search_text}
        for search_text in (
            "claude",
            "CLAUDE",
            "ClAuDe",
            "v2%286",
            "v2_1",
            "_",
            "%",
            "\\",
            "new developers",
            "NEW DEVELOPERS",
            "no item holds this",
        )
    ),
    {"limit": 100, "mode": "automated_watch"},
    {"limit": 100, "mode": "selected_library"},
    *({"limit": 5, "offset": offset} for offset in (0, 5, 10, 15, 20)),
    {
        "limit": 2,
        "offset": 1,
        "kinds": ["release", "newsletter_article"],
        "since": datetime(2026, 9, 1, tzinfo=UTC),
        "search_text": "a",
        "mode": "automated_watch",
    },
]
ITEM_IDS = [*range(1, 19), 999]
# Bounds no item of the test base reaches.
BOUNDS = DetailBounds(highlights=100, body_length=125_000)
TREND_WINDOWS = [None, date(2026, 10, 9), date(2026, 10, 10), date(2026, 1, 1)]


def read_everything(location):
    """The result of each reading compared, through the connection of the data API."""
    with (
        open_connected_readers(location, DATA_API_QUERY_TIMEOUT_SECONDS) as readers,
        connect_reader(readers, DATA_API_QUERY_TIMEOUT_SECONDS) as connection,
    ):
        return {
            "items": [read_items(connection, **call) for call in READ_ITEMS_CALLS],
            "details": [
                read_item_detail(connection, item_id, BOUNDS) for item_id in ITEM_IDS
            ],
            "highlights": [
                read_highlights(connection, item_id, BOUNDS.highlights)
                for item_id in (14, 15, 16)
            ],
            "trends": [read_trends(connection, window) for window in TREND_WINDOWS],
        }


def test_read_items_gives_the_same_results_on_postgresql_as_on_sqlite(
    items_database, items_postgresql_base
):
    on_sqlite = read_everything(items_database)

    on_postgresql = read_everything(items_postgresql_base)

    # The calls read something: an empty base would give equal results too.
    assert len(on_sqlite["items"][0].items) == 18
    assert [len(page.items) for page in on_sqlite["items"][1:8]] == [
        2,
        3,
        3,
        3,
        3,
        3,
        1,
    ]
    assert all(detail is not None for detail in on_sqlite["details"][:-1])
    assert on_postgresql == on_sqlite
