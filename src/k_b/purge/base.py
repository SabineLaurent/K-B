"""Step 2 of the sorting: delete from the base the watch past its duration, then the references
nothing cites any more and the tracked repositories no longer tracked."""

import logging
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from typing import NamedTuple

from k_b.core.config import RETENTION_YEARS_BY_ACQUISITION_MODE
from k_b.core.dates import DATABASE_DATE_FORMAT, subtract_months
from k_b.database import purge as purge_queries
from k_b.database.engine import Connection, connect_database, lock_for_writing
from k_b.database.location import DatabaseLocation

logger = logging.getLogger(__name__)


class BasePurgeCount(NamedTuple):
    """How many rows the purge of the base deleted, of each sort."""

    item_count: int
    trend_count: int
    reference_count: int
    tracked_repository_count: int


def purge_expired_rows(
    database: DatabaseLocation,
    purged_at: datetime,
    state_catalog_source_codes: Collection[str],
    tracked_repository_names: Sequence[str],
) -> BasePurgeCount:
    """Delete, in one transaction, what is past its duration and what it leaves uncited, once an
    import in progress on PostgreSQL has committed; log how many rows, never a name."""
    connection = connect_database(database)
    try:
        lock_for_writing(connection)
        count = delete_expired_rows(
            connection,
            purged_at,
            state_catalog_source_codes,
            tracked_repository_names,
        )
        connection.commit()
    except BaseException:
        # Ctrl-C and SIGTERM too: the base stays as it was before the purge. Only an open
        # transaction: a connection psycopg closed on a signal refuses the rollback, whose error
        # would replace the signal (exit 1 instead of 143), as in etl/load.py.
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
    logger.info(
        "base purge: %d items, %d trend rows, %d references, %d tracked repositories deleted",
        *count,
    )
    return count


def delete_expired_rows(
    connection: Connection,
    purged_at: datetime,
    state_catalog_source_codes: Collection[str],
    tracked_repository_names: Sequence[str],
) -> BasePurgeCount:
    """The steps of the purge of the base, source by source, in the order of the foreign keys."""
    item_count = trend_count = 0
    for source in purge_queries.read_sources(connection):
        bound = find_bound(source, purged_at, state_catalog_source_codes)
        if bound is None:
            continue
        item_count += purge_queries.delete_expired_items(connection, source.id, bound)
        trend_count += purge_queries.delete_expired_trends(connection, source.id, bound)
    reference_count = purge_queries.delete_uncited_references(connection)
    tracked_repository_count = delete_untracked_repositories(
        connection, tracked_repository_names
    )
    return BasePurgeCount(
        item_count, trend_count, reference_count, tracked_repository_count
    )


def find_bound(
    source: purge_queries.SourceRow,
    purged_at: datetime,
    state_catalog_source_codes: Collection[str],
) -> str | None:
    """The collection before which the data of a source expires, in the format of the base;
    None for a source kept without limit: its mode has no duration, or it is a state catalog."""
    years = RETENTION_YEARS_BY_ACQUISITION_MODE[source.acquisition_mode]
    if years is None or source.source_code in state_catalog_source_codes:
        return None
    bound = subtract_months(purged_at.astimezone(UTC), years * 12)
    return bound.strftime(DATABASE_DATE_FORMAT)


def delete_untracked_repositories(
    connection: Connection,
    tracked_repository_names: Sequence[str],
) -> int:
    """Delete the tracked repositories out of the list that no release cites any more; the names
    compare without case, as the base does (COLLATE NOCASE). Return how many."""
    tracked = {name.casefold() for name in tracked_repository_names}
    return sum(
        purge_queries.delete_tracked_repository_without_release(
            connection, repository.id
        )
        for repository in purge_queries.read_tracked_repositories_without_release(
            connection
        )
        if repository.repository_name.casefold() not in tracked
    )
