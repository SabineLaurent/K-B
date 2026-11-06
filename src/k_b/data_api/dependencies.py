"""The dependencies of the data routes: the connection of the request, bounded in time."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from k_b.database.engine import Connection, connect_reader


def open_database(request: Request) -> Iterator[Connection]:
    """One read-only connection per request, its readings stopped once the deadline is passed,
    closed or given back to the pool once the response is made."""
    with connect_reader(
        request.app.state.readers, request.app.state.query_timeout_seconds
    ) as connection:
        yield connection


Database = Annotated[Connection, Depends(open_database)]
