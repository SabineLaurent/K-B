"""The ranks, the trajectories and the criteria of the trend report, in pure code
(docs/tendances.md, "Rang et critères")."""

from datetime import date, timedelta

import pytest

from k_b.ai_api.trajectories import (
    RepositoryStars,
    StarWindow,
    Trajectory,
    find_trajectories,
    rank_by_stars,
    select_candidates,
)
from k_b.core.config import GH_ARCHIVE_TOP_SIZE, TREND_MAX_CANDIDATES

DAY = date(2026, 10, 20)
# The repository each test follows; the others fill the top around it.
REPOSITORY_ID = 7_000
# A rank out of the top: the repository is in the rows of the window, entered by its forks.
OUT = "out"
# A window the base does not have.
MISSING = "missing"


def stars(repository_id, stars_gained, name=None):
    return RepositoryStars(
        repository_id=repository_id,
        repository_name=name or f"owner/repo-{repository_id}",
        stars_gained=stars_gained,
    )


def window_with_rank(window_end, rank, name=None):
    """A window where REPOSITORY_ID has this rank in the top by stars, or is just out of it."""
    position = GH_ARCHIVE_TOP_SIZE + 1 if rank == OUT else rank
    above = [stars(1_000 + k, 900 - k) for k in range(position - 1)]
    below = [
        stars(2_000 + k, 100 - k) for k in range(GH_ARCHIVE_TOP_SIZE + 1 - position)
    ]
    return StarWindow(
        window_end=window_end,
        rows=(*above, stars(REPOSITORY_ID, 500, name), *below),
    )


def days(count, start=DAY):
    return [start + timedelta(days=offset) for offset in range(count)]


def follow(ranks, start=DAY, lookback=(), previous=None):
    """The trajectory of REPOSITORY_ID over a period of one window per rank given, or None."""
    period = days(len(ranks), start)
    windows = {
        end: window_with_rank(end, rank)
        for end, rank in zip(period, ranks, strict=True)
        if rank != MISSING
    }
    for end, rank in lookback:
        windows[end] = window_with_rank(end, rank)
    lookback_ends = [end for end, _ in lookback]
    trajectories = find_trajectories(period, windows, lookback_ends, previous)
    return next(
        (t for t in trajectories if t.repository_id == REPOSITORY_ID),
        None,
    )


def test_a_tie_at_the_last_rank_broken_by_the_forks_does_not_enter():
    above = [stars(k, 1_000 - k) for k in range(1, GH_ARCHIVE_TOP_SIZE)]
    # GET /trends breaks the tie by the forks: the larger repository_id comes first.
    window = StarWindow(DAY, (stars(31, 50), *above, stars(30, 50)))

    ranks = rank_by_stars(window)

    assert ranks[30] == GH_ARCHIVE_TOP_SIZE
    assert 31 not in ranks
    assert len(ranks) == GH_ARCHIVE_TOP_SIZE


def test_a_repository_without_a_star_gained_is_in_no_top():
    window = StarWindow(DAY, (stars(1, 12), stars(2, 0)))

    assert rank_by_stars(window) == {1: 1}


def test_the_trajectory_gives_each_window_of_the_period_its_state():
    trajectory = follow([12, OUT, MISSING, 3])

    assert [(p.window_end, p.state, p.rank) for p in trajectory.points] == [
        (DAY, "top", 12),
        (DAY + timedelta(days=1), "out_of_top", None),
        (DAY + timedelta(days=2), "missing", None),
        (DAY + timedelta(days=3), "top", 3),
    ]
    # The stars of a window in the top only.
    assert [p.stars_gained for p in trajectory.points] == [500, None, None, 500]
    assert trajectory.best_rank == 3


def test_a_repository_in_no_top_of_the_period_has_no_trajectory():
    assert follow([OUT, MISSING, OUT], lookback=[(DAY - timedelta(days=3), 1)]) is None


def test_the_name_is_the_one_of_the_most_recent_window():
    period = days(2)
    windows = {
        period[0]: window_with_rank(period[0], 5, name="old/name"),
        period[1]: window_with_rank(period[1], OUT, name="new/name"),
    }

    [trajectory] = [
        t
        for t in find_trajectories(period, windows, [], None)
        if t.repository_id == REPOSITORY_ID
    ]

    assert trajectory.repository_name == "new/name"


@pytest.mark.parametrize(
    ("ranks", "is_durable"),
    [
        # A peak of one window.
        ([MISSING, MISSING, 4, MISSING], False),
        # A peak of one day: in the 3 windows that hold it, which share it.
        ([4, 4, 4, OUT], False),
        # D and D+2 share D.
        ([4, OUT, 4, OUT], False),
        # D and D+3 have no day in common.
        ([4, OUT, OUT, 4], True),
        ([4, MISSING, MISSING, 20], True),
    ],
    ids=[
        "one-window",
        "one-day",
        "d-and-d-plus-2",
        "d-and-d-plus-3",
        "missing-between",
    ],
)
def test_durable_needs_two_windows_in_the_top_without_a_day_in_common(
    ranks, is_durable
):
    assert ("durable" in follow(ranks).criteria) is is_durable


def test_durable_counts_a_window_before_the_period():
    # The window 3 days before the first of the period: no day in common with it.
    trajectory = follow([4, OUT], lookback=[(DAY - timedelta(days=3), 25)])

    assert "durable" in trajectory.criteria


def test_durable_does_not_count_a_window_before_the_period_sharing_a_day():
    trajectory = follow([4, OUT], lookback=[(DAY - timedelta(days=2), 25)])

    assert "durable" not in trajectory.criteria


@pytest.mark.parametrize(
    ("ranks", "is_accelerating"),
    [
        ([12, 10, 8], False),
        ([12, 10, 7], True),
        # A missing window is skipped.
        ([12, MISSING, 7], True),
        # The repository enters the top, then rises (decision A of Sabine, 2026-10-30).
        ([OUT, 28, 20, 9], True),
        # Out of the top breaks the run, which starts again: 25 then 22.
        ([12, 7, OUT, 25, 22], False),
        # Out of the top at the end: the run starts again, empty.
        ([28, 20, 9, OUT], False),
        # Each rank better than the one before.
        ([20, 20, 9], False),
        ([20, 9, 12, 8], False),
        # A rank alone.
        ([MISSING, 3], False),
    ],
    ids=[
        "four-ranks",
        "five-ranks",
        "missing-skipped",
        "enters-then-rises",
        "out-then-back",
        "out-at-the-end",
        "same-rank",
        "falls-back",
        "one-rank",
    ],
)
def test_accelerating_reads_the_last_run_of_windows_in_the_top(ranks, is_accelerating):
    assert ("accelerating" in follow(ranks).criteria) is is_accelerating


def test_new_is_a_repository_in_no_top_of_the_previous_report():
    previous = days(2, DAY - timedelta(days=2))
    period_start = DAY

    absent_before = follow([4], period_start, previous=previous)
    in_a_top_before = follow(
        [4], period_start, lookback=[(previous[0], 30)], previous=previous
    )

    assert "new" in absent_before.criteria
    assert "new" not in in_a_top_before.criteria


def test_new_is_not_evaluated_without_a_previous_report():
    assert "new" not in follow([4]).criteria


def test_the_criteria_keep_their_order():
    trajectory = follow([20, 9, 4, 1], previous=[DAY - timedelta(days=1)])

    assert trajectory.criteria == ("durable", "new", "accelerating")


def test_the_trajectories_are_sorted_by_best_rank_then_repository_id():
    period = days(1)
    window = StarWindow(DAY, (stars(9, 30), stars(3, 30), stars(5, 40)))

    trajectories = find_trajectories(period, {DAY: window}, [], None)

    assert [t.repository_id for t in trajectories] == [5, 3, 9]


def trajectory(repository_id, best_rank, criteria=()):
    return Trajectory(
        repository_id=repository_id,
        repository_name=f"owner/repo-{repository_id}",
        points=(),
        criteria=criteria,
        best_rank=best_rank,
    )


def test_the_candidates_meet_a_criterion_first_then_come_by_best_peak():
    trajectories = [
        trajectory(4, 1),
        trajectory(2, 9, ("durable",)),
        trajectory(3, 2),
        trajectory(1, 9, ("new",)),
        trajectory(5, 2),
    ]

    candidates = select_candidates(trajectories)

    assert [t.repository_id for t in candidates] == [1, 2, 4, 3, 5]


def test_the_candidates_are_capped():
    trajectories = [trajectory(k, k) for k in range(1, TREND_MAX_CANDIDATES + 2)]

    candidates = select_candidates(trajectories)

    assert len(candidates) == TREND_MAX_CANDIDATES
    assert candidates[-1].repository_id == TREND_MAX_CANDIDATES
