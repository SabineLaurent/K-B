"""The dependencies of the data routes: the key of the client, the connection of the request."""

import hmac
import sqlite3
from collections.abc import Iterator, Mapping
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from k_b.data_api.errors import ApiError
from k_b.database.connection import connect_database_read_only

# auto_error=False: without a header, the 401 is the one of an unknown key, with the same body.
BEARER_SCHEME = HTTPBearer(auto_error=False)


def check_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER_SCHEME)],
) -> None:
    """Name the client of the key received, for the log; refuse a missing or unknown key with
    the same 401."""
    client_name = (
        None
        if credentials is None
        else find_client(credentials.credentials, request.app.state.api_keys)
    )
    if client_name is None:
        raise ApiError(401, "invalid_api_key")
    request.state.client_name = client_name


def find_client(received_key: str, api_keys: Mapping[str, SecretStr]) -> str | None:
    """The client whose key is the one received, or None.

    Compared in constant time with every key, without stopping at the one that matches: the
    time of the answer tells neither the key nor which client holds it. As bytes: compare_digest
    refuses a str that is not ASCII.
    """
    received = received_key.encode()
    client_name = None
    for name, key in api_keys.items():
        if hmac.compare_digest(received, key.get_secret_value().encode()):
            client_name = name
    return client_name


def open_database(request: Request) -> Iterator[sqlite3.Connection]:
    """One read-only connection per request, closed once the response is made."""
    connection = connect_database_read_only(request.app.state.database_path)
    try:
        yield connection
    finally:
        connection.close()


Database = Annotated[sqlite3.Connection, Depends(open_database)]
