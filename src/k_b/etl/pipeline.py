"""The two runs of the ETL, which talk through raw/: the collection (etl/extract.py) and the
import (etl/transform.py, then etl/load.py).

The only door of the two runs for commands/ (__all__): it reads no setting, prints nothing and
returns a named outcome its command prints."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import JOURNALS_DIR_NAME, TrackedRepository
from k_b.database.connection import DATABASE_FILE_NAME
from k_b.etl.extract import CollectionOutcome, collect_all_sources
from k_b.etl.load import (
    ImportJournalExistsError,
    ImportSummary,
    import_items,
    read_imported_paths,
)
from k_b.etl.raw_files import COLLECTION_NAME_FORMAT
from k_b.etl.raw_store import RAW_DIR_NAME
from k_b.etl.source_contract import Source, SourceKind
from k_b.etl.transform import read_raw_files

__all__ = [
    "CollectionOutcome",
    "ImportJournalExistsError",
    "ImportOutcome",
    "collect",
    "import_raw_files",
]

# One journal per import, named by its second as a raw file by its collection: never rewritten.
IMPORT_JOURNAL_FILE_NAME = "import-journal-{imported_at}.jsonl"


class ImportOutcome(NamedTuple):
    """What the import gives its command: what it wrote, and the journal that details it."""

    summary: ImportSummary
    journal_path: Path


def collect(sources: list[Source], data_dir: Path, now: datetime) -> CollectionOutcome:
    """Run the collection: each source given writes its raw files under raw/, then the collection
    state is written."""
    return collect_all_sources(sources, data_dir / RAW_DIR_NAME, data_dir, now)


def import_raw_files(
    data_dir: Path,
    kinds: Sequence[SourceKind],
    tracked_repositories: Sequence[TrackedRepository],
    imported_at: datetime,
) -> ImportOutcome:
    """Run the import: the raw files not in the registry of the base read in one walk of raw/,
    then written with the journal in one transaction.

    The tracked repositories are given once, so that the reading and the base cannot read two
    lists."""
    database_path = data_dir / DATABASE_FILE_NAME
    journal_path = (
        data_dir
        / JOURNALS_DIR_NAME
        / IMPORT_JOURNAL_FILE_NAME.format(
            imported_at=imported_at.strftime(COLLECTION_NAME_FORMAT)
        )
    )
    imported_paths = read_imported_paths(database_path)
    readings = read_raw_files(
        data_dir / RAW_DIR_NAME, kinds, imported_paths, tracked_repositories
    )
    summary = import_items(
        readings.items,
        readings.trends,
        database_path,
        journal_path,
        imported_at,
        tracked_repositories,
    )
    return ImportOutcome(summary, journal_path)
