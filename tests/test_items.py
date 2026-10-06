import re
import typing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from k_b.items import Item, SourceCode

SEED_SOURCES = (
    Path(__file__).parent.parent / "src" / "k_b" / "database" / "seed_sources.sql"
)
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = "automation/arxiv/2026-10-05T093000Z.xml"


def item_fields(**changes):
    fields = {
        "source_code": "arxiv",
        "source_item_id": "2509.12345",
        "title": "A paper",
        "url": "https://arxiv.org/abs/2509.12345",
        "collected_at": COLLECTED_AT,
        "raw_file_path": RAW_FILE_PATH,
    }
    fields.update(changes)
    return fields


def test_the_source_codes_are_those_of_the_database():
    seeded_codes = re.findall(r"\('(\w+)',", SEED_SOURCES.read_text())

    assert set(typing.get_args(SourceCode)) == set(seeded_codes)


def test_an_item_keeps_an_absence_as_an_absence():
    item = Item(**item_fields())

    assert item.authors == ()
    assert item.published_at is None
    assert item.revised_at is None
    assert item.saved_at is None
    assert item.summary is None
    assert item.cve is None
    assert item.is_vulnerability is False
    assert item.repository_name is None


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "rss"},
        {"source_item_id": ""},
        {"title": ""},
        {"url": "http://arxiv.org/abs/2509.12345"},
        {"url": "arxiv.org/abs/2509.12345"},
        {"published_at": datetime(2026, 10, 1, 18, 0, 22)},
        {"published_at": "2026-10-01T18:00:22Z"},
        {"collected_at": datetime(2026, 10, 5, 9, 30)},
        {"cve": "CVE-26-1"},
        {"cve": "CVE-2026-48775", "is_vulnerability": False},
        {"repository_name": "no-slash"},
        {"stars": 3},
    ],
)
def test_an_invalid_item_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**item_fields(**changes))


def test_an_item_cannot_be_changed():
    item = Item(**item_fields())

    with pytest.raises(ValidationError):
        item.title = "Another title"
