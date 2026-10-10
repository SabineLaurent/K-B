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
RAW_FILE_PATH = "automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"


def item_fields(**changes):
    """A paper, with every field its kind requires."""
    fields = {
        "source_code": "arxiv",
        "source_item_id": "2509.12345",
        "kind": "paper",
        "title": "A paper",
        "url": "https://arxiv.org/abs/2509.12345",
        "authors": ("Ada Lovelace",),
        "published_at": datetime(2025, 9, 15, 17, 0, tzinfo=UTC),
        "revised_at": datetime(2025, 9, 20, 12, 0, tzinfo=UTC),
        "summary": "What it says.",
        "collected_at": COLLECTED_AT,
        "raw_file_path": RAW_FILE_PATH,
    }
    fields.update(changes)
    return fields


def vulnerability_fields(**changes):
    """A CISA KEV vulnerability, with every field its kind requires."""
    fields = {
        "source_code": "cisa_kev",
        "source_item_id": "CVE-2026-86950",
        "kind": "vulnerability",
        "title": "Apple Multiple Products Out-of-Bounds Write Vulnerability",
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-86950",
        "published_at": datetime(2026, 9, 29, tzinfo=UTC),
        "summary": "An out-of-bounds write.",
        "collected_at": COLLECTED_AT,
        "raw_file_path": "automated_watch/cisa_kev/2026-10-05T093000Z.csv",
        "cve": "CVE-2026-86950",
        "vendor": "Apple",
        "product": "Multiple Products",
        "ransomware_use": "Unknown",
    }
    fields.update(changes)
    return fields


def test_the_source_codes_are_those_of_the_database():
    seeded_codes = re.findall(r"\('(\w+)',", SEED_SOURCES.read_text())

    assert set(typing.get_args(SourceCode)) == set(seeded_codes)


def test_an_item_keeps_an_absence_as_an_absence():
    item = Item(
        source_code="tldr",
        source_item_id="ai/2026-10-06#2",
        kind="newsletter_article",
        title="An article",
        url="https://openai.com/index/eu-text-provenance/",
        collected_at=COLLECTED_AT,
        raw_file_path="automated_watch/tldr_ai/2026-10-06T093000Z/2026-10-06.html",
    )

    assert item.authors == ()
    assert item.published_at is None
    assert item.revised_at is None
    assert item.saved_at is None
    assert item.summary is None
    assert item.cve is None
    assert item.vendor is None
    assert item.product is None
    assert item.ransomware_use is None


def test_a_paper_and_a_vulnerability_with_their_fields_are_accepted():
    assert Item(**item_fields()).kind == "paper"
    assert Item(**vulnerability_fields()).kind == "vulnerability"


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
        {"kind": "tweet"},
        {"cve": "CVE-2026-48775"},
        {"vendor": "Apple"},
        {"summary": None},
        {"authors": ()},
        {"revised_at": None},
        {"stars": 3},
    ],
)
def test_an_invalid_item_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**item_fields(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"cve": "CVE-26-1"},
        {"cve": None},
        {"vendor": None},
        {"vendor": ""},
        {"product": None},
        {"ransomware_use": None},
        {"ransomware_use": "Yes"},
        {"summary": None},
        {"published_at": None},
    ],
)
def test_an_invalid_vulnerability_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**vulnerability_fields(**changes))


def test_an_item_cannot_be_changed():
    item = Item(**item_fields())

    with pytest.raises(ValidationError):
        item.title = "Another title"
