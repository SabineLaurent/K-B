"""A page of GET /items for the feed: the answer of the data API on its test base
(tests/fixtures/items_database.sql) for the five kinds of the feed, its 14 items."""

import copy
import json
from itertools import cycle, islice
from pathlib import Path

ITEMS_PAGE_PATH = Path(__file__).parents[1] / "fixtures" / "web_items_page.json"
ITEMS_PAGE = json.loads(ITEMS_PAGE_PATH.read_text(encoding="utf-8"))


def make_page(count, total=None):
    """A page of count items, those of the fixture in turn, each with an id of its own; total
    defaults to count."""
    items = [
        {**copy.deepcopy(item), "id": 1000 + index}
        for index, item in enumerate(islice(cycle(ITEMS_PAGE["items"]), count))
    ]
    return {
        "items": items,
        "next_offset": None,
        "total": count if total is None else total,
    }
