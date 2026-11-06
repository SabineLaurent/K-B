"""The errors of the data API that the base gives, without SQL, those of both APIs being in
core/api_errors.py."""

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from k_b.core.api_errors import (
    API_ERROR_HANDLERS,
    API_ERROR_RESPONSES,
    RATE_LIMIT_EXCEEDED,
    ErrorHandlers,
    ErrorSchema,
    respond_with_error,
)
from k_b.core.api_request_log import read_request_id
from k_b.database.connection import MissingDatabaseError
from k_b.database.errors import EngineError, is_query_timeout

logger = logging.getLogger(__name__)

# The state of a request past its deadline in the base (data_api/dependencies.py).
QUERY_TIMEOUT = "query_timeout"
# The error bodies of a data route, declared in the OpenAPI.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **API_ERROR_RESPONSES,
    429: {"model": ErrorSchema, "description": RATE_LIMIT_EXCEEDED},
    500: {"model": ErrorSchema, "description": "database_error, internal_error"},
    503: {"model": ErrorSchema, "description": f"database_missing, {QUERY_TIMEOUT}"},
}


async def handle_missing_database(
    request: Request, error: MissingDatabaseError
) -> Response:
    return respond_with_error(503, "database_missing")


async def handle_database_error(request: Request, error: EngineError) -> Response:
    if is_query_timeout(error):
        return respond_to_query_timeout(request)
    # The type only: the message of SQLite may hold a path or a part of the query.
    logger.error(
        "database_error: %s request_id=%s",
        type(error).__name__,
        read_request_id(request),
    )
    return respond_with_error(500, "database_error")


def respond_to_query_timeout(request: Request) -> Response:
    # The time allowed, never the message of SQLite nor the query.
    logger.warning(
        "%s: %s s request_id=%s",
        QUERY_TIMEOUT,
        request.app.state.query_timeout_seconds,
        read_request_id(request),
    )
    return respond_with_error(503, QUERY_TIMEOUT)


ERROR_HANDLERS: ErrorHandlers = {
    **API_ERROR_HANDLERS,
    MissingDatabaseError: handle_missing_database,
    EngineError: handle_database_error,
}
