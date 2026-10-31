"""The sheet of a candidate read on GitHub, its facts and their cautions, and the counts of the
candidates (docs/tendances.md, "Fiche légère"): pure code, without any reading."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Self, get_args

from k_b.core.config import TREND_RECENT_REPOSITORY_DAYS

type Caution = Literal["created_recently", "no_license"]
# Why a candidate is left out: its name may now name another repository (docs/tendances.md).
type DropReason = Literal[
    "not_found", "unavailable_for_legal_reasons", "moved", "id_mismatch", "forbidden"
]
DROP_REASONS: tuple[DropReason, ...] = get_args(DropReason.__value__)


@dataclass(frozen=True)
class RepositoryCard:
    """What GitHub answers about a repository, checked by its schema."""

    repository_id: int
    # An SPDX identifier; None when GitHub recognizes no license.
    license: str | None
    created_at: datetime
    language: str | None
    topics: tuple[str, ...]
    stars_total: int


@dataclass(frozen=True)
class RepositoryFacts:
    license: str | None
    created_at: datetime
    language: str | None
    topics: tuple[str, ...]
    stars_total: int
    cautions: tuple[Caution, ...]


@dataclass(frozen=True)
class CandidateCounts:
    selected: int
    read: int
    dropped: Mapping[DropReason, int]

    @classmethod
    def count(cls, selected: int, dropped: Iterable[DropReason]) -> Self:
        """The counts of the candidates selected, every reason given, at 0 when none."""
        by_reason = Counter(dropped)
        return cls(
            selected=selected,
            read=selected - by_reason.total(),
            dropped={reason: by_reason[reason] for reason in DROP_REASONS},
        )


def to_facts(card: RepositoryCard, now: datetime) -> RepositoryFacts:
    return RepositoryFacts(
        license=card.license,
        created_at=card.created_at,
        language=card.language,
        topics=card.topics,
        stars_total=card.stars_total,
        cautions=find_cautions(card, now),
    )


def find_cautions(card: RepositoryCard, now: datetime) -> tuple[Caution, ...]:
    """created_recently strictly within TREND_RECENT_REPOSITORY_DAYS before now, then no_license."""
    cautions: list[Caution] = []
    if card.created_at > now - timedelta(days=TREND_RECENT_REPOSITORY_DAYS):
        cautions.append("created_recently")
    if card.license is None:
        cautions.append("no_license")
    return tuple(cautions)
