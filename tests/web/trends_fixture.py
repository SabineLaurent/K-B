"""The trends for the site: the answer of GET /trends of the data API on its test base
(tests/fixtures/items_database.sql), its latest window, 2026-10-10, and its five repositories."""

import copy
import json
from pathlib import Path

TRENDS_PATH = Path(__file__).parents[1] / "fixtures" / "web_trends.json"
TRENDS = json.loads(TRENDS_PATH.read_text(encoding="utf-8"))
# The older window of the test base, its two repositories tied on stars and forks.
OLDER_WINDOW_END = "2026-10-09"


def make_trends(count=None, **changes):
    """A copy of the trends of the fixture; count rows, those of the fixture in turn, each with a
    repository of its own."""
    trends = copy.deepcopy(TRENDS)
    if count is not None:
        rows = trends["trends"]
        trends["trends"] = [
            {
                **rows[index % len(rows)],
                "repository_id": 1000 + index,
                "repository_name": f"owner-{index}/repository-{index}",
            }
            for index in range(count)
        ]
    return {**trends, **changes}
