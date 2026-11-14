"""GET /tops/{top}, the twin of a top of a day, and GET /tops/{top}/days, its days: read in watch,
for the site only (docs/specs-api.md)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from k_b.core.api_access import check_client_allowed
from k_b.core.api_errors import ApiError, ErrorSchema
from k_b.core.config import (
    DAYS_LIMIT,
    MAX_DAYS_LIMIT,
    MAX_DAYS_OFFSET,
    MAX_TOP_LIMIT,
    TOP_LIMIT,
)
from k_b.data_api.dependencies import Watch
from k_b.data_api.errors import WATCH_ERROR_RESPONSES
from k_b.data_api.schemas.top_schema import (
    TopDaysSchema,
    TopRepositorySchema,
    TopSchema,
)
from k_b.data_api.watch_reading import TOP_TWINS
from k_b.items import TopName, WrittenDay

# After the key and the limit of the app: a route of the site refuses every other client.
router = APIRouter(
    prefix="/tops", tags=["tops"], dependencies=[Depends(check_client_allowed)]
)

TOP_RESPONSES = {
    **WATCH_ERROR_RESPONSES,
    404: {"model": ErrorSchema, "description": "top_not_found"},
}

Top = Annotated[TopName, Path()]


@router.get("/{top}", responses=TOP_RESPONSES)
def read_top(
    top: Top,
    watch: Watch,
    day: Annotated[WrittenDay | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_TOP_LIMIT)] = TOP_LIMIT,
) -> TopSchema:
    """The first repositories of the top of a day, the most recent when none is given."""
    found = watch.read_production(TOP_TWINS, top, day)
    if found is None:
        raise ApiError(404, "top_not_found")
    production = found.production
    return TopSchema(
        top=production.top,
        day=found.day,
        ranked_at=production.ranked_at,
        repositories=[
            TopRepositorySchema(**repository.model_dump())
            for repository in production.repositories[:limit]
        ],
    )


@router.get("/{top}/days", responses=WATCH_ERROR_RESPONSES)
def list_top_days(
    top: Top,
    watch: Watch,
    limit: Annotated[int, Query(ge=1, le=MAX_DAYS_LIMIT)] = DAYS_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_DAYS_OFFSET)] = 0,
) -> TopDaysSchema:
    """The days of the top, the most recent first, and their total."""
    days = watch.list_days(TOP_TWINS, top)
    return TopDaysSchema(days=days[offset : offset + limit], total=len(days))
