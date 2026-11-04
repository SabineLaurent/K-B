"""The vocabulary the stages of the ETL share: a raw file read, a file of trends read, a
rejection."""

from datetime import UTC, datetime
from typing import NamedTuple

from k_b.items import Item, SourceCode, TrendRow

# The name etl/extract.py gives every raw file of a collection.
COLLECTION_NAME_FORMAT = "%Y-%m-%dT%H%M%SZ"


def parse_collection_name(collection_name: str) -> datetime:
    """The collection time a raw file or a folder of pages is named by, in UTC; ValueError for
    another name."""
    return datetime.strptime(collection_name, COLLECTION_NAME_FORMAT).replace(
        tzinfo=UTC
    )


def read_collection_time(collection_name: str) -> datetime | None:
    """The collection time of a name kb gave, None for another name; strptime alone would take
    2026-10-5, which breaks the order of the names."""
    try:
        collected_at = parse_collection_name(collection_name)
    except ValueError:
        return None
    if collected_at.strftime(COLLECTION_NAME_FORMAT) != collection_name:
        return None
    return collected_at


class Rejection(NamedTuple):
    """A raw file, or an entry of it, refused at the import, with the reason."""

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
    """The raw files of items read, the rejections, and how many pages were opened."""

    files: list[RawFile]
    rejections: list[Rejection]
    # The pages opened, readable or not.
    read_count: int


def join_readings(readings: list[RawReading]) -> RawReading:
    """Join several readings of raw files into one."""
    return RawReading(
        [raw_file for reading in readings for raw_file in reading.files],
        [rejection for reading in readings for rejection in reading.rejections],
        sum(reading.read_count for reading in readings),
    )


class TrendFile(NamedTuple):
    """A raw file of trends of GH Archive read: the file to register, and its rows, which are not
    items."""

    raw_file: RawFile
    rows: list[TrendRow]


class TrendReading(NamedTuple):
    """The files of trends read, the rejections, and how many files were opened."""

    files: list[TrendFile]
    rejections: list[Rejection]
    # The files of trends opened, readable or not.
    read_count: int


def join_trend_readings(readings: list[TrendReading]) -> TrendReading:
    """Join several readings of trend files into one."""
    return TrendReading(
        [trend_file for reading in readings for trend_file in reading.files],
        [rejection for reading in readings for rejection in reading.rejections],
        sum(reading.read_count for reading in readings),
    )
