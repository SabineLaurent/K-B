"""The errors of the data API, written once for every route: a named state, no stack, no SQL, no
path, no value received (docs/specs-api.md, "Erreurs")."""

import logging
import sqlite3
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from k_b.database.connection import MissingDatabaseError

logger = logging.getLogger(__name__)

# The states of the errors Starlette raises when it routes a request.
STATE_BY_ROUTING_STATUS = {404: "route_not_found", 405: "method_not_allowed"}


class ErrorSchema(BaseModel):
    error: str


class InvalidParameterSchema(ErrorSchema):
    # The names of the parameters refused, never their values.
    parameters: list[str]


# The error bodies of a data route, declared in the OpenAPI in place of FastAPI's own 422.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorSchema, "description": "invalid_api_key"},
    422: {"model": InvalidParameterSchema, "description": "invalid_parameter"},
    500: {"model": ErrorSchema, "description": "database_error"},
    503: {"model": ErrorSchema, "description": "database_missing"},
}


class ApiError(Exception):
    """An error of the API, by its status and its named state."""

    def __init__(self, status_code: int, state: str) -> None:
        super().__init__(state)
        self.status_code = status_code
        self.state = state


def respond_with_error(
    status_code: int, state: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse({"error": state}, status_code=status_code, headers=headers)


async def handle_api_error(request: Request, error: ApiError) -> Response:
    # RFC 6750: a 401 says the scheme it expects.
    headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
    return respond_with_error(error.status_code, error.state, headers)


async def handle_invalid_parameter(
    request: Request, error: RequestValidationError
) -> Response:
    # loc is ("query", <name>, ...): the name of a declared parameter, never its value.
    parameters = sorted({str(detail["loc"][1]) for detail in error.errors()})
    return JSONResponse(
        {"error": "invalid_parameter", "parameters": parameters}, status_code=422
    )


async def handle_routing_error(
    request: Request, error: StarletteHTTPException
) -> Response:
    state = STATE_BY_ROUTING_STATUS.get(error.status_code)
    if state is None:
        return await http_exception_handler(request, error)
    return respond_with_error(error.status_code, state, error.headers)


async def handle_missing_database(
    request: Request, error: MissingDatabaseError
) -> Response:
    return respond_with_error(503, "database_missing")


async def handle_database_error(request: Request, error: sqlite3.Error) -> Response:
    # The type only: the message of SQLite may hold a path or a part of the query.
    logger.error("database_error: %s", type(error).__name__)
    return respond_with_error(500, "database_error")


# Given to FastAPI(exception_handlers=...), whose type takes a handler of one exception class.
ERROR_HANDLERS: dict[
    int | type[Exception], Callable[[Request, Any], Coroutine[Any, Any, Response]]
] = {
    ApiError: handle_api_error,
    RequestValidationError: handle_invalid_parameter,
    StarletteHTTPException: handle_routing_error,
    MissingDatabaseError: handle_missing_database,
    sqlite3.Error: handle_database_error,
}
