"""Files under raw/: the raw output of each collection and the date of the last one per source."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

COLLECTION_STATE_FILENAME = "collection_state.json"


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


def load_last_collection_dates(raw_dir: Path) -> dict[str, datetime]:
    state_path = raw_dir / COLLECTION_STATE_FILENAME
    if not state_path.exists():
        return {}
    try:
        state_content = state_path.read_text(encoding="utf-8")
    except OSError as error:
        raise InvalidCollectionStateError(
            f"{state_path} cannot be read: {error.strerror}"
        ) from error
    try:
        stored_dates = json.loads(state_content)
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


def save_last_collection_dates(raw_dir: Path, last_collection_dates: dict[str, datetime]) -> None:
    stored_dates = {
        source_name: collected_at.isoformat()
        for source_name, collected_at in last_collection_dates.items()
    }
    state_content = json.dumps(stored_dates, indent=2, sort_keys=True) + "\n"
    write_file_atomically(raw_dir / COLLECTION_STATE_FILENAME, state_content.encode("utf-8"))


def parse_utc_aware_datetime(stored_date: object) -> datetime:
    """Refuse anything but an ISO 8601 date with a time zone: naive dates compare wrongly."""
    if not isinstance(stored_date, str):
        raise ValueError(f"expected an ISO 8601 date, got {stored_date!r}")
    parsed_date = datetime.fromisoformat(stored_date)
    if parsed_date.tzinfo is None:
        raise ValueError(f"date without a time zone: {stored_date!r}")
    return parsed_date
