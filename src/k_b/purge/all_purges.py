"""The purges kb purge runs, in this order: the superseded catalogs, the base, the raw, the
registry, then the logs and the journals (docs/registre-traitements.md, procedure of sorting).
The first error stops the others; the next kb purge runs them again."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.database.engine import connect_database
from k_b.database.location import DatabaseLocation, check_database_exists
from k_b.database.reading import read_raw_file_paths
from k_b.etl.raw_store import RawStore
from k_b.purge.base import BasePurgeCount, purge_expired_rows
from k_b.purge.catalogs import delete_superseded_raw_files
from k_b.purge.raw import delete_expired_raw
from k_b.purge.registry import purge_registry
from k_b.purge.run_records import delete_expired_records


class StateCatalog(NamedTuple):
    """A source of which the raw keeps only the last file imported, and the base every row."""

    folder_key: str
    source_code: str


class PurgeCount(NamedTuple):
    """How many each purge deleted."""

    superseded_count: int
    base: BasePurgeCount
    expired_raw_count: int
    registry_count: int
    record_count: int


def purge_all(
    data_dir: Path,
    database: DatabaseLocation,
    purged_at: datetime,
    state_catalogs: Sequence[StateCatalog],
    tracked_repositories: Sequence[TrackedRepository],
) -> PurgeCount:
    """Run the purges in turn; each logs how many it deleted."""
    store = RawStore(data_dir)
    # Read once: no purge before the one of the registry writes to raw_data.
    imported_paths = read_imported_paths(database)
    folder_keys = [catalog.folder_key for catalog in state_catalogs]
    source_codes = frozenset(catalog.source_code for catalog in state_catalogs)
    superseded_count = delete_superseded_raw_files(store, imported_paths, folder_keys)
    base_count = purge_expired_rows(
        database,
        purged_at,
        source_codes,
        [repository.name for repository in tracked_repositories],
    )
    expired_raw_count = delete_expired_raw(
        store, purged_at, folder_keys, imported_paths
    )
    registry_count = purge_registry(database, store, source_codes)
    record_count = delete_expired_records(data_dir, purged_at)
    return PurgeCount(
        superseded_count, base_count, expired_raw_count, registry_count, record_count
    )


def read_imported_paths(database: DatabaseLocation) -> frozenset[str]:
    """The raw files the registry holds; a missing base is refused, never created."""
    check_database_exists(database)
    connection = connect_database(database)
    try:
        return read_raw_file_paths(connection)
    finally:
        connection.close()
