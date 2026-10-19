"""What a source gives the generic steps: how to collect it (E), how to read its raw files (T).

The sources themselves are declared once, in SOURCE_KINDS, that only commands/collect_command.py
and commands/import_command.py import in the package.
"""

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Any, NamedTuple, Protocol

from k_b.items import Item, SourceCode


class Source(Protocol):
    name: str
    extension: str
    # The folder of raw/ its raw files go to: the watch, or what the user selected.
    acquisition_dir_name: str

    def fetch(
        self, last_collected_at: datetime | None
    ) -> bytes | dict[str, bytes] | None:
        """Return the raw content published since last_collected_at (None: first collection).

        A source that reads several pages (a scraped site) returns them by page name. Return
        None when the source says nothing changed since last_collected_at.
        """
        ...


class EntryReading[EntryT](NamedTuple):
    """The entries of a raw file read, and the reason each invalid one was rejected."""

    entries: list[EntryT]
    # Each one names its entry (position or line, identifier once read) and its field.
    rejection_reasons: list[str]


def read_each_entry[RawEntryT, EntryT](
    numbered_entries: Iterable[tuple[int, RawEntryT]],
    parse: Callable[[RawEntryT, int], EntryT],
) -> EntryReading[EntryT]:
    """Parse each entry with its number; one that parse refuses (ValueError) is rejected with
    its reason, and the others are still read (conventions.md, rule 1).

    Only parse is guarded: an error while listing the entries (csv.Error) leaves the whole page
    unreadable.
    """
    entries = []
    rejection_reasons = []
    for number, raw_entry in numbered_entries:
        try:
            entry = parse(raw_entry, number)
        except ValueError as error:
            rejection_reasons.append(str(error))
            continue
        entries.append(entry)
    return EntryReading(entries, rejection_reasons)


def check_not_all_invalid(reading: EntryReading[Any]) -> None:
    """Refuse, at the collection, a page whose entries are all invalid (all_items_invalid): its
    source fails, so its last collection date stays and nothing is written to raw/. A page
    without any entry is not refused."""
    if reading.rejection_reasons and not reading.entries:
        raise ValueError(
            f"all_items_invalid: {len(reading.rejection_reasons)} entries, all rejected; "
            f"first: {reading.rejection_reasons[0]}"
        )


def check_not_empty(reading: EntryReading[Any]) -> None:
    """Refuse, at the collection, a state catalog without any entry (empty_catalog): its source
    fails, so nothing is written to raw/. Imported, it would supersede the last catalog, which the
    purge would then delete (ADR of 2026-10-19); the import already withdraws nothing for it."""
    if not reading.entries and not reading.rejection_reasons:
        raise ValueError("empty_catalog: 0 entries")


class SourceReader[EntryT](NamedTuple):
    """How to read a raw file of a source: its entries, then each entry as an item.

    read_entries raises only for a page it cannot read; it rejects an invalid entry alone.

    Declared in a constant annotated with its entry type, so that mypy refuses a converter of
    another source.
    """

    # The source_code of its items, and of its raw files in the base, even one without item.
    source_code: SourceCode
    read_entries: Callable[[bytes], EntryReading[EntryT]]
    convert: Callable[[EntryT, datetime, str], Item]


class SourceKind(NamedTuple):
    """A kind of source, declared once: its raw folders, its instances, its reader.

    Pass the READER constant of the reader module, never a SourceReader built here: only an
    annotated constant lets mypy refuse a converter of another source.
    """

    # The name of its raw folders, alone or followed by _ (github_releases_<repository>).
    folder_prefix: str
    sources: tuple[Source, ...]
    # None: its raw files are not read into items (no reader yet, none planned, or raw files
    # that are not items: the rankings of GH Archive).
    reader: SourceReader[Any] | None


def list_sources(kinds: Sequence[SourceKind]) -> list[Source]:
    return [source for kind in kinds for source in kind.sources]


def find_source_kind(
    folder_name: str, kinds: Sequence[SourceKind]
) -> SourceKind | None:
    """The kind a raw folder belongs to, tracked or not any more (cisa_kev_old is CISA's)."""
    for kind in kinds:
        if folder_name == kind.folder_prefix or folder_name.startswith(
            kind.folder_prefix + "_"
        ):
            return kind
    return None
