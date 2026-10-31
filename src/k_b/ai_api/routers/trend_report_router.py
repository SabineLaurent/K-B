"""POST /trend-reports: the repositories of the GH Archive windows after the previous report that
meet a criterion, read by the data API under the deadline, with the sheet of each candidate read
on GitHub; nothing is kept, each request is a trace."""

import logging
from datetime import datetime

import httpx2
from fastapi import APIRouter, Request, status

from k_b.ai_api.connectors.data_api_client import DataApiError
from k_b.ai_api.connectors.github_client import GithubError
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.dependencies import DataApiClient, GithubClient, RequestTime
from k_b.ai_api.errors import TREND_REPORT_ERROR_RESPONSES, to_api_error
from k_b.ai_api.repository_cards import RepositoryFacts
from k_b.ai_api.schemas.trend_report_schema import (
    CandidatesSchema,
    DroppedCandidatesSchema,
    RepositoryFactsSchema,
    TrajectoryPointSchema,
    TrendPeriodSchema,
    TrendReportRequestSchema,
    TrendReportSchema,
    TrendRepositorySchema,
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
    request_time: RequestTime,
) -> TrendReportSchema:
    """The repositories that meet a criterion over the windows after the previous report, each
    with its trajectory; no window after it gives an empty period, a reading that fails fails the
    request."""
    # The root span ends whatever happens, its state named, as the one of POST /digests. A 401 and
    # a 422 have none, and an error once the response is returned, when FastAPI serializes it,
    # leaves it at 200. Not in the docstring: it is the description of the route in the OpenAPI.
    request_id = read_request_id(request)
    tracing: Tracing = request.app.state.tracing
    with tracing.step(
        ROOT_SPAN, "server", ROOT_ATTRIBUTES | {"k_b.request_id": request_id}
    ) as root:
        try:
            report = read_trend_report(
                data_api_client,
                github_client,
                request_id,
                demand,
                request_time,
                tracing=tracing,
            )
            response = to_trend_report_schema(request_id, report)
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
    data_api_client: httpx2.Client,
    github_client: httpx2.Client,
    request_id: str,
    demand: TrendReportRequestSchema,
    request_time: datetime,
    *,
    tracing: Tracing = TRACING_OFF,
) -> TrendReport:
    """The report under its deadline; a failure of the data API or of GitHub is logged here, its
    state and its HTTP status, never a repository, and fails the whole request."""
    deadline = Deadline.after(TREND_REPORT_REQUEST_TIMEOUT_SECONDS)
    try:
        return build_trend_report(
            data_api_client,
            github_client,
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


def to_trend_report_schema(request_id: str, report: TrendReport) -> TrendReportSchema:
    """The report of the response; no model is called."""
    period = report.period
    return TrendReportSchema(
        request_id=request_id,
        model=None,
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
        trajectory=[
            TrajectoryPointSchema(
                window_end=point.window_end,
                state=point.state,
                rank=point.rank,
                stars_gained=point.stars_gained,
            )
            for point in trajectory.points
        ],
        facts=None if facts is None else to_facts_schema(facts),
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
