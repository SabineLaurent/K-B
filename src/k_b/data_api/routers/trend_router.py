"""GET /trends: the repositories that gained the most stars and forks over a window of 3 days
(docs/specs-api.md)."""

from typing import Annotated

from fastapi import APIRouter, Query

from k_b.core.api_errors import ApiError, ErrorSchema
from k_b.data_api.dependencies import Database
from k_b.data_api.errors import ERROR_RESPONSES
from k_b.data_api.schemas.trend_schema import TrendSchema, TrendWindowSchema
from k_b.database.reading import read_trends
from k_b.items import WrittenDay

router = APIRouter(prefix="/trends", tags=["trends"])

TRENDS_RESPONSES = {
    **ERROR_RESPONSES,
    404: {"model": ErrorSchema, "description": "trend_window_not_found"},
}


@router.get("", responses=TRENDS_RESPONSES)
def list_trends(
    connection: Database,
    window_end: Annotated[WrittenDay | None, Query()] = None,
) -> TrendWindowSchema:
    """The trends of a window, the latest in the base when none is given."""
    window = read_trends(connection, window_end)
    if window is None:
        raise ApiError(404, "trend_window_not_found")
    return TrendWindowSchema(
        window_end=window.window_end,
        trends=[TrendSchema(**trend._asdict()) for trend in window.trends],
    )
