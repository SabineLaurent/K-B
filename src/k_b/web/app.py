"""The site of K-B, rendered by the server without JavaScript, for its operator only
(docs/site-web.md)."""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from k_b.core.api_health import HEALTH_PATH, answer_health
from k_b.core.api_methods import remove_implicit_head
from k_b.core.api_request_log import log_request
from k_b.core.api_telemetry import NATIVE_TELEMETRY_OFF
from k_b.core.config import WEB_ALLOWED_HOSTS
from k_b.web.errors import ERROR_HANDLERS, respond_to_unexpected_error
from k_b.web.operator_check import check_operator
from k_b.web.pages import router as page_router
from k_b.web.response_headers import STATIC_PATH, add_response_headers


def create_app(
    *, operator_id: str | None, allowed_hosts: Sequence[str] = WEB_ALLOWED_HOSTS
) -> FastAPI:
    """The site, given the object id of its operator in lowercase, or None to check no header
    (KB_WEB_AUTH=off), and the hosts it answers; it serves no document of an API."""
    app = FastAPI(
        title="K-B",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        # /sources/ is an unknown route (404): Starlette would build its redirection with the
        # scheme it sees, http behind the ingress of Azure Container Apps.
        redirect_slashes=False,
        exception_handlers=ERROR_HANDLERS,
        # Its traces would carry the raw query of a request (core/api_telemetry.py).
        telemetry=NATIVE_TELEMETRY_OFF,
    )
    app.state.operator_id = operator_id
    # The last added is the outermost: the compression of every answer, the error pages included,
    # then the request id, the headers of every answer, the 500, and the host and the operator
    # checked before any page.
    app.middleware("http")(check_operator)
    # www_redirect=False: Starlette would build its redirection with the scheme it sees, as for
    # redirect_slashes above.
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(allowed_hosts), www_redirect=False
    )
    app.middleware("http")(respond_to_unexpected_error)
    app.middleware("http")(add_response_headers)
    app.middleware("http")(log_request)
    app.add_middleware(GZipMiddleware)
    app.include_router(page_router)
    # By the package, never by a path: the image holds the wheel, not src/.
    app.mount(STATIC_PATH, StaticFiles(packages=[("k_b.web", "static")]), name="static")
    # add_route, as for the APIs: a route of Starlette, outside the pages.
    app.add_route(HEALTH_PATH, answer_health, methods=["GET"], include_in_schema=False)
    # Last: after every route is added.
    remove_implicit_head(app)
    return app
