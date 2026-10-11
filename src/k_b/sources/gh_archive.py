"""The GH Archive source: the GitHub repositories that gain the most stars and forks (E).

GH Archive records every public GitHub event, one table a day, as a public BigQuery dataset. The
source counts, for each window of 3 complete UTC days, the stars (WatchEvent) and forks
(ForkEvent) each repository gains, in one query that reads each day once. What the query returns,
with the windows it covers, is the raw result: a ranking, refused whole when one row is invalid.

The query runs in a BigQuery sandbox without billing (docs/bigquery.md): a dry run first, then
the query capped by maximum_bytes_billed. The service account key is found by the client through
GOOGLE_APPLICATION_CREDENTIALS; the source never opens it.
"""

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from google.cloud import bigquery
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from k_b.items import RepositoryName
from k_b.raw_store import AUTOMATED_WATCH_DIR_NAME

logger = logging.getLogger(__name__)

# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "gh_archive"

WINDOW_DAYS = 3
# The 30 first by stars and the 30 first by forks, together (decision of 2026-10-08).
TOP_SIZE = 30
MAX_ROWS_PER_WINDOW = 2 * TOP_SIZE
# Two weeks of missed collections: a repository that rose earlier adds little to the watch
# (decision of 2026-10-11). Beyond, the most recent windows are kept.
MAX_CATCH_UP_WINDOWS = 15
# The cap grows with the windows, up to a bound (decision of 2026-10-11). Measured on 2026-10-11
# (dry run): 1 window 133.8 MB, 15 windows 1.58 GB. A daily collection that reads 20 times its
# usual volume is stopped by the dry run.
MAX_BYTES_PER_WINDOW = 200_000_000
MAX_BYTES_BILLED = 2_000_000_000
QUERY_TIMEOUT_SECONDS = 300
# An identifier BigQuery gives as INT64.
MAX_INT64 = 2**63 - 1
# How much of an invalid value goes into the error.
MAX_QUOTED_VALUE_LENGTH = 100
# Holds the owner's login when the owner is a person: never quoted, only its length.
FIELDS_NEVER_QUOTED = frozenset({"repository_name"})

TABLE_PREFIX = "githubarchive.day."
# With the wildcard day.20*, _TABLE_SUFFIX is what follows "20": YYMMDD (261008 for 2026-10-08).
TABLE_SUFFIX_FORMAT = "%y%m%d"

# Reads 4 columns of the events: never actor, payload or org. An event without repo.id or
# repo.name is left out: on 2026-10-10, 14 ForkEvent had neither (seen on 2026-10-11). A
# WatchEvent is a star given (GH Archive does not record a star removed): events are counted,
# not people. Ties are broken by repository_id, and the last name seen by the name, so that the
# same tables give the same result. The table is written in the query (a table cannot be a
# parameter): a test keeps it equal to TABLE_PREFIX.
TRENDS_QUERY = """
WITH events AS (
  SELECT repo.id AS repository_id, repo.name AS repository_name, type, created_at,
         PARSE_DATE('%Y%m%d', CONCAT('20', _TABLE_SUFFIX)) AS event_day
  FROM `githubarchive.day.20*`
  WHERE _TABLE_SUFFIX BETWEEN @first_suffix AND @last_suffix
    AND type IN ('WatchEvent', 'ForkEvent')
    AND repo.id IS NOT NULL
    AND repo.name IS NOT NULL
),
counts AS (
  SELECT window_end, repository_id,
    ARRAY_AGG(repository_name ORDER BY created_at DESC, repository_name DESC LIMIT 1)[OFFSET(0)]
      AS repository_name,
    COUNTIF(type = 'WatchEvent') AS stars_gained,
    COUNTIF(type = 'ForkEvent') AS forks_gained
  FROM UNNEST(@window_ends) AS window_end
  JOIN events
    ON event_day BETWEEN DATE_SUB(window_end, INTERVAL @window_days - 1 DAY) AND window_end
  GROUP BY window_end, repository_id
),
ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY window_end ORDER BY stars_gained DESC, repository_id)
      AS star_rank,
    ROW_NUMBER() OVER (PARTITION BY window_end ORDER BY forks_gained DESC, repository_id)
      AS fork_rank
  FROM counts
)
SELECT window_end, repository_id, repository_name, stars_gained, forks_gained
FROM ranked
WHERE star_rank <= @top_size OR fork_rank <= @top_size
ORDER BY window_end, stars_gained DESC, repository_id
"""


class DayTableNotClosedError(Exception):
    """The table of the last day of a window was last modified before that day ended."""


class DryRunOverLimitError(Exception):
    """The dry run of a single window announces more bytes than its cap."""


class DryRunVolumeUnknownError(Exception):
    """The dry run gives no volume: the query is not run (fail closed)."""


class TrendsExtractInvalidError(ValueError):
    """The raw result is not a readable ranking: it is refused whole."""


class TrendRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    window_end: date
    repository_id: Annotated[int, Field(gt=0, le=MAX_INT64)]
    repository_name: RepositoryName
    stars_gained: Annotated[int, Field(ge=0)]
    forks_gained: Annotated[int, Field(ge=0)]


class TrendsExtract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    window_ends: Annotated[list[date], Field(min_length=1)]
    rows: list[TrendRow]


class GhArchiveSource:
    name = FOLDER_PREFIX
    extension = "json"
    acquisition_dir_name = AUTOMATED_WATCH_DIR_NAME

    def __init__(self, create_client: Callable[[], bigquery.Client]) -> None:
        # Created at the collection: a missing or invalid key fails this source alone.
        self.create_client = create_client

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the trends of every window due since last_collected_at; None if none is due.

        The day is read from the clock when the source runs, not when the collection started: a
        collection that runs past midnight UTC collects the next window, and the next collection
        takes it again (a raw file twice, nothing lost).
        """
        window_ends = list_window_ends(last_collected_at, current_day())
        if not window_ends:
            return None
        client = self.create_client()
        check_day_table_closed(client, window_ends[-1])
        window_ends = drop_windows_over_the_cap(client, window_ends)
        job = client.query(
            TRENDS_QUERY,
            job_config=configure_query(window_ends, dry_run=False),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
        rows = job.result(timeout=QUERY_TIMEOUT_SECONDS)
        raw_result = encode_result(window_ends, (dict(row.items()) for row in rows))
        extract = read_trends(raw_result)
        logger.info(
            "gh_archive: %d window(s) from %s to %s, %s bytes processed, %d rows",
            len(window_ends),
            window_ends[0],
            window_ends[-1],
            job.total_bytes_processed,
            len(extract.rows),
        )
        return raw_result


def create_bigquery_client() -> bigquery.Client:
    return bigquery.Client()


def compute_bytes_cap(window_count: int) -> int:
    return min(window_count * MAX_BYTES_PER_WINDOW, MAX_BYTES_BILLED)


def current_day() -> date:
    return datetime.now(UTC).date()


def list_window_ends(last_collected_at: datetime | None, today: date) -> list[date]:
    """The last day of each window due, oldest first, the most recent ending yesterday.

    A collection made on day L covered the window ending on L - 1: the windows due end from L to
    yesterday. A first collection takes the window ending yesterday.
    """
    yesterday = today - timedelta(days=1)
    if last_collected_at is None:
        return [yesterday]
    first_end = last_collected_at.astimezone(UTC).date()
    if first_end > today:
        raise ValueError(f"last collection day {first_end} is after today {today}")
    due_count = (yesterday - first_end).days + 1
    if due_count > MAX_CATCH_UP_WINDOWS:
        logger.info(
            "gh_archive: %d windows due since %s, the %d most recent are collected",
            due_count,
            first_end,
            MAX_CATCH_UP_WINDOWS,
        )
        due_count = MAX_CATCH_UP_WINDOWS
    return [yesterday - timedelta(days=offset) for offset in reversed(range(due_count))]


def check_day_table_closed(client: bigquery.Client, day: date) -> None:
    """Refuse a day whose table was last modified before the day ended: hours may be missing.

    GH Archive adds each hour to the table of its day; the last one arrived around 00:08 UTC the
    next day (seen on 2026-10-11).
    """
    table = client.get_table(
        f"{TABLE_PREFIX}{day:%Y%m%d}", timeout=QUERY_TIMEOUT_SECONDS
    )
    day_end = datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC)
    if table.modified is None or table.modified < day_end:
        raise DayTableNotClosedError(
            f"table of {day} last modified at {describe_time(table.modified)},"
            f" before {day_end.isoformat()}"
        )


def describe_time(moment: datetime | None) -> str:
    return "an unknown time" if moment is None else moment.isoformat()


def drop_windows_over_the_cap(
    client: bigquery.Client, window_ends: list[date]
) -> list[date]:
    """Drop the oldest windows until the dry run fits their cap; refuse one window over it.

    Failing instead would fail every collection once the windows due are over the cap.
    """
    while True:
        dry_run = client.query(
            TRENDS_QUERY,
            job_config=configure_query(window_ends, dry_run=True),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
        bytes_processed = dry_run.total_bytes_processed
        if bytes_processed is None:
            raise DryRunVolumeUnknownError(
                f"dry run of {len(window_ends)} window(s): total_bytes_processed is None"
            )
        cap = compute_bytes_cap(len(window_ends))
        if bytes_processed <= cap:
            return window_ends
        if len(window_ends) == 1:
            raise DryRunOverLimitError(
                f"dry run of the window ending {window_ends[0]}: {bytes_processed} bytes,"
                f" maximum {cap}"
            )
        logger.info(
            "gh_archive: dry run of %d windows: %d bytes, maximum %d; window ending %s dropped",
            len(window_ends),
            bytes_processed,
            cap,
            window_ends[0],
        )
        window_ends = window_ends[1:]


def configure_query(window_ends: list[date], dry_run: bool) -> bigquery.QueryJobConfig:
    first_day = window_ends[0] - timedelta(days=WINDOW_DAYS - 1)
    parameters = [
        bigquery.ScalarQueryParameter(
            "first_suffix", "STRING", f"{first_day:{TABLE_SUFFIX_FORMAT}}"
        ),
        bigquery.ScalarQueryParameter(
            "last_suffix", "STRING", f"{window_ends[-1]:{TABLE_SUFFIX_FORMAT}}"
        ),
        bigquery.ArrayQueryParameter("window_ends", "DATE", window_ends),
        bigquery.ScalarQueryParameter("window_days", "INT64", WINDOW_DAYS),
        bigquery.ScalarQueryParameter("top_size", "INT64", TOP_SIZE),
    ]
    if dry_run:
        return bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, query_parameters=parameters
        )
    return bigquery.QueryJobConfig(
        maximum_bytes_billed=compute_bytes_cap(len(window_ends)),
        query_parameters=parameters,
    )


def encode_result(window_ends: list[date], rows: Iterable[Mapping[str, Any]]) -> bytes:
    result = {
        "window_ends": [window_end.isoformat() for window_end in window_ends],
        "rows": [
            {
                key: value.isoformat() if isinstance(value, date) else value
                for key, value in row.items()
            }
            for row in rows
        ],
    }
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()


def read_trends(raw_result: bytes) -> TrendsExtract:
    """Read a raw result: every row valid, of an announced window, at most two tops per window."""
    try:
        extract = TrendsExtract.model_validate_json(raw_result)
    except ValidationError as error:
        raise TrendsExtractInvalidError(describe_validation_error(error)) from None
    announced = set(extract.window_ends)
    for position, row in enumerate(extract.rows):
        if row.window_end not in announced:
            raise TrendsExtractInvalidError(
                f"row {position}: window {row.window_end} not in window_ends"
            )
    keys = Counter((row.window_end, row.repository_id) for row in extract.rows)
    for (window_end, repository_id), count in keys.items():
        if count > 1:
            raise TrendsExtractInvalidError(
                f"window {window_end}: repository_id {repository_id} twice"
            )
    rows_per_window = Counter(row.window_end for row in extract.rows)
    for window_end, count in rows_per_window.items():
        if count > MAX_ROWS_PER_WINDOW:
            raise TrendsExtractInvalidError(
                f"window {window_end}: {count} rows, at most {MAX_ROWS_PER_WINDOW}"
            )
    return extract


def describe_validation_error(error: ValidationError) -> str:
    """The first error: its place, its type and the value, quoted short and escaped."""
    first = error.errors()[0]
    location = first["loc"]
    if location[:1] == ("rows",) and len(location) >= 2:
        place = f"row {location[1]}: {'.'.join(str(part) for part in location[2:])}"
    else:
        place = ".".join(str(part) for part in location) or "result"
    value = first.get("input")
    if isinstance(value, dict | list):
        # A missing field or a wrong row gives the whole row: it holds the repository name.
        quoted = f"{type(value).__name__} of {len(value)}"
    elif location[-1:] and location[-1] in FIELDS_NEVER_QUOTED:
        quoted = (
            f"length {len(value)}" if isinstance(value, str) else type(value).__name__
        )
    else:
        quoted = repr(value)[:MAX_QUOTED_VALUE_LENGTH]
    return f"{place} ({first['type']}): {quoted}; {error.error_count()} error(s)"
