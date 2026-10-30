"""The ranks by stars of the GH Archive windows, the trajectory of each repository over a period and
the criteria it meets (docs/tendances.md, "Rang et critères"): pure code, without any reading."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from k_b.core.config import (
    GH_ARCHIVE_TOP_SIZE,
    GH_ARCHIVE_WINDOW_DAYS,
    TREND_ACCELERATION_MIN_RANKS,
    TREND_DURABLE_MIN_WINDOWS,
    TREND_MAX_CANDIDATES,
)
from k_b.items import Criterion, WindowState


@dataclass(frozen=True)
class RepositoryStars:
    """A repository of a window and the stars it gained there."""

    repository_id: int
    repository_name: str
    stars_gained: int


@dataclass(frozen=True)
class StarWindow:
    """The repositories of a window, those of its top by stars and those of its top by forks."""

    window_end: date
    rows: tuple[RepositoryStars, ...]


@dataclass(frozen=True)
class TrajectoryPoint:
    window_end: date
    state: WindowState
    # In the top only.
    rank: int | None
    stars_gained: int | None


@dataclass(frozen=True)
class Trajectory:
    repository_id: int
    repository_name: str
    # One per window of the period, the oldest first.
    points: tuple[TrajectoryPoint, ...]
    criteria: tuple[Criterion, ...]
    best_rank: int


def rank_by_stars(window: StarWindow) -> dict[int, int]:
    """The rank of each repository of the top by stars, by (stars_gained desc, repository_id asc),
    as star_rank at the collection; a repository without a star gained is in no top."""
    ranked = sorted(
        (row for row in window.rows if row.stars_gained > 0),
        key=lambda row: (-row.stars_gained, row.repository_id),
    )
    return {
        row.repository_id: rank
        for rank, row in enumerate(ranked[:GH_ARCHIVE_TOP_SIZE], start=1)
    }


def find_trajectories(
    period: Sequence[date],
    windows: Mapping[date, StarWindow],
    lookback: Sequence[date],
    previous: Sequence[date] | None,
) -> tuple[Trajectory, ...]:
    """The trajectory of each repository in the top of a window of the period, by best rank then
    repository_id; windows holds the windows found, previous those of the previous report, None
    when new is not evaluated."""
    ranks = {end: rank_by_stars(window) for end, window in windows.items()}
    names = name_repositories(windows[end] for end in period if end in windows)
    period_top = {
        repository_id for end in period for repository_id in ranks.get(end, {})
    }
    previous_top = (
        None
        if previous is None
        else {repository_id for end in previous for repository_id in ranks.get(end, {})}
    )
    trajectories = []
    for repository_id in period_top:
        points = tuple(
            to_point(end, windows.get(end), ranks.get(end, {}), repository_id)
            for end in period
        )
        top_ends = [
            end for end in (*lookback, *period) if repository_id in ranks.get(end, {})
        ]
        trajectories.append(
            Trajectory(
                repository_id=repository_id,
                repository_name=names[repository_id],
                points=points,
                criteria=find_criteria(
                    points,
                    top_ends,
                    None if previous_top is None else repository_id in previous_top,
                ),
                best_rank=min(point.rank for point in points if point.rank is not None),
            )
        )
    return tuple(
        sorted(
            trajectories,
            key=lambda trajectory: (trajectory.best_rank, trajectory.repository_id),
        )
    )


def name_repositories(windows: Iterable[StarWindow]) -> dict[int, str]:
    """The name of each repository in the most recent of the windows, given the oldest first."""
    return {
        row.repository_id: row.repository_name
        for window in windows
        for row in window.rows
    }


def to_point(
    window_end: date,
    window: StarWindow | None,
    ranks: Mapping[int, int],
    repository_id: int,
) -> TrajectoryPoint:
    if window is None:
        return TrajectoryPoint(window_end, "missing", None, None)
    rank = ranks.get(repository_id)
    if rank is None:
        return TrajectoryPoint(window_end, "out_of_top", None, None)
    stars_gained = next(
        row.stars_gained for row in window.rows if row.repository_id == repository_id
    )
    return TrajectoryPoint(window_end, "top", rank, stars_gained)


def find_criteria(
    points: Sequence[TrajectoryPoint],
    top_ends: Sequence[date],
    was_in_a_previous_top: bool | None,
) -> tuple[Criterion, ...]:
    criteria: list[Criterion] = []
    if is_durable(top_ends):
        criteria.append("durable")
    if was_in_a_previous_top is False:
        criteria.append("new")
    if is_accelerating(points):
        criteria.append("accelerating")
    return tuple(criteria)


def is_durable(top_ends: Sequence[date]) -> bool:
    """In the top of TREND_DURABLE_MIN_WINDOWS windows without a day in common: each picked as
    early as it can be, which picks the most."""
    picked: list[date] = []
    for end in sorted(top_ends):
        if not picked or (end - picked[-1]).days >= GH_ARCHIVE_WINDOW_DAYS:
            picked.append(end)
    return len(picked) >= TREND_DURABLE_MIN_WINDOWS


def is_accelerating(points: Sequence[TrajectoryPoint]) -> bool:
    """Whether each rank of the last run of windows in the top beats the one before, with
    TREND_ACCELERATION_MIN_RANKS gained at least, a missing window skipped and a window out of the
    top starting the run again."""
    # Decision A of Sabine, 2026-10-30 (docs/tendances.md).
    run: list[int] = []
    for point in points:
        if point.state == "out_of_top":
            run = []
        elif point.rank is not None:
            run.append(point.rank)
    return (
        len(run) >= 2
        and all(later < earlier for earlier, later in pairwise(run))
        and run[0] - run[-1] >= TREND_ACCELERATION_MIN_RANKS
    )


def select_candidates(trajectories: Sequence[Trajectory]) -> tuple[Trajectory, ...]:
    """TREND_MAX_CANDIDATES at most: those meeting a criterion first, then by best rank, then by
    repository_id."""
    ranked = sorted(
        trajectories,
        key=lambda trajectory: (
            not trajectory.criteria,
            trajectory.best_rank,
            trajectory.repository_id,
        ),
    )
    return tuple(ranked[:TREND_MAX_CANDIDATES])
