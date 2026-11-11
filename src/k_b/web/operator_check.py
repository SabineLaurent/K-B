"""The check of the operator: every request but /health carries her object id, in the header Azure
Container Apps sets once Microsoft Entra has signed her in, and that it refuses from a client
(docs/site-web.md, "Accès")."""

import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import Request, Response

from k_b.core.api_health import HEALTH_PATH
from k_b.core.api_request_log import read_request_id
from k_b.core.config import GUID
from k_b.web.errors import render_error_page

logger = logging.getLogger(__name__)

# The header of the object id of the person signed in (Microsoft Learn, "Authentication and
# authorization in Azure Container Apps", read on 2026-11-11); Starlette reads names in lowercase.
OPERATOR_ID_HEADER = "x-ms-client-principal-id"
type OperatorRefusal = Literal[
    "header_absent", "header_repeated", "header_malformed", "header_other"
]


def find_operator_refusal(
    values: list[str], operator_id: str
) -> OperatorRefusal | None:
    """Why the header received is refused, or None: present once, a GUID, the one of the
    operator, given in lowercase."""
    if not values:
        return "header_absent"
    if len(values) > 1:
        return "header_repeated"
    [value] = values
    if not GUID.fullmatch(value):
        return "header_malformed"
    # compare_digest: the time taken does not tell how much of the id matched.
    if not hmac.compare_digest(value.lower(), operator_id):
        return "header_other"
    return None


async def check_operator(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Let through the requests of the operator, and /health, which holds no data; any other gets
    the page 403, logged by its state, never with the value received."""
    operator_id: str | None = request.app.state.operator_id
    # The path the router follows, decoded: request.url.path reads /health in /health%3F, which
    # a route /{name} would serve.
    if operator_id is None or request.scope["path"] == HEALTH_PATH:
        return await call_next(request)
    refusal = find_operator_refusal(
        request.headers.getlist(OPERATOR_ID_HEADER), operator_id
    )
    if refusal is not None:
        logger.warning(
            "operator_refused: %s request_id=%s", refusal, read_request_id(request)
        )
        return render_error_page(request, 403)
    return await call_next(request)
