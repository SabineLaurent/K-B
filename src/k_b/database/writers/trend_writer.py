"""Write the rows of a GH Archive ranking: a news feed applied to the whole window, the first
ranking seen of a window is kept."""

import sqlite3
from collections.abc import Sequence
from datetime import date

from k_b.database.dates import format_day
from k_b.items import TrendRow

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


def write_trends(
    connection: sqlite3.Connection, rows: Sequence[TrendRow], raw_data_id: int
) -> tuple[int, dict[date, str]]:
    """Write the rows of the ranking of the raw data raw_data_id; return how many were
    written, and each window the base left out with the collection of the ranking kept, in the
    format of the base."""
    written_count = 0
    # A dict keeps the windows left out once each, in the order of the rows.
    windows_left_out: dict[date, None] = {}
    for row in rows:
        if write_trend(connection, row, raw_data_id):
            written_count += 1
        else:
            windows_left_out[row.window_end] = None
    return written_count, {
        window_end: read_trend_window_collected_at(connection, window_end)
        for window_end in windows_left_out
    }


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
