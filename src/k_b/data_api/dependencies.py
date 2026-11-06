"""The dependencies of the data routes: the connection of the request, bounded in time."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from k_b.database.engine import (
    Connection,
    connect_database_read_only,
    set_query_timeout,
)


def open_database(request: Request) -> Iterator[Connection]:
    """One read-only connection per request, its readings stopped once the deadline is passed,
    closed once the response is made."""
    connection = connect_database_read_only(request.app.state.database_path)
    try:
        set_query_timeout(connection, request.app.state.query_timeout_seconds)
        yield connection
    finally:
        connection.close()


Database = Annotated[Connection, Depends(open_database)]
