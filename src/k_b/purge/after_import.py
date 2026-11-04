"""The purges kb import runs once its import committed, in this order: the superseded catalogs,
the base, the raw, then the registry (docs/registre-traitements.md, procedure of sorting). The
first error stops the others; the next import runs them again."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.database.connection import DATABASE_FILE_NAME
from k_b.etl.raw_store import RawStore
from k_b.purge.base import purge_expired_rows
from k_b.purge.catalogs import purge_superseded_catalogs
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
    """Run the purges, the registry last, once the base and the raw purged; each logs how many
    it deleted."""
    store = RawStore(data_dir)
    database_path = data_dir / DATABASE_FILE_NAME
    folder_keys = [catalog.folder_key for catalog in state_catalogs]
    source_codes = frozenset(catalog.source_code for catalog in state_catalogs)
    purge_superseded_catalogs(database_path, store, folder_keys)
    purge_expired_rows(
        database_path,
        imported_at,
        source_codes,
        [repository.name for repository in tracked_repositories],
    )
    delete_expired_raw(store, imported_at, folder_keys)
    purge_registry(database_path, store, source_codes)
