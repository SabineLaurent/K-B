import json
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.github_advisories import Advisory, read_advisories

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "github_advisories_extract.json").read_bytes()


def advisory_payload(**changes):
    payload = json.loads(RECORDED_RESPONSE)[0]
    payload.update(changes)
    return json.dumps([payload]).encode()


def test_a_recorded_response_gives_one_advisory_per_entry_newest_first():
    advisories = read_advisories(RECORDED_RESPONSE)

    assert [advisory.ghsa_id for advisory in advisories] == [
        "GHSA-fjqc-hq36-qh5p",
        "GHSA-gr75-jv2w-4656",
        "GHSA-3644-q5cj-c5c7",
    ]
    newest = advisories[0]
    assert newest.cve_id == "CVE-2026-48775"
    assert newest.severity == "medium"
    assert newest.url == "https://github.com/advisories/GHSA-fjqc-hq36-qh5p"
    assert newest.published_at == datetime(2026, 6, 25, 18, 25, 42, tzinfo=UTC)
    assert newest.reviewed_at == datetime(2026, 6, 25, 18, 25, 42, tzinfo=UTC)
    assert newest.summary


def test_each_affected_package_is_kept_once_in_its_order():
    assert read_advisories(RECORDED_RESPONSE)[2].packages == (
        "langsmith",
        "langchain-classic",
        "langchain",
    )


def test_the_credited_people_are_not_kept():
    assert not any("credit" in field.name for field in fields(Advisory))


def test_an_advisory_without_cve_keeps_an_empty_cve():
    assert read_advisories(advisory_payload(cve_id=None))[0].cve_id is None


def test_a_response_that_is_not_a_list_is_refused():
    with pytest.raises(ValueError, match="list"):
        read_advisories(b'{"message": "Validation Failed"}')


@pytest.mark.parametrize(
    "changes",
    [
        {"ghsa_id": "GHSA-../../etc"},
        {"cve_id": "CVE-26-1"},
        {"severity": "urgent"},
        {"summary": None},
        {"html_url": "https://evil.example.com/advisories/GHSA-fjqc-hq36-qh5p"},
        {"published_at": "2026-06-25T18:25:42"},
        {"github_reviewed_at": None},
        {"vulnerabilities": [{"package": {"name": 42}}]},
    ],
)
def test_an_invalid_advisory_is_refused_with_its_position(changes):
    with pytest.raises(ValueError, match="advisory 0"):
        read_advisories(advisory_payload(**changes))
