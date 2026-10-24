"""The two runs of the ETL, which talk to each other through raw/: the collection (stage 1,
etl/extract.py) and the import (stages 2 and 3, etl/transform.py then etl/load.py). They run
apart: kb collect writes raw/, kb import reads it.

The only module of etl that chains the stages, and the only door of the two runs for commands/:
__all__ lists what passes, as database/writing.py does for the writers. It reads no setting,
prints nothing and returns no exit code: what names the sources (the kinds, the tracked
repositories, the folders of a state catalog) comes in as a parameter, and each run returns a
named outcome its command prints. Each stage keeps its own log lines.

The retention of the raw is a step of its own, outside the three stages (etl/raw_purge.py):
its command runs it once it has printed the summary of the import, so that a purge that fails
leaves the summary of the import it committed.
"""

from collections.abc import Collection, Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.database.connection import DATABASE_FILE_NAME
from k_b.etl.extract import CollectionOutcome, collect_all_sources
from k_b.etl.load import (
    ImportLogExistsError,
    ImportSummary,
    import_items,
    read_imported_paths,
)
from k_b.etl.raw_files import COLLECTION_NAME_FORMAT
from k_b.etl.raw_purge import delete_superseded_raw_files
from k_b.etl.raw_store import RAW_DIR_NAME, RawStore
from k_b.etl.source_contract import Source, SourceKind
from k_b.etl.transform import read_raw_files

__all__ = [
    "CollectionOutcome",
    "ImportLogExistsError",
    "ImportOutcome",
    "collect",
    "import_raw_files",
    "purge_superseded_raw",
]

# One log per import, named by its second as a raw file by its collection: never rewritten.
IMPORT_LOG_FILE_NAME = "import-log-{imported_at}.jsonl"


class ImportOutcome(NamedTuple):
    """What the import gives its command: what it wrote, and the log that details it."""

    summary: ImportSummary
    log_path: Path


def collect(sources: list[Source], data_dir: Path, now: datetime) -> CollectionOutcome:
    """Run the collection: each source given writes its raw files under raw/, then the
    collection state is written (stage 1).

    The sources are created by the composition, which the caller holds: a source failing or
    skipped is its business, this run only gives them the data directory and the time.
    """
    return collect_all_sources(sources, data_dir / RAW_DIR_NAME, data_dir, now)


def import_raw_files(
    data_dir: Path,
    kinds: Sequence[SourceKind],
    tracked_repositories: Sequence[TrackedRepository],
    imported_at: datetime,
) -> ImportOutcome:
    """Run the import: the registry of the base, then the raw files not in it read as items and
    as trends, in one walk of raw/ (stage 2), then the base and the log of this import, in one
    transaction (stage 3).

    The tracked repositories are given once: the filter of the reading and the table of the base
    cannot read two different lists.
    """
    database_path = data_dir / DATABASE_FILE_NAME
    log_path = data_dir / IMPORT_LOG_FILE_NAME.format(
        imported_at=imported_at.strftime(COLLECTION_NAME_FORMAT)
    )
    imported_paths = read_imported_paths(database_path)
    readings = read_raw_files(
        data_dir / RAW_DIR_NAME, kinds, imported_paths, tracked_repositories
    )
    summary = import_items(
        readings.items,
        readings.trends,
        database_path,
        log_path,
        imported_at,
        tracked_repositories,
    )
    return ImportOutcome(summary, log_path)


def purge_superseded_raw(
    data_dir: Path, latest_only_folder_keys: Collection[str]
) -> int:
    """Delete the raw files of the folders given that the last one imported superseded; return
    how many.

    Run after the import: the registry is read again, so a file the base registers for the first
    time can be the one kept.
    """
    return delete_superseded_raw_files(
        RawStore(data_dir),
        read_imported_paths(data_dir / DATABASE_FILE_NAME),
        latest_only_folder_keys,
    )
