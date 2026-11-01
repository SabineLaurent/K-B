"""The facts of a candidate read on GitHub and its cautions (docs/tendances.md, "Fiche légère"):
pure code, without any reading."""

from datetime import UTC, datetime, timedelta

import pytest

from k_b.ai_api.repository_cards import (
    CandidateCounts,
    RepositoryCard,
    to_facts,
)
from k_b.core.config import TREND_RECENT_REPOSITORY_DAYS

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def make_card(license="MIT", created_at=datetime(2018, 12, 8, tzinfo=UTC)):
    return RepositoryCard(
        repository_id=7,
        license=license,
        created_at=created_at,
        language="Python",
        topics=("api", "python"),
        stars_total=104_367,
        description="FastAPI framework, high performance, easy to learn",
    )


def test_the_facts_are_the_card_and_no_caution_for_an_old_licensed_repository():
    facts = to_facts(make_card(), NOW)

    assert facts.license == "MIT"
    assert facts.created_at == datetime(2018, 12, 8, tzinfo=UTC)
    assert facts.language == "Python"
    assert facts.topics == ("api", "python")
    assert facts.stars_total == 104_367
    assert facts.cautions == ()


@pytest.mark.parametrize(
    ("age", "cautions"),
    [
        (timedelta(days=TREND_RECENT_REPOSITORY_DAYS), ()),
        (
            timedelta(days=TREND_RECENT_REPOSITORY_DAYS) - timedelta(seconds=1),
            ("created_recently",),
        ),
        (timedelta(0), ("created_recently",)),
    ],
    ids=["seven-days-exactly", "a-second-less", "created-now"],
)
def test_created_recently_is_strictly_less_than_seven_days_before_the_request(
    age, cautions
):
    assert TREND_RECENT_REPOSITORY_DAYS == 7
    assert to_facts(make_card(created_at=NOW - age), NOW).cautions == cautions


def test_without_a_license_recognized_both_cautions_come_in_their_order():
    facts = to_facts(make_card(license=None, created_at=NOW), NOW)

    assert facts.license is None
    assert facts.cautions == ("created_recently", "no_license")


def test_the_counts_hold_every_reason_and_their_sum():
    counts = CandidateCounts.count(selected=5, dropped=["moved", "moved", "forbidden"])

    assert counts.selected == 5
    assert counts.read == 2
    assert counts.dropped == {
        "not_found": 0,
        "unavailable_for_legal_reasons": 0,
        "moved": 2,
        "id_mismatch": 0,
        "forbidden": 1,
    }
