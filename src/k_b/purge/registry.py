"""The registry after the purges: a row of raw_data goes once its raw file is gone and nothing in
the base cites it any more; the last catalog of a state catalog stays, as the import reads it
(database/writers/catalog.py)."""

import logging
from collections.abc import Collection

from k_b.database import purge as purge_queries
from k_b.database.engine import Connection, connect_database, lock_for_writing
from k_b.database.location import DatabaseLocation
from k_b.etl.raw_store import RAW_DIR_NAME, RAW_DIR_NAMES, RawStore

logger = logging.getLogger(__name__)


def purge_registry(
    database: DatabaseLocation,
    store: RawStore,
    state_catalog_source_codes: Collection[str],
) -> int:
    """Delete the rows of the registry whose file is gone and that nothing cites, once an import in
    progress on PostgreSQL has committed; return how many."""
    connection = connect_database(database)
    try:
        lock_for_writing(connection)
        deleted_count = delete_rows_without_file(
            connection, store, state_catalog_source_codes
        )
        connection.commit()
    except BaseException:
        # Only an open transaction, as in purge/base.py.
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
    logger.info("registry purge: %d rows deleted", deleted_count)
    return deleted_count


def delete_rows_without_file(
    connection: Connection,
    store: RawStore,
    state_catalog_source_codes: Collection[str],
) -> int:
    """Delete each uncited row whose file is gone, but the last catalog of a state catalog, and
    any row of an acquisition folder absent: a volume not mounted makes every file of it look gone,
    to be imported again once it is back."""
    mounted_dir_names = {
        dir_name
        for dir_name in RAW_DIR_NAMES
        if store.has_folder(f"{RAW_DIR_NAME}/{dir_name}")
    }
    state_catalog_source_ids = {
        source.id
        for source in purge_queries.read_sources(connection)
        if source.source_code in state_catalog_source_codes
    }
    last_collections = purge_queries.read_last_collection_of_each_source(connection)
    return sum(
        purge_queries.delete_uncited_raw_data(connection, row.id)
        for row in purge_queries.read_uncited_raw_data(connection)
        if row.raw_file_path.partition("/")[0] in mounted_dir_names
        and not (
            row.source_id in state_catalog_source_ids
            and row.collected_at == last_collections[row.source_id]
        )
        and is_file_gone(store, row.raw_file_path)
    )


def is_file_gone(store: RawStore, raw_file_path: str) -> bool:
    """Tell whether the raw file of a row is gone; a path the store refuses stays, as the raw purge
    leaves a name it refuses."""
    try:
        return not store.has_file(f"{RAW_DIR_NAME}/{raw_file_path}")
    except ValueError:
        return False
