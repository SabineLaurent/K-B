"""Who may call an API of K-B: the key of a request, checked against the keys of its clients
(docs/specs-api.md, "Accès par clé"), and the client each route of the AI API opens to
(docs/fiches-veille.md, "Accès")."""

import hmac
from collections.abc import Mapping
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from k_b.core.api_errors import CLIENT_NOT_ALLOWED, ApiError
from k_b.core.api_request_log import find_route_template

# The access rules a client reads in the OpenAPI of both APIs (docs/specs-api.md, "Accès par clé").
BEARER_SCHEME_DESCRIPTION = (
    "One key per client, sent as `Authorization: Bearer <key>`. A missing or unknown key gets"
    " the same 401 `invalid_api_key`. No login route and no token lifetime: a key is revoked by"
    " removing it and restarting the API."
)
# auto_error=False: without a header, the 401 is the one of an unknown key, with the same body.
BEARER_SCHEME = HTTPBearer(auto_error=False, description=BEARER_SCHEME_DESCRIPTION)
# RFC 6750: a 401 says the scheme it expects.
INVALID_API_KEY_HEADERS = {"WWW-Authenticate": "Bearer"}


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
        raise ApiError(401, "invalid_api_key", INVALID_API_KEY_HEADERS)
    request.state.client_name = client_name


async def check_client_allowed(request: Request) -> None:
    """Refuse a client on a route that is not its own, after check_api_key; a route absent from
    the table of the app is refused to every client."""
    route = find_route_template(request)
    if request.app.state.client_by_route.get(route) != request.state.client_name:
        raise ApiError(403, CLIENT_NOT_ALLOWED)


def find_client(received_key: str, api_keys: Mapping[str, SecretStr]) -> str | None:
    """The client whose key is the one received, or None.

    Compared in constant time with every key, as bytes (compare_digest refuses a non-ASCII str):
    the time of the answer reveals neither the key nor its client."""
    received = received_key.encode()
    client_name = None
    for name, key in api_keys.items():
        if hmac.compare_digest(received, key.get_secret_value().encode()):
            client_name = name
    return client_name
