"""POST /digests: the digests of the watch of a window, read by the data API, classified and
written by the model under the deadline; nothing is kept, each request is a trace."""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx2
from fastapi import APIRouter, Request, status
from fastapi.exceptions import RequestValidationError

from k_b.ai_api.connectors.data_api_client import DataApiError, read_watch
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.dependencies import DataApiClient, LlmClient, RequestTime
from k_b.ai_api.digests import DigestsResult, build_digests
from k_b.ai_api.errors import ERROR_RESPONSES, to_api_error
from k_b.ai_api.observability.metrics import RequestMeasures, write_llm_call_lines
from k_b.ai_api.schemas.digest_schema import (
    ClaimSchema,
    DigestRequestSchema,
    DigestSchema,
    DigestsSchema,
    FailedSubjectSchema,
    SourceSchema,
    WindowSchema,
)
from k_b.ai_api.stages.checking import Digest
from k_b.ai_api.stages.classification import ClassificationFailure
from k_b.ai_api.tracing import TRACING_OFF, Tracing
from k_b.ai_api.watch_items import WatchReading
from k_b.core.api_errors import ApiError
from k_b.core.api_request_log import read_request_id
from k_b.core.config import (
    DIGEST_REQUEST_TIMEOUT_SECONDS,
    MAX_DIGEST_WINDOW_DAYS,
    MILLISECONDS_PER_SECOND,
    DigestSubject,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/digests", tags=["digests"])
# The root span, named as the conventions of HTTP name a server span: its method and its route.
ROOT_SPAN = "POST /digests"
ROOT_ATTRIBUTES: dict[str, str] = {
    "http.request.method": "POST",
    "http.route": "/digests",
}
HTTP_STATUS = "http.response.status_code"
SUBJECT_STARTS = "since_by_subject"


@dataclass(frozen=True)
class DigestWindow:
    """The window of a request: the start of each subject, in the order of the list, and the
    instant of the request; days is the window of a subject without a start."""

    days: int
    until: datetime
    since_by_subject: Mapping[str, datetime]

    @property
    def since(self) -> datetime:
        """The start of the reading, the oldest start of a subject."""
        return min(self.since_by_subject.values())


@router.post("", responses=ERROR_RESPONSES)
def post_digests(
    request: Request,
    demand: DigestRequestSchema,
    llm_client: LlmClient,
    data_api_client: DataApiClient,
    request_time: RequestTime,
) -> DigestsSchema:
    """The digests of the items of the window, one per subject with items; a subject whose
    writing fails is named in failed_subjects, a reading or a classification that fails fails
    the request."""
    # The root span ends whatever happens, its state named. A 401, a 403, a 422 and a 429 have
    # none, and an error once the response is returned leaves it at 200 (docs/fiches-veille.md,
    # "Traces").
    # Not in the docstring: it is the description of the route in the OpenAPI.
    # The starts are checked before the root span: a 422 opens none, as a 422 of the body.
    window = find_digest_window(
        demand,
        request.app.state.subjects,
        request.app.state.default_window_days,
        request_time,
    )
    request_id = read_request_id(request)
    tracing: Tracing = request.app.state.tracing
    with (
        request.app.state.model_metrics.measure_request("/digests"),
        tracing.step(
            ROOT_SPAN, "server", ROOT_ATTRIBUTES | {"k_b.request_id": request_id}
        ) as root,
    ):
        try:
            digests = answer_digests(
                request,
                request_id,
                window,
                llm_client,
                data_api_client,
                tracing=tracing,
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
        return digests


def find_digest_window(
    demand: DigestRequestSchema,
    subjects: Sequence[DigestSubject],
    default_window_days: int,
    request_time: datetime,
) -> DigestWindow:
    """The start of each subject: given, or window_days before the request, and never more than
    MAX_DIGEST_WINDOW_DAYS before it; a start of a subject out of the list, or after the request,
    is refused as its parameter."""
    window_days = (
        default_window_days if demand.window_days is None else demand.window_days
    )
    until = request_time.replace(microsecond=0)
    given = demand.since_by_subject or {}
    names = [subject.name for subject in subjects]
    if any(name not in names for name in given) or any(
        start > until for start in given.values()
    ):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", SUBJECT_STARTS),
                    "msg": "a subject out of the list, or a start after the request",
                }
            ]
        )
    default_since = until - timedelta(days=window_days)
    bound = until - timedelta(days=MAX_DIGEST_WINDOW_DAYS)
    return DigestWindow(
        days=window_days,
        until=until,
        since_by_subject={
            name: max(given.get(name, default_since), bound) for name in names
        },
    )


def answer_digests(
    request: Request,
    request_id: str,
    window: DigestWindow,
    llm_client: httpx2.Client,
    data_api_client: httpx2.Client,
    *,
    tracing: Tracing = TRACING_OFF,
) -> DigestsSchema:
    """The reading, the digests and their measures; a reading or a classification that fails
    raises its ApiError."""
    deadline = Deadline.after(DIGEST_REQUEST_TIMEOUT_SECONDS)
    state = request.app.state
    started = time.perf_counter()
    reading = read_window(
        data_api_client, window.since, deadline, request_id, tracing=tracing
    )
    data_fetch_ms = round((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    # Each request read, a model called or not (docs/fiches-veille.md, "Métriques").
    state.model_metrics.record_data_fetch(data_fetch_ms)
    result = build_digests(
        llm_client,
        state.llm_settings,
        reading,
        state.subjects,
        window.since_by_subject,
        window.until,
        deadline,
        tracing=tracing,
    )
    write_llm_call_lines(
        request_id,
        state.llm_settings,
        result.stage_calls,
        RequestMeasures(
            data_fetch_ms=data_fetch_ms,
            items_dropped_before_writing_stage=(
                reading.items_dropped
                if isinstance(result, ClassificationFailure)
                else result.items_dropped_before_writing_stage
            ),
            items_capped=reading.items_capped,
        ),
    )
    state.model_metrics.record_calls(state.llm_settings, result.stage_calls)
    if isinstance(result, ClassificationFailure):
        raise to_api_error(result.state, result.retry_after_seconds)
    return DigestsSchema(
        request_id=request_id,
        model=state.llm_settings.model,
        window=WindowSchema(
            days=window.days,
            since=window.since,
            until=window.until,
            capped_kind=reading.capped_kind,
            covered_after=reading.covered_after,
        ),
        since_by_subject=dict(window.since_by_subject),
        digests=[to_digest_schema(digest) for digest in result.digests],
        failed_subjects=to_failed_subject_schemas(result),
        subjects_without_items=list(result.subjects_without_items),
        no_suitable_subject=list(result.no_suitable_subject),
        unanswered=list(result.unanswered),
        items_in=result.items_in,
        items_truncated=result.items_truncated,
        items_dropped_before_writing_stage=result.items_dropped_before_writing_stage,
        items_before_subject_start=result.items_before_subject_start,
        items_capped=result.items_capped,
    )


def read_window(
    http_client: httpx2.Client,
    since: datetime,
    deadline: Deadline,
    request_id: str,
    *,
    tracing: Tracing = TRACING_OFF,
) -> WatchReading:
    """The watch of the window; a failure of the data API is logged here and fails the request,
    without call to the model."""
    with tracing.step("read_watch") as step:
        try:
            reading = read_watch(http_client, since, deadline=deadline)
        except DataApiError as error:
            step.fail(error.state)
            logger.error(
                "reading of the watch failed: %s, request_id=%s", error, request_id
            )
            raise to_api_error(error.state) from None
        step.set(
            {
                "k_b.items.read": len(reading.items),
                "k_b.items.dropped": reading.items_dropped,
                "k_b.items.capped": reading.items_capped,
                "k_b.capped_kind": reading.capped_kind,
            }
        )
        return reading


def to_digest_schema(digest: Digest) -> DigestSchema:
    """The digest of the response: the claims the checks kept, without their facts."""
    return DigestSchema(
        subject=digest.subject,
        claims=[
            ClaimSchema(text=claim.text, item_ids=list(claim.item_ids))
            for claim in digest.claims
        ],
        sources=[
            SourceSchema(
                item_id=source.item_id,
                kind=source.kind,
                title=source.title,
                url=source.url,
            )
            for source in digest.sources
        ],
        items_not_retained_in_output=list(digest.items_not_retained_in_output),
        claims_removed=digest.claims_removed,
        items_removed_by_checks=list(digest.items_removed_by_checks),
    )


def to_failed_subject_schemas(result: DigestsResult) -> list[FailedSubjectSchema]:
    return [
        FailedSubjectSchema(
            subject=failed.subject, stage=failed.stage, error=failed.error
        )
        for failed in result.failed_subjects
    ]
