"""Step 3 of the sorting: delete every raw collection older than its duration, the state catalogs
apart, of which the raw keeps the last file imported (step 7)."""

import logging
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import PurePosixPath

from k_b.core.config import RAW_RETENTION_MONTHS
from k_b.core.dates import subtract_months
from k_b.etl.raw_files import read_collection_time
from k_b.etl.raw_store import RAW_DIR_NAME, RawCollection, RawStore

logger = logging.getLogger(__name__)


def delete_expired_raw(
    store: RawStore,
    imported_at: datetime,
    state_catalog_folder_keys: Collection[str],
    imported_paths: frozenset[str],
) -> int:
    """Delete the collections older than the duration, listed from the folders: the duration is a
    maximum, a collection never imported goes too, and the log counts it."""
    bound = subtract_months(imported_at.astimezone(UTC), RAW_RETENTION_MONTHS)
    imported_keys = find_imported_keys(imported_paths)
    deleted_count = never_imported_count = kept_count = 0
    for folder_key in store.list_source_folder_keys():
        if folder_key in state_catalog_folder_keys:
            continue
        for collection in store.list_collections(folder_key):
            if not is_collected_before(collection, bound):
                continue
            deletion = store.delete_collection(collection.key)
            deleted_count += deletion == "deleted"
            never_imported_count += (
                deletion == "deleted" and collection.key not in imported_keys
            )
            kept_count += deletion == "kept"
    logger.info(
        "raw purge: %d collections older than %d months deleted, %d of them never imported,"
        " %d kept (a folder or a link inside)",
        deleted_count,
        RAW_RETENTION_MONTHS,
        never_imported_count,
        kept_count,
    )
    return deleted_count


def find_imported_keys(imported_paths: frozenset[str]) -> frozenset[str]:
    """The keys of the collections the registry holds: a raw file, or the folder of a page."""
    keys = {f"{RAW_DIR_NAME}/{path}" for path in imported_paths}
    return frozenset(keys | {str(PurePosixPath(key).parent) for key in keys})


def is_collected_before(collection: RawCollection, bound: datetime) -> bool:
    """Tell whether the name of a collection dates it before the bound; a name kb did not give
    never expires."""
    collected_at = read_collection_time(collection.name)
    return collected_at is not None and collected_at < bound
