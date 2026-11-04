"""The purges kb import runs once its import committed, in this order: the superseded catalogs,
the base, the raw, then the registry (docs/registre-traitements.md, procedure of sorting). The
first error stops the others; the next import runs them again."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.database.connection import (
    DATABASE_FILE_NAME,
    check_database_exists,
    connect_database,
)
from k_b.database.reading import read_raw_file_paths
from k_b.etl.raw_store import RawStore
from k_b.purge.base import purge_expired_rows
from k_b.purge.catalogs import delete_superseded_raw_files
from k_b.purge.raw import delete_expired_raw
from k_b.purge.registry import purge_registry


class StateCatalog(NamedTuple):
    """A source of which the raw keeps only the last file imported, and the base every row."""

    folder_key: str
    source_code: str


def purge_after_import(
    data_dir: Path,
    imported_at: datetime,
    state_catalogs: Sequence[StateCatalog],
    tracked_repositories: Sequence[TrackedRepository],
) -> None:
    """Run the purges, the registry last; each logs how many it deleted."""
    store = RawStore(data_dir)
    database_path = data_dir / DATABASE_FILE_NAME
    # Read once: no purge before the one of the registry writes to raw_data.
    imported_paths = read_imported_paths(database_path)
    folder_keys = [catalog.folder_key for catalog in state_catalogs]
    source_codes = frozenset(catalog.source_code for catalog in state_catalogs)
    delete_superseded_raw_files(store, imported_paths, folder_keys)
    purge_expired_rows(
        database_path,
        imported_at,
        source_codes,
        [repository.name for repository in tracked_repositories],
    )
    delete_expired_raw(store, imported_at, folder_keys, imported_paths)
    purge_registry(database_path, store, source_codes)


def read_imported_paths(database_path: Path) -> frozenset[str]:
    """The raw files the registry holds; a missing base is refused, never created."""
    check_database_exists(database_path)
    connection = connect_database(database_path)
    try:
        return read_raw_file_paths(connection)
    finally:
        connection.close()
