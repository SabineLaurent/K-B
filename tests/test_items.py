import re
import typing
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from k_b.arxiv_papers import Paper
from k_b.cisa_kev import Vulnerability
from k_b.github_advisories import Advisory
from k_b.github_most_starred import StarredRepository
from k_b.github_releases import Release
from k_b.items import (
    Item,
    SourceCode,
    convert_advisory,
    convert_paper,
    convert_release,
    convert_starred_repository,
    convert_vulnerability,
)

SEED_SOURCES = Path(__file__).parent.parent / "src" / "k_b" / "database" / "seed_sources.sql"
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = "automation/arxiv/2026-10-05T093000Z.xml"
PUBLISHED_AT = datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)


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


def test_a_paper_keeps_its_id_without_version_and_its_revision_date():
    paper = Paper(
        arxiv_id="2509.12345",
        version=2,
        title="A paper",
        summary="What it says.",
        authors=("Ada Lovelace", "Alan Turing"),
        published_at=datetime(2025, 9, 15, 17, 0, tzinfo=UTC),
        updated_at=datetime(2025, 9, 20, 12, 0, tzinfo=UTC),
        url="https://arxiv.org/abs/2509.12345",
    )

    item = convert_paper(paper, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "arxiv"
    assert item.source_item_id == "2509.12345"
    assert item.title == "A paper"
    assert item.url == "https://arxiv.org/abs/2509.12345"
    assert item.authors == ("Ada Lovelace", "Alan Turing")
    assert item.published_at == datetime(2025, 9, 15, 17, 0, tzinfo=UTC)
    assert item.revised_at == datetime(2025, 9, 20, 12, 0, tzinfo=UTC)
    assert item.summary == "What it says."
    assert item.collected_at == COLLECTED_AT
    assert item.raw_file_path == RAW_FILE_PATH


def test_a_vulnerability_points_to_its_nvd_page_and_is_dated_at_midnight_utc():
    vulnerability = Vulnerability(
        cve_id="CVE-2026-86950",
        vendor_project="Apple",
        product="Multiple Products",
        vulnerability_name="Apple Multiple Products Out-of-Bounds Write Vulnerability",
        date_added=date(2026, 9, 29),
        short_description="An out-of-bounds write.",
    )

    item = convert_vulnerability(vulnerability, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "cisa_kev"
    assert item.source_item_id == "CVE-2026-86950"
    assert item.title == "Apple Multiple Products Out-of-Bounds Write Vulnerability"
    assert item.url == "https://nvd.nist.gov/vuln/detail/CVE-2026-86950"
    assert item.published_at == datetime(2026, 9, 29, tzinfo=UTC)
    assert item.summary == "An out-of-bounds write."
    assert item.cve == "CVE-2026-86950"
    assert item.is_vulnerability is True


def test_a_release_is_identified_by_its_release_id():
    release = Release(
        repository="anthropics/claude-code",
        release_id=401174143,
        tag_name="v2.1.287",
        name=None,
        url="https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
        published_at=PUBLISHED_AT,
        is_prerelease=False,
        body="## What's changed",
    )

    item = convert_release(release, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "github"
    assert item.source_item_id == "401174143"
    assert item.title == "anthropics/claude-code v2.1.287"
    assert item.url == "https://github.com/anthropics/claude-code/releases/tag/v2.1.287"
    assert item.published_at == PUBLISHED_AT
    assert item.summary == "## What's changed"
    assert item.repository_name is None


def test_a_named_release_is_titled_by_its_name():
    release = Release(
        repository="langchain-ai/langgraph",
        release_id=1,
        tag_name="0.6.0",
        name="LangGraph 0.6",
        url="https://github.com/langchain-ai/langgraph/releases/tag/0.6.0",
        published_at=PUBLISHED_AT,
        is_prerelease=False,
        body=None,
    )

    item = convert_release(release, COLLECTED_AT, RAW_FILE_PATH)

    assert item.title == "langchain-ai/langgraph LangGraph 0.6"
    assert item.summary is None


def test_an_advisory_keeps_its_cve():
    advisory = Advisory(
        ghsa_id="GHSA-fjqc-hq36-qh5p",
        cve_id="CVE-2026-48775",
        summary="Path traversal in langchain",
        severity="high",
        url="https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
        published_at=PUBLISHED_AT,
        reviewed_at=COLLECTED_AT,
        packages=("langchain",),
    )

    item = convert_advisory(advisory, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "github"
    assert item.source_item_id == "GHSA-fjqc-hq36-qh5p"
    assert item.title == "Path traversal in langchain"
    assert item.url == "https://github.com/advisories/GHSA-fjqc-hq36-qh5p"
    assert item.published_at == PUBLISHED_AT
    assert item.cve == "CVE-2026-48775"
    assert item.is_vulnerability is True


def test_an_advisory_without_cve_is_still_a_vulnerability():
    advisory = Advisory(
        ghsa_id="GHSA-fjqc-hq36-qh5p",
        cve_id=None,
        summary="Path traversal in langchain",
        severity="high",
        url="https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
        published_at=PUBLISHED_AT,
        reviewed_at=COLLECTED_AT,
        packages=("langchain",),
    )

    item = convert_advisory(advisory, COLLECTED_AT, RAW_FILE_PATH)

    assert item.cve is None
    assert item.is_vulnerability is True


def test_a_starred_repository_is_a_repository_without_publication_date():
    repository = StarredRepository(
        rank=1,
        full_name="codecrafters-io/build-your-own-x",
        url="https://github.com/codecrafters-io/build-your-own-x",
        description="Master programming by recreating your favorite technologies",
        stars=400000,
        topics=(),
        created_at=PUBLISHED_AT,
    )

    item = convert_starred_repository(repository, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "github"
    assert item.source_item_id == "codecrafters-io/build-your-own-x"
    assert item.title == "codecrafters-io/build-your-own-x"
    assert item.url == "https://github.com/codecrafters-io/build-your-own-x"
    assert item.published_at is None
    assert item.summary == "Master programming by recreating your favorite technologies"
    assert item.repository_name == "codecrafters-io/build-your-own-x"
