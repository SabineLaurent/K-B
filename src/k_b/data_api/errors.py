"""The errors of the data API that the base and watch give, without SQL nor a name of watch, those
of both APIs being in core/api_errors.py."""

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from k_b.core.api_errors import (
    API_ERROR_HANDLERS,
    API_ERROR_RESPONSES,
    CLIENT_NOT_ALLOWED,
    INTERNAL_ERROR,
    RATE_LIMIT_EXCEEDED,
    ErrorHandlers,
    ErrorSchema,
    respond_with_error,
)
from k_b.core.api_request_log import read_request_id
from k_b.data_api.watch_reading import WatchReadingError, WatchReadingState
from k_b.database.errors import ENGINE_ERRORS, EngineError, is_query_timeout
from k_b.database.location import MissingDatabaseError
from k_b.exchange.storage import ExchangeStorageError

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
# The state of a route of watch when kb serve-data has no setting of the exchange storage.
WATCH_UNCONFIGURED = "watch_unconfigured"
STATUS_BY_WATCH_STATE: dict[WatchReadingState, int] = {
    "watch_listing_too_long": 502,
    "watch_production_refused": 502,
    "watch_production_changed": 503,
}
# A request to the exchange storage that failed: 502, the answer of the storage not usable; 503 when
# the container is gone; 504 past its wait.
STATUS_BY_STORAGE_STATE = {
    "exchange_storage_not_found": 503,
    "exchange_storage_timeout": 504,
}
# The error bodies of a route of watch, declared in the OpenAPI: it reads no base.
WATCH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **API_ERROR_RESPONSES,
    403: {"model": ErrorSchema, "description": CLIENT_NOT_ALLOWED},
    429: {"model": ErrorSchema, "description": RATE_LIMIT_EXCEEDED},
    500: {"model": ErrorSchema, "description": INTERNAL_ERROR},
    502: {
        "model": ErrorSchema,
        "description": "watch_listing_too_long, watch_production_refused,"
        " exchange_storage_unavailable, exchange_storage_no_token,"
        " exchange_storage_unauthorized, exchange_storage_forbidden, exchange_storage_failed",
    },
    503: {
        "model": ErrorSchema,
        "description": f"{WATCH_UNCONFIGURED}, watch_production_changed,"
        " exchange_storage_not_found",
    },
    504: {"model": ErrorSchema, "description": "exchange_storage_timeout"},
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


async def handle_watch_reading_error(
    request: Request, error: WatchReadingError
) -> Response:
    """A reading of watch that stopped, logged by its state and its measure: a twin changed since
    its listing is a race with a job, a warning; the others an error."""
    level = (
        logging.WARNING if error.state == "watch_production_changed" else logging.ERROR
    )
    logger.log(level, "%s request_id=%s", error, read_request_id(request))
    return respond_with_error(STATUS_BY_WATCH_STATE[error.state], error.state)


async def handle_storage_error(
    request: Request, error: ExchangeStorageError
) -> Response:
    """A request to the exchange storage that failed, logged by its state, its status and the code
    of the storage, never the message of the SDK, which may name a blob."""
    logger.error("%s request_id=%s", error, read_request_id(request))
    return respond_with_error(
        STATUS_BY_STORAGE_STATE.get(error.state, 502), error.state
    )


ERROR_HANDLERS: ErrorHandlers = {
    **API_ERROR_HANDLERS,
    MissingDatabaseError: handle_missing_database,
    **dict.fromkeys(ENGINE_ERRORS, handle_database_error),
    WatchReadingError: handle_watch_reading_error,
    ExchangeStorageError: handle_storage_error,
}
