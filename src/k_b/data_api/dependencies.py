"""The dependencies of the data routes: the connection of the request, bounded in time, and the
reader of watch."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from k_b.core.api_errors import ApiError
from k_b.data_api.errors import WATCH_UNCONFIGURED
from k_b.data_api.watch_reading import WatchReader
from k_b.database.engine import Connection, connect_reader


def open_database(request: Request) -> Iterator[Connection]:
    """One read-only connection per request, its readings stopped once the deadline is passed,
    closed or given back to the pool once the response is made."""
    with connect_reader(
        request.app.state.readers, request.app.state.query_timeout_seconds
    ) as connection:
        yield connection


Database = Annotated[Connection, Depends(open_database)]


def read_watch(request: Request) -> WatchReader:
    """The reader of watch of the app; without one, 503 watch_unconfigured."""
    watch: WatchReader | None = request.app.state.watch
    if watch is None:
        raise ApiError(503, WATCH_UNCONFIGURED)
    return watch


Watch = Annotated[WatchReader, Depends(read_watch)]
