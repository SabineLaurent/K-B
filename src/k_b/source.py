"""What a source gives the generic steps: how to collect it (E), how to read its raw files (T).

The sources themselves are declared once, in a list that only the command line reads.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, NamedTuple, Protocol

from k_b.items import Item


class Source(Protocol):
    name: str
    extension: str

    def fetch(
        self, last_collected_at: datetime | None
    ) -> bytes | dict[str, bytes] | None:
        """Return the raw content published since last_collected_at (None: first collection).

        A source that reads several pages (a scraped site) returns them by page name. Return
        None when the source says nothing changed since last_collected_at.
        """
        ...


class SourceReader[EntryT](NamedTuple):
    """How to read a raw file of a source: its entries, then each entry as an item.

    Declared in a constant annotated with its entry type, so that mypy refuses a converter of
    another source.
    """

    read_entries: Callable[[bytes], Sequence[EntryT]]
    convert: Callable[[EntryT, datetime, str], Item]


class SourceKind(NamedTuple):
    """A kind of source, declared once: its raw folders, its instances, its reader."""

    # The name of its raw folders, alone or followed by _ (github_releases_<repository>).
    folder_prefix: str
    sources: tuple[Source, ...]
    # None while the kind has no reader yet.
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
