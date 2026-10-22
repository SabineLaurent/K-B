"""Normalize the items read (docs/specs-collecte.md, step 3).

No input or output here: the items come from etl/transform.py, which calls normalize_item on each
item its reading keeps (read_raw_items); the base removes the duplicates at the import
(etl/load.py).
"""

from urllib.parse import urlsplit, urlunsplit

from k_b.items import Item

TRACKING_PARAMETER_PREFIX = "utm_"


def normalize_item(item: Item) -> Item:
    """The same item, with its URL without tracking parameters. Its dates, those of its
    highlights too, are in UTC already (UtcDatetime, items.py)."""
    fields = item.model_dump()
    if item.url is not None:
        fields["url"] = remove_tracking_parameters(item.url)
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
