"""The detail of an item for the site: the answers of GET /items/{item_id} of the data API on its
test base (tests/fixtures/items_database.sql), one or more by kind of the feed."""

import copy
import json
from pathlib import Path

ITEM_DETAILS_PATH = Path(__file__).parents[1] / "fixtures" / "web_item_details.json"
ITEM_DETAILS = {
    int(item_id): detail
    for item_id, detail in json.loads(
        ITEM_DETAILS_PATH.read_text(encoding="utf-8")
    ).items()
}
# The ids of the fixture, by what each one shows.
PAPER = 1
VULNERABILITY = 3
WITHDRAWN_VULNERABILITY = 5
RELEASE = 6
ADVISORY_IN_CATALOG = 9
ADVISORY_WITHOUT_CVE = 10
ADVISORY_ABSENT_FROM_CATALOG = 17
NEWSLETTER_ARTICLE = 12
# The Zotero entry and the clip of the test base, which the site never shows.
ZOTERO_ENTRY = 16
CLIP = 18


def make_detail(item_id, **changes):
    """The detail of item_id in the fixture, a copy, its fields changed by changes."""
    return {**copy.deepcopy(ITEM_DETAILS[item_id]), **changes}
