"""Step 3 of the sorting: delete every raw collection older than its duration, the state catalogs
apart, of which the raw keeps the last file imported (step 7)."""

import logging
from collections.abc import Collection
from datetime import datetime

from k_b.core.config import RAW_RETENTION_MONTHS
from k_b.core.dates import subtract_months
from k_b.etl.raw_files import read_collection_time
from k_b.etl.raw_store import RawCollection, RawStore

logger = logging.getLogger(__name__)


def delete_expired_raw(
    store: RawStore, imported_at: datetime, state_catalog_folder_keys: Collection[str]
) -> int:
    """Delete the collections of every source folder but the state catalogs' collected before the
    bound; return how many. The list comes from the folders, not the registry: the duration is
    a maximum, and the tops are not in the registry. The log gives numbers, never a name."""
    bound = subtract_months(imported_at, RAW_RETENTION_MONTHS)
    deletions = [
        store.delete_collection(collection.key)
        for folder_key in store.list_source_folder_keys()
        if folder_key not in state_catalog_folder_keys
        for collection in store.list_collections(folder_key)
        if is_collected_before(collection, bound)
    ]
    deleted_count = deletions.count("deleted")
    logger.info(
        "raw purge: %d collections older than %d months deleted, %d kept"
        " (a folder or a link inside)",
        deleted_count,
        RAW_RETENTION_MONTHS,
        deletions.count("kept"),
    )
    return deleted_count


def is_collected_before(collection: RawCollection, bound: datetime) -> bool:
    """Tell whether the name of a collection dates it before the bound; a name kb did not give
    never expires."""
    collected_at = read_collection_time(collection.name)
    return collected_at is not None and collected_at < bound
