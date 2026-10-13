"""Normalize the items read (docs/specs-collecte.md, step 3).

No input or output here: the items come from raw_items.py; the base removes the duplicates at
the import (import_items.py).
"""

from datetime import UTC
from urllib.parse import urlsplit, urlunsplit

from k_b.items import Item

TRACKING_PARAMETER_PREFIX = "utm_"
DATE_FIELDS = ("published_at", "revised_at", "saved_at", "collected_at")


def normalize_item(item: Item) -> Item:
    """The same item, with its URL without tracking parameters and its dates in UTC, those of
    its highlights too."""
    fields = item.model_dump()
    if item.url is not None:
        fields["url"] = remove_tracking_parameters(item.url)
    for field in DATE_FIELDS:
        if fields[field] is not None:
            fields[field] = fields[field].astimezone(UTC)
    for highlight in fields["highlights"]:
        highlight["highlighted_at"] = highlight["highlighted_at"].astimezone(UTC)
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
