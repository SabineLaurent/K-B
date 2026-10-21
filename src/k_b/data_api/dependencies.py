"""The dependencies of the data routes: the connection of the request. The key of the client is
checked by core/api_access.py, on the whole app."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from k_b.database.connection import connect_database_read_only


def open_database(request: Request) -> Iterator[sqlite3.Connection]:
    """One read-only connection per request, closed once the response is made."""
    connection = connect_database_read_only(request.app.state.database_path)
    try:
        yield connection
    finally:
        connection.close()


Database = Annotated[sqlite3.Connection, Depends(open_database)]
