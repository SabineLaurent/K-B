"""Merge the items of every raw file into one set (docs/specs-collecte.md, step 3).

No input or output here: the items come from raw_items.py, the discards are written by the import.
"""

from datetime import UTC
from typing import Literal, NamedTuple
from urllib.parse import urlsplit, urlunsplit

from k_b.items import Item

DiscardRule = Literal["same_source_id", "same_url", "same_cve", "arxiv_revision"]

TRACKING_PARAMETER_PREFIX = "utm_"
DATE_FIELDS = ("published_at", "revised_at", "saved_at", "collected_at")


class Discard(NamedTuple):
    rule: DiscardRule
    item: Item
    # The URL of the item kept in its place, to find it in the base.
    kept_url: str


class MergeResult(NamedTuple):
    items: list[Item]
    discards: list[Discard]


def merge_items(items: list[Item]) -> MergeResult:
    """One item per source identifier, URL, and CVE within a source; each removal is traced.

    The items come in collection order: the first one seen is kept, as its collection brought
    it, except for a newer arXiv revision, which takes the place of the paper kept.
    """
    kept: list[Item] = []
    position_by_source_id: dict[tuple[str, str], int] = {}
    position_by_url: dict[str, int] = {}
    # By source: the same CVE from CISA and from GitHub gives two items, linked by their CVE.
    position_by_source_cve: dict[tuple[str, str], int] = {}
    discards: list[Discard] = []

    for item in map(normalize_item, items):
        position = position_by_source_id.get((item.source_code, item.source_item_id))
        if position is not None:
            previous = kept[position]
            if is_newer_revision(item, previous):
                kept[position] = item
                position_by_url[item.url] = position
                discards.append(Discard("arxiv_revision", previous, item.url))
            else:
                discards.append(Discard("same_source_id", item, previous.url))
            continue
        if item.url in position_by_url:
            discards.append(
                Discard("same_url", item, kept[position_by_url[item.url]].url)
            )
            continue
        source_cve = (item.source_code, item.cve) if item.cve is not None else None
        if source_cve in position_by_source_cve:
            discards.append(
                Discard("same_cve", item, kept[position_by_source_cve[source_cve]].url)
            )
            continue
        position = len(kept)
        kept.append(item)
        position_by_source_id[(item.source_code, item.source_item_id)] = position
        position_by_url[item.url] = position
        if source_cve is not None:
            position_by_source_cve[source_cve] = position
    return MergeResult(kept, discards)


def normalize_item(item: Item) -> Item:
    """The same item, with its URL without tracking parameters and its dates in UTC."""
    fields = item.model_dump()
    fields["url"] = remove_tracking_parameters(item.url)
    for field in DATE_FIELDS:
        if fields[field] is not None:
            fields[field] = fields[field].astimezone(UTC)
    # Validated again: the normalized item must pass the same checks as the item read.
    return Item(**fields)


def remove_tracking_parameters(url: str) -> str:
    """Remove the utm_* parameters; the others are kept as written, in their order."""
    parts = urlsplit(url)
    query = "&".join(
        parameter
        for parameter in parts.query.split("&")
        if parameter and not parameter.startswith(TRACKING_PARAMETER_PREFIX)
    )
    return urlunsplit(parts._replace(query=query))


def is_newer_revision(item: Item, previous: Item) -> bool:
    return (
        item.source_code == "arxiv"
        and item.revised_at is not None
        and previous.revised_at is not None
        and item.revised_at > previous.revised_at
    )
