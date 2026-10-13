"""The raw output of each collection, under raw/, and the date of the last one per source, in
the collection state file at the root of the data directory."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

# The folder of raw/ that holds what the watch collects, one folder per source.
AUTOMATED_WATCH_DIR_NAME = "automated_watch"
# The folder of raw/ that holds what the user selected (ADR of 2026-10-09).
SELECTED_LIBRARY_DIR_NAME = "selected_library"
# The only folders of raw/ a source may write to: a misspelt one would hold raw files that
# no reader looks for.
RAW_DIR_NAMES = (AUTOMATED_WATCH_DIR_NAME, SELECTED_LIBRARY_DIR_NAME)
COLLECTION_STATE_FILENAME = "collection_state.json"


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
    """Write to a temporary file, then rename it: a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary_file:
        temporary_file.write(content)
    try:
        os.replace(temporary_file.name, path)
    except OSError:
        os.remove(temporary_file.name)
        raise


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
            source_name: parse_utc_aware_datetime(stored_date)
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


def parse_utc_aware_datetime(stored_date: object) -> datetime:
    """Refuse anything but an ISO 8601 date with a time zone: naive dates compare wrongly."""
    if not isinstance(stored_date, str):
        raise ValueError(f"expected an ISO 8601 date, got {stored_date!r}")
    parsed_date = datetime.fromisoformat(stored_date)
    if parsed_date.tzinfo is None:
        raise ValueError(f"date without a time zone: {stored_date!r}")
    return parsed_date
