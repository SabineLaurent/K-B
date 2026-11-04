"""The registry after the purges: a row of raw_data goes once its raw file is gone and nothing in
the base cites it any more; the last catalog of a state catalog stays, as the import reads it
(database/writers/catalog.py)."""

import logging
import sqlite3
from collections.abc import Collection
from pathlib import Path

from k_b.database import purge as purge_queries
from k_b.database.connection import connect_database
from k_b.etl.raw_store import RAW_DIR_NAME, RawStore

logger = logging.getLogger(__name__)


def purge_registry(
    database_path: Path, store: RawStore, state_catalog_source_codes: Collection[str]
) -> int:
    """Delete the rows of the registry whose file is gone and that nothing cites; return how
    many. Without a raw folder, nothing: every file would seem gone, and be imported again once
    the folder is back (a volume not mounted)."""
    if not store.has_folder(RAW_DIR_NAME):
        logger.info("registry purge skipped: no raw folder")
        return 0
    connection = connect_database(database_path)
    try:
        deleted_count = delete_rows_without_file(
            connection, store, state_catalog_source_codes
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    logger.info("registry purge: %d rows deleted", deleted_count)
    return deleted_count


def delete_rows_without_file(
    connection: sqlite3.Connection,
    store: RawStore,
    state_catalog_source_codes: Collection[str],
) -> int:
    """Delete each uncited row whose file is gone, but the last catalog of a state catalog, which
    tells the import which catalog came last; return how many."""
    state_catalog_source_ids = {
        source.id
        for source in purge_queries.read_sources(connection)
        if source.source_code in state_catalog_source_codes
    }
    last_collections = purge_queries.read_last_collection_of_each_source(connection)
    return sum(
        purge_queries.delete_uncited_raw_data(connection, row.id)
        for row in purge_queries.read_uncited_raw_data(connection)
        if not (
            row.source_id in state_catalog_source_ids
            and row.collected_at == last_collections[row.source_id]
        )
        and not store.has_file(f"{RAW_DIR_NAME}/{row.raw_file_path}")
    )
