"""The two types of a top ranking, shared by its source and by post/top_sheets.py, and the
count its two sources read alike."""

from collections.abc import Callable
from dataclasses import dataclass

from k_b.etl.source_contract import PageRefusedError
from k_b.items import MAX_INT64, TopName


@dataclass(frozen=True)
class TopEntry:
    """A repository of a ranking, as its sheet shows it."""

    rank: int
    # owner/name, checked by the reader of its source.
    full_name: str
    # Built from the name by the source, never read in the response.
    url: str
    description: str | None
    # Its stars or its forks.
    count: int


@dataclass(frozen=True)
class Top:
    """A top ranking: the folder of its sheets under veille/tops/, the raw folder of its
    rankings, their reader, and the words of its sheet."""

    name: TopName
    folder_key: str
    read_entries: Callable[[bytes], list[TopEntry]]
    count_heading: str
    # What it ranks, after "Top <n> des".
    subject: str


def read_ranking_count(item: dict[str, object], field: str, rank: int) -> int:
    """The stars or the forks of a repository of a ranking, as the twin of its sheet holds them
    (TopProduction): an integer from 0 to MAX_INT64, the page refused otherwise."""
    count = item.get(field)
    # bool is a subclass of int in Python: refuse it explicitly.
    if not isinstance(count, int) or isinstance(count, bool):
        raise PageRefusedError(f"repository {rank}: {field} is not an integer")
    if not 0 <= count <= MAX_INT64:
        raise PageRefusedError(f"repository {rank}: {field} out of 0 to {MAX_INT64}")
    return count
