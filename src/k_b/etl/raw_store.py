"""The raw output of each collection, under raw/, and the date of the last one per source, in
the collection state file at the root of the data directory."""

import contextlib
import errno
import itertools
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from k_b.core.quoting import quote_value
from k_b.items import parse_aware_datetime

# The folder of raw/ that holds what the watch collects, one folder per source.
AUTOMATED_WATCH_DIR_NAME = "automated_watch"
# The folder of raw/ that holds what the user selected (ADR of 2026-10-09).
SELECTED_LIBRARY_DIR_NAME = "selected_library"
# The only folders of raw/ a source may write to: a misspelt one would hold raw files that
# no reader looks for.
RAW_DIR_NAMES = (AUTOMATED_WATCH_DIR_NAME, SELECTED_LIBRARY_DIR_NAME)
COLLECTION_STATE_FILENAME = "collection_state.json"
# The errors of a file system that does not support the sync of a folder: EINVAL (fsync(2)),
# EBADF on some systems. PostgreSQL tolerates the same two, EINVAL since bug #15636 on Linux
# CIFS (https://www.postgresql.org/message-id/E1gxrcU-0002A8-17%40gemulon.postgresql.org,
# read on 2026-10-16). Any other error is raised: the rename is not known to be on disk.
REFUSED_FOLDER_SYNC_ERRORS = (errno.EBADF, errno.EINVAL)


def find_stream(raw_file_path: str) -> str:
    """The stream of a raw file: the name of its source folder, second part of its path
    relative to raw/ (automated_watch/<stream>/...)."""
    parts = PurePosixPath(raw_file_path).parts
    if len(parts) < 3:
        raise ValueError(f"raw file path without a source folder: {raw_file_path}")
    return parts[1]


class InvalidCollectionStateError(ValueError):
    """The collection state file cannot be trusted: collecting from it could skip data."""


def write_file_atomically(path: Path, content: bytes) -> None:
    """Write to a hidden temporary file of the target folder, sync it to disk, rename it, then
    sync the folder and each folder created for it: a reader never sees a half-written file,
    and a power cut cannot keep a later file while losing this one. On any exception, Ctrl-C
    included, the temporary file is removed and the exception raised; a rest left by a killed
    process is hidden, so the import skips it (list_visible_entries)."""
    # The folder of the target, then each new parent up to the first that exists: each holds
    # the entry of a new file or folder.
    folders_to_sync = [path.parent]
    folders_to_sync += [
        folder.parent
        for folder in itertools.takewhile(
            lambda folder: not folder.exists(), path.parents
        )
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as temporary_file:
        try:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_file.close()
            os.replace(temporary_file.name, path)
        except BaseException:
            # The original error is raised. A failed flush leaves data in the buffer: closed
            # here, the file does not fail again on leaving the with block. The temporary file
            # may already be renamed (Ctrl-C right after os.replace) or not removable.
            with contextlib.suppress(OSError):
                temporary_file.close()
            with contextlib.suppress(OSError):
                os.remove(temporary_file.name)
            raise
    for folder in folders_to_sync:
        folder_descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(folder_descriptor)
        except OSError as error:
            if error.errno not in REFUSED_FOLDER_SYNC_ERRORS:
                raise
        finally:
            os.close(folder_descriptor)


def write_new_raw_file(path: Path, content: bytes) -> None:
    """raw/ is immutable: a raw file is written once and never overwritten."""
    if path.exists():
        raise FileExistsError(f"raw file already exists: {path}")
    write_file_atomically(path, content)


def load_last_collection_dates(data_dir: Path) -> dict[str, datetime]:
    state_path = data_dir / COLLECTION_STATE_FILENAME
    if not state_path.exists():
        return {}
    try:
        state_content = state_path.read_bytes()
    except OSError as error:
        raise InvalidCollectionStateError(
            f"{state_path} cannot be read: {error.strerror}"
        ) from error
    try:
        stored_dates = json.loads(state_content.decode("utf-8"))
        if not isinstance(stored_dates, dict):
            raise ValueError("expected an object mapping each source name to a date")
        return {
            source_name: parse_aware_datetime(
                stored_date, f"date of {quote_value(source_name)}"
            )
            for source_name, stored_date in stored_dates.items()
        }
    except ValueError as error:
        raise InvalidCollectionStateError(
            f"{state_path} is invalid ({error}); fix it, or delete it to collect every source "
            "from scratch"
        ) from error


def save_last_collection_dates(
    data_dir: Path, last_collection_dates: dict[str, datetime]
) -> None:
    stored_dates = {
        source_name: collected_at.isoformat()
        for source_name, collected_at in last_collection_dates.items()
    }
    state_content = json.dumps(stored_dates, indent=2, sort_keys=True) + "\n"
    write_file_atomically(
        data_dir / COLLECTION_STATE_FILENAME, state_content.encode("utf-8")
    )
