"""The factual trend report: the period after the previous report, its windows read by the data API
under the deadline, then the repositories that meet a criterion (docs/tendances.md); nothing is
written nor logged here, the reading is a span without any repository."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

import httpx2

from k_b.ai_api.connectors.data_api_client import DataApiError, read_trend_window
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.tracing import TRACING_OFF, Tracing
from k_b.ai_api.trajectories import StarWindow, Trajectory, find_trajectories
from k_b.core.config import (
    GH_ARCHIVE_MAX_CATCH_UP_WINDOWS,
    TREND_DURABLE_LOOKBACK_WINDOWS,
    TREND_FIRST_REPORT_WINDOWS,
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
class TrendReport:
    period: TrendPeriod
    repositories: tuple[Trajectory, ...]
    # Meeting a criterion, left out: their name, `.` or with `..`, would go into a path.
    repositories_dropped: int


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
    http_client: httpx2.Client,
    after: date | None,
    previous_first_window: date | None,
    deadline: Deadline,
    *,
    tracing: Tracing = TRACING_OFF,
) -> TrendReport:
    """The repositories that meet a criterion over the windows after `after`, the last window of
    the previous report, None for the first; a failure of the data API raises its DataApiError."""
    with tracing.step("read_trend_windows") as step:
        try:
            reading = read_period(http_client, after, previous_first_window, deadline)
        except DataApiError as error:
            step.fail(error.state)
            raise
        report = to_trend_report(after is None, reading)
        step.set(
            {
                "k_b.windows.period": len(report.period.windows),
                "k_b.windows.read": reading.requests,
                "k_b.windows.missing": len(report.period.missing_windows),
                "k_b.windows.capped": report.period.windows_capped,
                "k_b.repositories.reported": len(report.repositories),
                "k_b.repositories.dropped": report.repositories_dropped,
            }
        )
        return report


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


def to_trend_report(first_report: bool, reading: PeriodReading) -> TrendReport:
    """The repositories that meet a criterion; new is not evaluated when every window of the
    previous report is missing."""
    previous = reading.previous
    if previous is not None and not any(end in reading.windows for end in previous):
        previous = None
    trajectories = find_trajectories(
        reading.period, reading.windows, reading.lookback, previous
    )
    meeting_a_criterion = [
        trajectory for trajectory in trajectories if trajectory.criteria
    ]
    repositories = tuple(
        trajectory
        for trajectory in meeting_a_criterion
        if is_repository_name(trajectory.repository_name)
    )
    return TrendReport(
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
        repositories=repositories,
        repositories_dropped=len(meeting_a_criterion) - len(repositories),
    )
