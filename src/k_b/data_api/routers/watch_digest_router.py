"""GET /digests/{subject}, the twin of the digest of a subject of a day, and GET
/digests/{subject}/days, its days: read in watch, for the site only (docs/specs-api.md)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from k_b.core.api_access import check_client_allowed
from k_b.core.api_errors import ApiError, ErrorSchema
from k_b.core.config import DAYS_LIMIT, MAX_DAYS_LIMIT, MAX_DAYS_OFFSET
from k_b.data_api.dependencies import Watch
from k_b.data_api.errors import WATCH_ERROR_RESPONSES
from k_b.data_api.schemas.watch_digest_schema import (
    DigestSubjectName,
    WatchDigestDaysSchema,
    WatchDigestSchema,
)
from k_b.data_api.watch_reading import DIGEST_TWINS
from k_b.items import WrittenDay

# After the key and the limit of the app: a route of the site refuses every other client.
router = APIRouter(
    prefix="/digests", tags=["digests"], dependencies=[Depends(check_client_allowed)]
)

DIGEST_RESPONSES = {
    **WATCH_ERROR_RESPONSES,
    404: {"model": ErrorSchema, "description": "digest_not_found"},
}

Subject = Annotated[DigestSubjectName, Path()]


@router.get("/{subject}", responses=DIGEST_RESPONSES)
def read_digest(
    subject: Subject,
    watch: Watch,
    day: Annotated[WrittenDay | None, Query()] = None,
) -> WatchDigestSchema:
    """The digest of the subject of a day, the most recent when none is given."""
    found = watch.read_production(DIGEST_TWINS, subject, day)
    if found is None:
        raise ApiError(404, "digest_not_found")
    return WatchDigestSchema(day=found.day, **found.production.model_dump())


@router.get("/{subject}/days", responses=WATCH_ERROR_RESPONSES)
def list_digest_days(
    subject: Subject,
    watch: Watch,
    limit: Annotated[int, Query(ge=1, le=MAX_DAYS_LIMIT)] = DAYS_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_DAYS_OFFSET)] = 0,
) -> WatchDigestDaysSchema:
    """The days of the subject, the most recent first, and their total."""
    days = watch.list_days(DIGEST_TWINS, subject)
    return WatchDigestDaysSchema(days=days[offset : offset + limit], total=len(days))
