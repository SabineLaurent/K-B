"""POST /trend-reports: the repositories of the GH Archive windows after the previous report that
meet a criterion, read by the data API under the deadline, with the sheet of each candidate read
on GitHub and the choice of the model among them; nothing is kept, each request is a trace."""

import logging
from datetime import datetime

import httpx2
from fastapi import APIRouter, Request, status

from k_b.ai_api.connectors.data_api_client import DataApiError
from k_b.ai_api.connectors.github_client import GithubError
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.dependencies import (
    DataApiClient,
    GithubClient,
    LlmClient,
    RequestTime,
)
from k_b.ai_api.errors import TREND_REPORT_ERROR_RESPONSES, to_api_error
from k_b.ai_api.observability.metrics import write_llm_call_lines
from k_b.ai_api.repository_cards import RepositoryFacts
from k_b.ai_api.schemas.trend_report_schema import (
    CandidatesSchema,
    ChosenRepositorySchema,
    DroppedCandidatesSchema,
    RepositoryFactsSchema,
    TrajectoryPointSchema,
    TrendPeriodSchema,
    TrendReportRequestSchema,
    TrendReportSchema,
    TrendRepositorySchema,
)
from k_b.ai_api.stages.trend_selection import (
    ChosenRepository,
    Selection,
    SelectionFailure,
)
from k_b.ai_api.tracing import TRACING_OFF, Tracing
from k_b.ai_api.trajectories import Trajectory
from k_b.ai_api.trend_reports import TrendReport, build_trend_report
from k_b.core.api_errors import ApiError
from k_b.core.api_request_log import read_request_id
from k_b.core.config import TREND_REPORT_REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trend-reports", tags=["trend-reports"])
# The root span, named as the conventions of HTTP name a server span: its method and its route.
ROOT_SPAN = "POST /trend-reports"
ROOT_ATTRIBUTES: dict[str, str] = {
    "http.request.method": "POST",
    "http.route": "/trend-reports",
}
HTTP_STATUS = "http.response.status_code"


@router.post("", responses=TREND_REPORT_ERROR_RESPONSES)
def post_trend_reports(
    request: Request,
    demand: TrendReportRequestSchema,
    data_api_client: DataApiClient,
    github_client: GithubClient,
    llm_client: LlmClient,
    request_time: RequestTime,
) -> TrendReportSchema:
    """The repositories that meet a criterion over the windows after the previous report, each
    with its trajectory, and those the model chose among the candidates read; no window after it
    gives an empty period, a reading that fails fails the request, a choice that fails leaves the
    report factual, with its state."""
    # The root span ends whatever happens, its state named, as the one of POST /digests. A 401, a
    # 403, a 422 and a 429 have none, and an error once the response is returned, when FastAPI
    # serializes it, leaves it at 200. Not in the docstring: it is the description of the route in
    # the OpenAPI.
    request_id = read_request_id(request)
    tracing: Tracing = request.app.state.tracing
    with tracing.step(
        ROOT_SPAN, "server", ROOT_ATTRIBUTES | {"k_b.request_id": request_id}
    ) as root:
        try:
            report = read_trend_report(
                request,
                data_api_client,
                github_client,
                llm_client,
                request_id,
                demand,
                request_time,
                tracing=tracing,
            )
            response = to_trend_report_schema(
                request_id, report, request.app.state.llm_settings.model
            )
        except ApiError as error:
            root.fail(error.state)
            root.set({HTTP_STATUS: error.status_code})
            raise
        except Exception:
            # Failed by the name of its type when the block ends.
            root.set({HTTP_STATUS: status.HTTP_500_INTERNAL_SERVER_ERROR})
            raise
        root.set({HTTP_STATUS: status.HTTP_200_OK})
        return response


def read_trend_report(
    request: Request,
    data_api_client: httpx2.Client,
    github_client: httpx2.Client,
    llm_client: httpx2.Client,
    request_id: str,
    demand: TrendReportRequestSchema,
    request_time: datetime,
    *,
    tracing: Tracing = TRACING_OFF,
) -> TrendReport:
    """The report under its deadline and the measures of its call to the model; a failure of the
    data API or of GitHub is logged here, its state and its HTTP status, never a repository, and
    fails the whole request."""
    deadline = Deadline.after(TREND_REPORT_REQUEST_TIMEOUT_SECONDS)
    state = request.app.state
    try:
        report = build_trend_report(
            data_api_client,
            github_client,
            llm_client,
            state.llm_settings,
            state.subjects,
            demand.after,
            demand.previous_first_window,
            deadline,
            request_time,
            tracing=tracing,
        )
    except DataApiError as error:
        logger.error(
            "reading of the trend windows failed: %s, request_id=%s", error, request_id
        )
        raise to_api_error(error.state) from None
    except GithubError as error:
        logger.error(
            "reading of the repository cards failed: %s, request_id=%s",
            error,
            request_id,
        )
        raise to_api_error(error.state, error.retry_after_seconds) from None
    # One line per call, the choice made or failed (.claude/rules/poc.md, rule 4); the readings
    # are measured in their spans, so no measure of the request.
    stage_calls = () if report.choice is None else report.choice.stage_calls
    write_llm_call_lines(request_id, state.llm_settings, stage_calls, None)
    state.model_metrics.record_calls(state.llm_settings, stage_calls)
    return report


def to_trend_report_schema(
    request_id: str, report: TrendReport, model: str
) -> TrendReportSchema:
    """The report of the response: the model named when it chose, none chosen included."""
    period = report.period
    choice = report.choice
    return TrendReportSchema(
        request_id=request_id,
        model=model if isinstance(choice, Selection) else None,
        choice_failure=choice.state if isinstance(choice, SelectionFailure) else None,
        chosen=[
            to_chosen_schema(chosen)
            for chosen in (choice.chosen if isinstance(choice, Selection) else ())
        ],
        period=TrendPeriodSchema(
            first_report=period.first_report,
            windows=list(period.windows),
            missing_windows=list(period.missing_windows),
            windows_capped=period.windows_capped,
            new_evaluated=period.new_evaluated,
            latest_window=period.latest_window,
        ),
        repositories=[
            to_repository_schema(trajectory, report.facts.get(trajectory.repository_id))
            for trajectory in report.repositories
        ],
        repositories_dropped=report.repositories_dropped,
        candidates=CandidatesSchema(
            selected=report.candidates.selected,
            read=report.candidates.read,
            dropped=DroppedCandidatesSchema.model_validate(report.candidates.dropped),
        ),
    )


def to_repository_schema(
    trajectory: Trajectory, facts: RepositoryFacts | None
) -> TrendRepositorySchema:
    return TrendRepositorySchema(
        repository_id=trajectory.repository_id,
        repository_name=trajectory.repository_name,
        criteria=list(trajectory.criteria),
        best_rank=trajectory.best_rank,
        trajectory=to_trajectory_schema(trajectory),
        facts=None if facts is None else to_facts_schema(facts),
    )


def to_trajectory_schema(trajectory: Trajectory) -> list[TrajectoryPointSchema]:
    return [
        TrajectoryPointSchema(
            window_end=point.window_end,
            state=point.state,
            rank=point.rank,
            stars_gained=point.stars_gained,
        )
        for point in trajectory.points
    ]


def to_chosen_schema(chosen: ChosenRepository) -> ChosenRepositorySchema:
    trajectory = chosen.candidate.trajectory
    return ChosenRepositorySchema(
        repository_id=trajectory.repository_id,
        repository_name=trajectory.repository_name,
        criteria=list(chosen.criteria),
        watch_subjects=list(chosen.watch_subjects),
        best_rank=trajectory.best_rank,
        trajectory=to_trajectory_schema(trajectory),
        facts=to_facts_schema(chosen.candidate.facts),
    )


def to_facts_schema(facts: RepositoryFacts) -> RepositoryFactsSchema:
    return RepositoryFactsSchema(
        license=facts.license,
        created_at=facts.created_at,
        language=facts.language,
        topics=list(facts.topics),
        stars_total=facts.stars_total,
        cautions=list(facts.cautions),
    )
