"""The trend report: the period after the previous report, its windows read by the data API under
the deadline, the repositories that meet a criterion, the sheet of each candidate read on GitHub,
then the choice of the model among those read (docs/tendances.md); nothing is written nor logged
here, each step is a span without any repository."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx2

from k_b.ai_api.connectors.data_api_client import DataApiError, read_trend_window
from k_b.ai_api.connectors.github_client import (
    GithubError,
    GithubReading,
    read_repository,
)
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.repository_cards import (
    CandidateCounts,
    DropReason,
    RepositoryCard,
    RepositoryFacts,
    to_facts,
)
from k_b.ai_api.stages.trend_selection import (
    Selection,
    SelectionCandidate,
    SelectionFailure,
    select_trends,
)
from k_b.ai_api.tracing import TRACING_OFF, Tracing
from k_b.ai_api.trajectories import (
    StarWindow,
    Trajectory,
    find_trajectories,
    select_candidates,
)
from k_b.core.config import (
    GH_ARCHIVE_MAX_CATCH_UP_WINDOWS,
    TREND_DURABLE_LOOKBACK_WINDOWS,
    TREND_FIRST_REPORT_WINDOWS,
    DigestSubject,
)
from k_b.items import is_repository_name


@dataclass(frozen=True)
class TrendPeriod:
    first_report: bool
    # The oldest first, the missing ones included.
    windows: tuple[date, ...]
    missing_windows: tuple[date, ...]
    windows_capped: bool
    new_evaluated: bool
    # None when the base has no window.
    latest_window: date | None


@dataclass(frozen=True)
class Trends:
    """The trajectories of the period, before GitHub."""

    period: TrendPeriod
    # Every repository of a top of the period whose name can go into a path, meeting a criterion
    # or not, by best rank then repository_id.
    trajectories: tuple[Trajectory, ...]
    # Meeting a criterion, left out: their name, `.` or with `..`, would go into a path.
    repositories_dropped: int


@dataclass(frozen=True)
class CardReading:
    """The sheets of the candidates read on GitHub."""

    facts: Mapping[int, RepositoryFacts]
    # Raw, by repository_id: cleaned when the message of the choice is built, never in facts.
    descriptions: Mapping[int, str | None]
    dropped_ids: frozenset[int]
    counts: CandidateCounts


@dataclass(frozen=True)
class TrendReport:
    period: TrendPeriod
    # Meeting a criterion, but the candidates GitHub left out.
    repositories: tuple[Trajectory, ...]
    repositories_dropped: int
    # By repository_id, for the candidates read only.
    facts: Mapping[int, RepositoryFacts]
    candidates: CandidateCounts
    # None when no candidate is read: no call to the model.
    choice: Selection | SelectionFailure | None


@dataclass(frozen=True)
class PeriodReading:
    """The windows found for a report, and the days each criterion reads them on."""

    latest_window: date | None
    period: list[date]
    windows_capped: bool
    lookback: list[date]
    # None for the first report.
    previous: list[date] | None
    windows: Mapping[date, StarWindow]
    requests: int


def build_trend_report(
    data_api_client: httpx2.Client,
    github_client: httpx2.Client,
    llm_client: httpx2.Client,
    llm_settings: LlmSettings,
    subjects: Sequence[DigestSubject],
    after: date | None,
    previous_first_window: date | None,
    deadline: Deadline,
    now: datetime,
    *,
    tracing: Tracing = TRACING_OFF,
) -> TrendReport:
    """The repositories that meet a criterion over the windows after `after`, the last window of
    the previous report, None for the first, with the sheet of each candidate read on GitHub at
    `now`, the time of the request, and the choice of the model among those read; a failure of a
    reading raises its DataApiError or its GithubError, a failure of the choice is in the
    report."""
    with tracing.step("read_trend_windows") as step:
        try:
            reading = read_period(
                data_api_client, after, previous_first_window, deadline
            )
        except DataApiError as error:
            step.fail(error.state)
            raise
        trends = find_trends(after is None, reading)
        step.set(
            {
                "k_b.windows.period": len(trends.period.windows),
                "k_b.windows.read": reading.requests,
                "k_b.windows.missing": len(trends.period.missing_windows),
                "k_b.windows.capped": trends.period.windows_capped,
                "k_b.repositories.reported": count_meeting_a_criterion(
                    trends.trajectories
                ),
                "k_b.repositories.dropped": trends.repositories_dropped,
            }
        )
    candidates = select_candidates(trends.trajectories)
    cards = read_repository_cards(
        github_client, candidates, deadline, now, tracing=tracing
    )
    read = [
        SelectionCandidate(
            candidate,
            cards.facts[candidate.repository_id],
            cards.descriptions[candidate.repository_id],
        )
        for candidate in candidates
        if candidate.repository_id in cards.facts
    ]
    choice = (
        select_trends(
            llm_client,
            llm_settings,
            read,
            subjects,
            deadline,
            tracing=tracing,
        )
        if read
        else None
    )
    return to_trend_report(trends, cards, choice)


def read_period(
    http_client: httpx2.Client,
    after: date | None,
    previous_first_window: date | None,
    deadline: Deadline,
) -> PeriodReading:
    """The windows of the period, of the lookback of durable and of the previous report, each read
    once, one after the other; the latest alone when no window is after `after`."""
    latest = read_trend_window(http_client, None, deadline=deadline)
    if latest is None:
        return PeriodReading(None, [], False, [], None, {}, 1)
    period, windows_capped = list_period(after, latest.window_end)
    if not period:
        return PeriodReading(
            latest.window_end, [], False, [], None, {latest.window_end: latest}, 1
        )
    lookback = list_days_before(period[0], TREND_DURABLE_LOOKBACK_WINDOWS)
    previous = (
        None
        if after is None or previous_first_window is None
        else list_days(previous_first_window, after)
    )
    to_read = sorted({*period, *lookback, *(previous or ())} - {latest.window_end})
    windows = {latest.window_end: latest}
    for end in to_read:
        window = read_trend_window(http_client, end, deadline=deadline)
        if window is not None:
            windows[end] = window
    return PeriodReading(
        latest_window=latest.window_end,
        period=period,
        windows_capped=windows_capped,
        lookback=lookback,
        previous=previous,
        windows=windows,
        requests=1 + len(to_read),
    )


def list_period(after: date | None, latest: date) -> tuple[list[date], bool]:
    """The windows of the report, the oldest first, GH_ARCHIVE_MAX_CATCH_UP_WINDOWS at most, and
    whether older ones were left out; empty when no window is after `after`."""
    if after is None:
        return [
            *list_days_before(latest, TREND_FIRST_REPORT_WINDOWS - 1),
            latest,
        ], False
    # Compared before any addition: the day after `after` may not exist.
    if after >= latest:
        return [], False
    capped_start = latest - timedelta(days=GH_ARCHIVE_MAX_CATCH_UP_WINDOWS - 1)
    start = after + timedelta(days=1)
    return list_days(max(start, capped_start), latest), start < capped_start


def list_days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def list_days_before(day: date, count: int) -> list[date]:
    """The count days before day, the oldest first."""
    return [day - timedelta(days=count - offset) for offset in range(count)]


def find_trends(first_report: bool, reading: PeriodReading) -> Trends:
    """The trajectories of the period; new is not evaluated when every window of the previous
    report is missing."""
    previous = reading.previous
    if previous is not None and not any(end in reading.windows for end in previous):
        previous = None
    trajectories = find_trajectories(
        reading.period, reading.windows, reading.lookback, previous
    )
    named = tuple(
        trajectory
        for trajectory in trajectories
        if is_repository_name(trajectory.repository_name)
    )
    return Trends(
        period=TrendPeriod(
            first_report=first_report,
            windows=tuple(reading.period),
            missing_windows=tuple(
                end for end in reading.period if end not in reading.windows
            ),
            windows_capped=reading.windows_capped,
            new_evaluated=previous is not None,
            latest_window=reading.latest_window,
        ),
        trajectories=named,
        repositories_dropped=count_meeting_a_criterion(trajectories)
        - count_meeting_a_criterion(named),
    )


def count_meeting_a_criterion(trajectories: Sequence[Trajectory]) -> int:
    return sum(1 for trajectory in trajectories if trajectory.criteria)


def read_repository_cards(
    http_client: httpx2.Client,
    candidates: Sequence[Trajectory],
    deadline: Deadline,
    now: datetime,
    *,
    tracing: Tracing = TRACING_OFF,
) -> CardReading:
    """The sheet of each candidate, one request after the other; none without a candidate. A
    span of counts and states, never a repository."""
    reading = GithubReading(http_client, deadline, now)
    facts: dict[int, RepositoryFacts] = {}
    descriptions: dict[int, str | None] = {}
    dropped: dict[int, DropReason] = {}
    with tracing.step("read_repository_cards") as step:
        try:
            for candidate in candidates:
                card = read_repository(
                    reading, candidate.repository_id, candidate.repository_name
                )
                if isinstance(card, RepositoryCard):
                    facts[candidate.repository_id] = to_facts(card, now)
                    descriptions[candidate.repository_id] = card.description
                else:
                    dropped[candidate.repository_id] = card
        except GithubError as error:
            step.fail(error.state)
            step.set({"k_b.github.requests": reading.requests})
            raise
        counts = CandidateCounts.count(len(candidates), dropped.values())
        step.set(
            {
                "k_b.candidates.selected": counts.selected,
                "k_b.candidates.read": counts.read,
                **{
                    f"k_b.candidates.dropped.{reason}": count
                    for reason, count in counts.dropped.items()
                },
                "k_b.github.requests": reading.requests,
            }
        )
    return CardReading(facts, descriptions, frozenset(dropped), counts)


def to_trend_report(
    trends: Trends, cards: CardReading, choice: Selection | SelectionFailure | None
) -> TrendReport:
    """The repositories that meet a criterion, but the candidates GitHub left out: their name may
    now name another repository."""
    return TrendReport(
        period=trends.period,
        repositories=tuple(
            trajectory
            for trajectory in trends.trajectories
            if trajectory.criteria and trajectory.repository_id not in cards.dropped_ids
        ),
        repositories_dropped=trends.repositories_dropped,
        facts=cards.facts,
        candidates=cards.counts,
        choice=choice,
    )
