"""The request of kb trend-report to the AI API, POST /trend-reports, and the response it accepts,
an untrusted input read by a closed schema, then checked against the request and against itself:
a period that would move the register back or widen it is refused before anything is written."""

from collections.abc import Sequence
from datetime import date, timedelta
from itertools import pairwise
from typing import Annotated, Literal, get_args

import httpx2
from pydantic import AfterValidator, Field

from k_b.core.api_keys import AI_API_KEY_VARIABLE_PREFIX
from k_b.core.config import (
    DIGEST_SUBJECTS,
    GH_ARCHIVE_MAX_CATCH_UP_WINDOWS,
    GH_ARCHIVE_TOP_SIZE,
    MODEL_NAME,
    TREND_MAX_CHOSEN,
)
from k_b.items import (
    ChoiceCriterion,
    Criterion,
    WindowState,
    WrittenDayInStrictModel,
    has_too_many_windows,
    is_repository_name,
)
from k_b.post.ai_api_client import (
    REQUEST_ID,
    AiApiModel,
    match_fully,
    raise_invalid,
    read_response,
    send_request,
)

# The client KB_TREND_REPORT of kb serve-ai: one value for both sides (README, "Changer une clé").
TREND_REPORT_KEY_VARIABLE = f"{AI_API_KEY_VARIABLE_PREFIX}KB_TREND_REPORT"
TREND_REPORTS_PATH = "trend-reports"
# The criteria in the order the AI API gives them (docs/tendances.md, "Ce que rend #366").
CRITERIA: tuple[Criterion, ...] = get_args(Criterion.__value__)
CHOICE_CRITERIA: tuple[ChoiceCriterion, ...] = get_args(ChoiceCriterion.__value__)
WATCH_SUBJECT: ChoiceCriterion = "watch_subject"
SUBJECT_NAMES = tuple(subject.name for subject in DIGEST_SUBJECTS)
# The states of a choice that failed, those of LlmFailure in ai_api, which post does not import:
# a test keeps both equal.
type ChoiceFailure = Literal[
    "llm_invalid_output",
    "llm_truncated",
    "llm_content_filtered",
    "llm_rate_limited",
    "llm_unavailable",
    "llm_timeout",
]

Rank = Annotated[int, Field(ge=1, le=GH_ARCHIVE_TOP_SIZE)]
Count = Annotated[int, Field(ge=0)]


def check_repository_name(name: str) -> str:
    """owner/name, neither part `.` nor with `..`, as it makes the URL of the repository in the
    report; the message never quotes the name."""
    if not is_repository_name(name):
        raise ValueError("not owner/name, or a part . or with ..")
    return name


class TrendPoint(AiApiModel):
    window_end: WrittenDayInStrictModel
    state: WindowState
    # In the top only; stars_gained is not read: the report shows no count of stars.
    rank: Rank | None


class TrendRepository(AiApiModel):
    repository_id: int
    repository_name: Annotated[str, AfterValidator(check_repository_name)]
    criteria: Annotated[list[Criterion], Field(min_length=1)]
    best_rank: Rank
    trajectory: list[TrendPoint]


class ChosenRepository(AiApiModel):
    """A repository the model chose; its trajectory and facts are not read: the report shows
    them for the repositories of the table."""

    repository_id: int
    repository_name: Annotated[str, AfterValidator(check_repository_name)]
    criteria: Annotated[list[ChoiceCriterion], Field(min_length=1)]
    watch_subjects: list[str]


class TrendPeriod(AiApiModel):
    first_report: bool
    windows: list[WrittenDayInStrictModel]
    missing_windows: list[WrittenDayInStrictModel]
    windows_capped: bool
    new_evaluated: bool
    latest_window: WrittenDayInStrictModel | None


class DroppedCandidates(AiApiModel):
    not_found: Count
    unavailable_for_legal_reasons: Count
    moved: Count
    id_mismatch: Count
    forbidden: Count


class Candidates(AiApiModel):
    """The repositories whose sheet the AI API read on GitHub, counted; kb reads no fact."""

    selected: Count
    read: Count
    dropped: DroppedCandidates


class TrendReportResponse(AiApiModel):
    request_id: Annotated[str, AfterValidator(match_fully(REQUEST_ID))]
    model: Annotated[str, AfterValidator(match_fully(MODEL_NAME))] | None
    choice_failure: ChoiceFailure | None
    chosen: Annotated[list[ChosenRepository], Field(max_length=TREND_MAX_CHOSEN)]
    period: TrendPeriod
    repositories: list[TrendRepository]
    repositories_dropped: Count
    candidates: Candidates


def request_trend_report(
    http_client: httpx2.Client,
    after: date | None,
    previous_first_window: date | None,
    today: date,
) -> TrendReportResponse:
    """The report of the windows after `after`, the last one of the previous report, checked
    against the request and the day of the run."""
    body = {
        "after": write_day(after),
        "previous_first_window": write_day(previous_first_window),
    }
    response = read_response(
        send_request(http_client, TREND_REPORTS_PATH, body), TrendReportResponse
    )
    refuse_inconsistent_period(response, after, today)
    refuse_inconsistent_repositories(response)
    refuse_inconsistent_candidates(response)
    refuse_inconsistent_choice(response)
    refuse_inconsistent_chosen(response)
    return response


def write_day(day: date | None) -> str | None:
    return None if day is None else day.isoformat()


def refuse_inconsistent_period(
    response: TrendReportResponse, after: date | None, today: date
) -> None:
    """Refuse a period the request did not ask for, or one the register could not hold."""
    period = response.period
    request_id = response.request_id
    if period.first_report != (after is None):
        raise_invalid(request_id, "period.first_report", "not_the_request")
    if period.first_report and period.new_evaluated:
        raise_invalid(request_id, "period.new_evaluated", "first_report")
    if period.latest_window is not None and period.latest_window > today:
        raise_invalid(request_id, "period.latest_window", "after_today")
    if not period.windows:
        # Nothing is written: neither the register nor the vault takes anything from it.
        if period.latest_window is not None and (
            after is None or period.latest_window > after
        ):
            raise_invalid(request_id, "period.windows", "empty_with_a_new_window")
        return
    refuse_inconsistent_windows(response, after)


def refuse_inconsistent_windows(
    response: TrendReportResponse, after: date | None
) -> None:
    """Consecutive days from the day after `after`, as many as a report holds, up to the latest
    window, with the missing ones among them."""
    period = response.period
    windows = period.windows
    request_id = response.request_id
    if any((later - earlier).days != 1 for earlier, later in pairwise(windows)):
        raise_invalid(request_id, "period.windows", "not_consecutive")
    if has_too_many_windows(windows[0], windows[-1]):
        raise_invalid(request_id, "period.windows", "too_many_windows")
    if not is_following(after, windows, period.windows_capped):
        raise_invalid(request_id, "period.windows", "not_following_the_previous_report")
    if windows[-1] != period.latest_window:
        raise_invalid(request_id, "period.windows", "not_up_to_the_latest_window")
    if not is_in_order_once(period.missing_windows, windows):
        raise_invalid(request_id, "period.missing_windows", "not_among_the_windows")


def is_following(
    after: date | None, windows: Sequence[date], windows_capped: bool
) -> bool:
    """Whether the windows start the day after `after`, or, capped, are the most a report holds,
    older ones left out; a first report is never capped."""
    if after is None:
        return not windows_capped
    day_after = after + timedelta(days=1)
    if windows_capped:
        return (
            windows[0] > day_after and len(windows) == GH_ARCHIVE_MAX_CATCH_UP_WINDOWS
        )
    return windows[0] == day_after


def is_in_order_once[Value](values: Sequence[Value], listed: Sequence[Value]) -> bool:
    """Whether values are taken from listed, each once, in the order of listed."""
    return list(values) == [value for value in listed if value in values]


def refuse_inconsistent_repositories(response: TrendReportResponse) -> None:
    """Each repository once, its trajectory one point per window of the period, its ranks and its
    criteria as the period gives them."""
    seen_ids: set[int] = set()
    for number, repository in enumerate(response.repositories):
        place = f"repositories.{number}"
        if repository.repository_id in seen_ids:
            raise_invalid(response.request_id, place, "repository_twice")
        seen_ids.add(repository.repository_id)
        refuse_inconsistent_trajectory(response, place, repository)
        refuse_inconsistent_criteria(response, place, repository)


def refuse_inconsistent_trajectory(
    response: TrendReportResponse, place: str, repository: TrendRepository
) -> None:
    period = response.period
    request_id = response.request_id
    trajectory = repository.trajectory
    if [point.window_end for point in trajectory] != period.windows:
        raise_invalid(request_id, f"{place}.trajectory", "not_the_windows")
    for number, point in enumerate(trajectory):
        point_place = f"{place}.trajectory.{number}"
        if (point.state == "missing") != (point.window_end in period.missing_windows):
            raise_invalid(request_id, point_place, "not_the_missing_windows")
        if (point.rank is not None) != (point.state == "top"):
            raise_invalid(request_id, point_place, "rank_out_of_the_top")
    ranks = [point.rank for point in trajectory if point.rank is not None]
    if not ranks or repository.best_rank != min(ranks):
        raise_invalid(request_id, f"{place}.best_rank", "not_the_best_rank")


def refuse_inconsistent_criteria(
    response: TrendReportResponse, place: str, repository: TrendRepository
) -> None:
    if not is_in_order_once(repository.criteria, CRITERIA):
        raise_invalid(response.request_id, f"{place}.criteria", "not_in_order_once")
    if "new" in repository.criteria and not response.period.new_evaluated:
        raise_invalid(response.request_id, f"{place}.criteria", "new_not_evaluated")


def refuse_inconsistent_candidates(response: TrendReportResponse) -> None:
    """The candidates selected are those read and those left out."""
    candidates = response.candidates
    if candidates.selected != candidates.read + sum(
        candidates.dropped.model_dump().values()
    ):
        raise_invalid(response.request_id, "candidates", "not_the_sum")


def refuse_inconsistent_choice(response: TrendReportResponse) -> None:
    """A model or a failure when a candidate is read, never both; a failure chooses nothing, and
    a choice names its model."""
    request_id = response.request_id
    if response.model is not None and response.choice_failure is not None:
        raise_invalid(request_id, "choice_failure", "with_a_model")
    if response.chosen and response.choice_failure is not None:
        raise_invalid(request_id, "chosen", "with_a_choice_failure")
    if response.chosen and response.model is None:
        raise_invalid(request_id, "chosen", "without_a_model")
    if response.candidates.read == 0:
        if response.model is not None:
            raise_invalid(request_id, "model", "choice_without_candidate_read")
        if response.choice_failure is not None:
            raise_invalid(request_id, "choice_failure", "choice_without_candidate_read")
    elif response.model is None and response.choice_failure is None:
        raise_invalid(request_id, "model", "no_choice_with_candidates_read")


def refuse_inconsistent_chosen(response: TrendReportResponse) -> None:
    """Each chosen once, its criteria in order, met in the table of the repositories but
    watch_subject, which goes with its subjects, taken from the list in its order."""
    criteria_by_id = {r.repository_id: r.criteria for r in response.repositories}
    seen_ids: set[int] = set()
    for number, chosen in enumerate(response.chosen):
        place = f"chosen.{number}"
        if chosen.repository_id in seen_ids:
            raise_invalid(response.request_id, place, "repository_twice")
        seen_ids.add(chosen.repository_id)
        refuse_inconsistent_chosen_criteria(
            response, place, chosen, criteria_by_id.get(chosen.repository_id, [])
        )


def refuse_inconsistent_chosen_criteria(
    response: TrendReportResponse,
    place: str,
    chosen: ChosenRepository,
    criteria_met: Sequence[Criterion],
) -> None:
    request_id = response.request_id
    criteria = chosen.criteria
    if not is_in_order_once(criteria, CHOICE_CRITERIA):
        raise_invalid(request_id, f"{place}.criteria", "not_in_order_once")
    if "new" in criteria and not response.period.new_evaluated:
        raise_invalid(request_id, f"{place}.criteria", "new_not_evaluated")
    if any(c != WATCH_SUBJECT and c not in criteria_met for c in criteria):
        raise_invalid(request_id, f"{place}.criteria", "not_met_in_the_repositories")
    if (WATCH_SUBJECT in criteria) != bool(chosen.watch_subjects):
        raise_invalid(request_id, f"{place}.watch_subjects", "not_with_watch_subject")
    if not is_in_order_once(chosen.watch_subjects, SUBJECT_NAMES):
        raise_invalid(request_id, f"{place}.watch_subjects", "not_in_order_once")
