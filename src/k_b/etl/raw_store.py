"""The raw output of each collection, under raw/, and the date of the last collection per source."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple

from k_b.core.atomic_write import write_file_atomically
from k_b.core.quoting import quote_value
from k_b.items import parse_aware_datetime

# The folder of the data directory that holds the raw output of each collection.
RAW_DIR_NAME = "raw"
# The folder of raw/ that holds what the watch collects, one folder per source.
AUTOMATED_WATCH_DIR_NAME = "automated_watch"
# The folder of raw/ that holds what the user selected (ADR of 2026-10-09).
SELECTED_LIBRARY_DIR_NAME = "selected_library"
# The only folders of raw/ a source may write to: a misspelt one would hold raw files that
# no reader looks for.
RAW_DIR_NAMES = (AUTOMATED_WATCH_DIR_NAME, SELECTED_LIBRARY_DIR_NAME)
COLLECTION_STATE_FILENAME = "collection_state.json"

# What became of a collection the purge deleted: kept, it holds a folder or a link.
type CollectionDeletion = Literal["deleted", "already_gone", "kept"]


class RawCollection(NamedTuple):
    """A collection of a source folder, a raw file or a folder of pages, and the name that dates
    it: the name of a folder, the name of a file without its extension."""

    key: str
    name: str


def find_stream(raw_file_path: str) -> str:
    """The stream of a raw file: the name of its source folder (automated_watch/<stream>/...)."""
    parts = PurePosixPath(raw_file_path).parts
    if len(parts) < 3:
        raise ValueError(f"raw file path without a source folder: {raw_file_path}")
    return parts[1]


def make_source_folder_key(acquisition_dir_name: str, source_name: str) -> str:
    """Make the key of the raw folder of a source: raw/<acquisition folder>/<source>."""
    return f"{RAW_DIR_NAME}/{acquisition_dir_name}/{source_name}"


@dataclass(frozen=True)
class RawStore:
    """The raw files of a data directory, each named by a POSIX key relative to it, never by a
    Path (.claude/rules/poc.md, rule 3)."""

    data_dir: Path

    def delete(self, key: str) -> bool:
        """Delete the file of key; False when it is already gone."""
        try:
            self.find_path(key).unlink()
        except FileNotFoundError:
            return False
        return True

    def has_file(self, key: str) -> bool:
        """Tell whether the store holds a file under this key."""
        return self.find_path(key).is_file()

    def has_folder(self, key: str) -> bool:
        """Tell whether the store holds a folder under this key."""
        return self.find_path(key).is_dir()

    def list_source_folder_keys(self) -> list[str]:
        """The keys of the source folders of both acquisition folders, in name order; a hidden
        entry, a file or a link left out."""
        keys: list[str] = []
        for acquisition_dir_name in RAW_DIR_NAMES:
            acquisition_key = f"{RAW_DIR_NAME}/{acquisition_dir_name}"
            keys += sorted(
                f"{acquisition_key}/{path.name}"
                for path in self.list_visible_entries(acquisition_key)
                if is_folder_not_link(path)
            )
        return keys

    def list_collections(self, folder_key: str) -> list[RawCollection]:
        """The collections of a source folder, in name order: its visible files and folders, a
        link left out."""
        collections = []
        for path in sorted(self.list_visible_entries(folder_key)):
            key = f"{folder_key}/{path.name}"
            if is_folder_not_link(path):
                collections.append(RawCollection(key, path.name))
            elif path.is_file() and not path.is_symlink():
                collections.append(RawCollection(key, path.stem))
        return collections

    def delete_collection(self, key: str) -> CollectionDeletion:
        """Delete a collection: its file, or the files of its folder, hidden ones included, then
        the folder. One that holds a folder or a link is kept whole; one already gone, deleted by
        another import, is no error."""
        path = self.find_path(key)
        try:
            if path.is_symlink():
                return "kept"
            if not path.is_dir():
                path.unlink()
                return "deleted"
            entries = list(path.iterdir())
            if any(entry.is_symlink() or entry.is_dir() for entry in entries):
                return "kept"
            for entry in entries:
                self.delete(f"{key}/{entry.name}")
            path.rmdir()
        except FileNotFoundError:
            return "already_gone"
        return "deleted"

    def list_visible_entries(self, folder_key: str) -> list[Path]:
        """The entries of a folder whose name does not start with a dot; none when the folder is
        absent or a link, or gone meanwhile."""
        folder = self.find_path(folder_key)
        if not is_folder_not_link(folder):
            return []
        try:
            return [path for path in folder.iterdir() if not path.name.startswith(".")]
        except FileNotFoundError:
            return []

    def read_latest(self, folder_key: str) -> bytes | None:
        """The last raw file of a folder in collection order; None when it has none."""
        keys = self.list_file_keys(folder_key)
        if not keys:
            return None
        return self.read(keys[-1])

    def list_file_keys(self, folder_key: str) -> list[str]:
        """The keys of the files of a folder, in collection order, hidden files and subfolders
        left out."""
        folder = self.find_path(folder_key)
        if not folder.is_dir():
            return []
        return sorted(
            f"{folder_key}/{path.name}"
            for path in folder.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )

    def read(self, key: str) -> bytes:
        """Read the bytes of the file under this key."""
        return self.find_path(key).read_bytes()

    def find_path(self, key: str) -> Path:
        """The path of key in the data directory; a key empty, absolute, going up (..) or holding
        a backslash is refused, as the keys of the purges come from the base and the folders."""
        key_path = PurePosixPath(key)
        if (
            not key_path.parts
            or key_path.is_absolute()
            or ".." in key_path.parts
            or "\\" in key
        ):
            raise ValueError(
                f"not a key relative to the data directory: {quote_value(key)}"
            )
        return self.data_dir.joinpath(*key_path.parts)


def is_folder_not_link(path: Path) -> bool:
    """Tell whether path is a folder that is not a link: the purge never follows one."""
    return path.is_dir() and not path.is_symlink()


class InvalidCollectionStateError(ValueError):
    """The collection state file cannot be trusted: collecting from it could skip data."""


def write_new_raw_file(path: Path, content: bytes) -> None:
    """Write a raw file once: raw/ is immutable, a raw file is never overwritten."""
    if path.exists():
        raise FileExistsError(f"raw file already exists: {path}")
    write_file_atomically(path, content)


def load_last_collection_dates(data_dir: Path) -> dict[str, datetime]:
    """The date of the last collection of each source; empty when the state file is absent.

    A state half read would make the next collection start from a date nobody wrote:
    InvalidCollectionStateError instead."""
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
    """Write the date of the last collection of each source, whole and atomically."""
    stored_dates = {
        source_name: collected_at.isoformat()
        for source_name, collected_at in last_collection_dates.items()
    }
    state_content = json.dumps(stored_dates, indent=2, sort_keys=True) + "\n"
    write_file_atomically(
        data_dir / COLLECTION_STATE_FILENAME, state_content.encode("utf-8")
    )
