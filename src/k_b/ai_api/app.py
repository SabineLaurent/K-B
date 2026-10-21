"""The AI API: the digests of the watch, the one door of K-B to the model (docs/fiches-veille.md),
on the machine by default. create_app plugs in the routers (gathered by api_router.py), the key
and the errors; it keeps nothing between two requests (.claude/rules/poc.md, rule 7)."""

from collections.abc import Mapping, Sequence

from fastapi import Depends, FastAPI
from pydantic import SecretStr

from k_b.ai_api.api_router import api_router
from k_b.ai_api.connectors.data_api_settings import DataApiSettings
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.core.api_access import check_api_key
from k_b.core.api_errors import API_ERROR_HANDLERS, respond_to_unexpected_error
from k_b.core.api_health import HEALTH_PATH, answer_health
from k_b.core.api_request_log import log_request
from k_b.core.config import DigestSubject

# The version of the contract of docs/fiches-veille.md: a change a client can see changes both.
API_VERSION = "0.2.0"


def create_app(
    api_keys: Mapping[str, SecretStr],
    llm_settings: LlmSettings,
    data_api_settings: DataApiSettings,
    subjects: Sequence[DigestSubject],
    default_window_days: int,
) -> FastAPI:
    """The app, its keys, the model and the data API it calls, the subjects it writes and the
    window of a request that gives none: a test makes its own, kb serve-ai gives those of the
    environment. Without any key, POST /digests answers 401."""
    app = FastAPI(
        title="K-B AI API",
        version=API_VERSION,
        # On the app, not on a router: no route of the model can leave it out. /docs,
        # /openapi.json and /health are routes of Starlette, outside: they hold no data. ReDoc
        # and the OAuth2 redirect of Swagger UI, which K-B does not use, are not served.
        dependencies=[Depends(check_api_key)],
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        # /digests/ is an unknown route (404), not a redirection to /digests.
        redirect_slashes=False,
        exception_handlers=API_ERROR_HANDLERS,
    )
    app.state.api_keys = dict(api_keys)
    app.state.llm_settings = llm_settings
    app.state.data_api_settings = data_api_settings
    app.state.subjects = tuple(subjects)
    app.state.default_window_days = default_window_days
    # The last added is the outermost: the 500 of an unexpected error has its line too. No
    # TrustedHostMiddleware: without the key, a request reaches only /health, /docs and
    # /openapi.json, which hold no data (docs/fiches-veille.md, "Sécurité").
    app.middleware("http")(respond_to_unexpected_error)
    app.middleware("http")(log_request)
    app.include_router(api_router)
    # add_route, as FastAPI adds /docs: a route of Starlette, which the key of the app does not
    # reach (fastapi/applications.py, 0.143).
    app.add_route(HEALTH_PATH, answer_health, methods=["GET"], include_in_schema=False)
    return app
