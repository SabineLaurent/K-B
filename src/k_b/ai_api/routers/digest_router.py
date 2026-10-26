"""POST /digests: the digests of the watch of a window, read by the data API, classified and
written by the model under the deadline; nothing is kept."""

import logging
import time
from datetime import datetime, timedelta

import httpx2
from fastapi import APIRouter, Request

from k_b.ai_api.connectors.data_api_client import DataApiError, read_watch
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.dependencies import DataApiClient, LlmClient, RequestTime
from k_b.ai_api.digests import (
    ClassificationFailure,
    Digest,
    DigestsResult,
    build_digests,
)
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
from k_b.ai_api.watch_items import WatchReading
from k_b.core.api_request_log import read_request_id
from k_b.core.config import DIGEST_REQUEST_TIMEOUT_SECONDS, MILLISECONDS_PER_SECOND

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/digests", tags=["digests"])


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
    deadline = Deadline.after(DIGEST_REQUEST_TIMEOUT_SECONDS)
    state = request.app.state
    request_id = read_request_id(request)
    window_days = (
        state.default_window_days if demand.window_days is None else demand.window_days
    )
    until = request_time.replace(microsecond=0)
    since = until - timedelta(days=window_days)
    started = time.perf_counter()
    reading = read_window(data_api_client, since, deadline, request_id)
    data_fetch_ms = round((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    # Each request read, a model called or not (docs/fiches-veille.md, "Métriques").
    state.model_metrics.record_data_fetch(data_fetch_ms)
    result = build_digests(
        llm_client, state.llm_settings, reading, state.subjects, deadline
    )
    write_llm_call_lines(
        request_id,
        state.llm_settings,
        result.stage_calls,
        RequestMeasures(
            data_fetch_ms=data_fetch_ms,
            items_dropped=(
                reading.items_dropped
                if isinstance(result, ClassificationFailure)
                else result.items_dropped
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
            days=window_days,
            since=since,
            until=until,
            capped_kind=reading.capped_kind,
            covered_after=reading.covered_after,
        ),
        digests=[to_digest_schema(digest) for digest in result.digests],
        failed_subjects=to_failed_subject_schemas(result),
        not_retained=list(result.not_retained),
        unanswered=list(result.unanswered),
        items_in=result.items_in,
        items_truncated=result.items_truncated,
        items_dropped=result.items_dropped,
        items_capped=result.items_capped,
    )


def read_window(
    http_client: httpx2.Client, since: datetime, deadline: Deadline, request_id: str
) -> WatchReading:
    """The watch of the window; a failure of the data API is logged here and fails the request,
    without call to the model."""
    try:
        return read_watch(http_client, since, deadline=deadline)
    except DataApiError as error:
        logger.error(
            "reading of the watch failed: %s, request_id=%s", error, request_id
        )
        raise to_api_error(error.state) from None


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
        not_retained=list(digest.not_retained),
        claims_removed=digest.claims_removed,
        items_uncited=list(digest.items_uncited),
    )


def to_failed_subject_schemas(result: DigestsResult) -> list[FailedSubjectSchema]:
    return [
        FailedSubjectSchema(
            subject=failed.subject, stage=failed.stage, error=failed.error
        )
        for failed in result.failed_subjects
    ]
