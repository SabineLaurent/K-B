"""The vocabulary the stages of the ETL share: a raw file read, a ranking read, and a rejection."""

from datetime import UTC, datetime
from typing import NamedTuple

from k_b.items import Item, SourceCode, TrendRow

# The name etl/extract.py gives every raw file of a collection.
COLLECTION_NAME_FORMAT = "%Y-%m-%dT%H%M%SZ"


def parse_collection_name(collection_name: str) -> datetime:
    return datetime.strptime(collection_name, COLLECTION_NAME_FORMAT).replace(
        tzinfo=UTC
    )


class Rejection(NamedTuple):
    raw_file_path: str
    reason: str


class RawFile(NamedTuple):
    """A raw file read: a page, for a collection that is a folder of pages."""

    raw_file_path: str
    source_code: SourceCode
    collected_at: datetime
    items: list[Item]
    # Its entries rejected by its reader or refused as items: a catalog with one of them
    # withdraws nothing (#106).
    rejection_count: int


class RawReading(NamedTuple):
    files: list[RawFile]
    rejections: list[Rejection]
    # The pages opened, readable or not.
    read_count: int


class TrendFile(NamedTuple):
    """A raw ranking of GH Archive read: the file to register, and its rows, which are not
    items."""

    raw_file: RawFile
    rows: list[TrendRow]


class TrendReading(NamedTuple):
    files: list[TrendFile]
    rejections: list[Rejection]
    # The rankings opened, readable or not.
    read_count: int
