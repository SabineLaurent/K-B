"""GET /health/database: whether the data API reads its base, for Sabine, kb smoke-test and the
monitoring; never for a probe of a container, which would restart the API at each failure of the
base (docs/specs-api.md, "Santé")."""

from threading import Lock

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from k_b.core.api_errors import REQUEST_ALREADY_RUNNING, respond_with_error
from k_b.core.api_health import HEALTHY_ANSWER
from k_b.core.config import DATABASE_HEALTH_RETRY_AFTER_SECONDS
from k_b.database.engine import connect_reader
from k_b.database.reading import check_reading


def answer_database_health(request: Request) -> Response:
    """200 once the base is read, or the error a data route gets for the same cause (data_api/
    errors.py); one check at a time, the next refused with 429: the route has no key, and each
    check holds a connection of the pool.

    A function, not a coroutine: Starlette runs it in a thread, as the reading blocks."""
    slot: Lock = request.app.state.database_health_slot
    if not slot.acquire(blocking=False):
        return respond_with_error(
            429,
            REQUEST_ALREADY_RUNNING,
            {"Retry-After": str(DATABASE_HEALTH_RETRY_AFTER_SECONDS)},
        )
    try:
        with connect_reader(
            request.app.state.readers, request.app.state.query_timeout_seconds
        ) as connection:
            check_reading(connection)
    finally:
        slot.release()
    return JSONResponse(HEALTHY_ANSWER)
