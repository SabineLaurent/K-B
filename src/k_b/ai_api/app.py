"""The AI API: the digests of the watch and the trend reports, the one door of K-B to the model
(docs/fiches-veille.md, docs/tendances.md); it keeps nothing between two requests but the
measures, the spans and the log records not sent yet, and the count of the recent calls, which a
restart empties (.claude/rules/poc.md, rule 7)."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool
from pydantic import SecretStr

from k_b.ai_api.api_router import api_router
from k_b.ai_api.connectors.data_api_settings import DataApiSettings
from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.connectors.trace_export import TraceExport
from k_b.ai_api.observability.metric_instruments import ModelMetrics
from k_b.core.api_access import check_api_key, check_client_allowed
from k_b.core.api_body_limit import bound_request_bodies
from k_b.core.api_errors import API_ERROR_HANDLERS, respond_to_unexpected_error
from k_b.core.api_health import HEALTH_PATH, answer_health
from k_b.core.api_methods import remove_implicit_head
from k_b.core.api_rate_limit import RateLimiter, check_rate_limit, hold_route_slot
from k_b.core.api_request_log import log_request
from k_b.core.api_telemetry import NATIVE_TELEMETRY_OFF
from k_b.core.config import (
    AI_API_CLIENT_BY_ROUTE,
    AI_API_RATE_LIMITS,
    MAX_AI_API_BODY_BYTES,
    DigestSubject,
)

# The version of the contracts of docs/fiches-veille.md and docs/tendances.md: a change a client
# can see changes both.
API_VERSION = "0.12.0"


def create_app(
    api_keys: Mapping[str, SecretStr],
    llm_settings: LlmSettings,
    data_api_settings: DataApiSettings,
    github_settings: GithubSettings,
    subjects: Sequence[DigestSubject],
    default_window_days: int,
    model_metrics: ModelMetrics,
    trace_export: TraceExport,
    openapi_url: str | None = None,
) -> FastAPI:
    """The app, its keys, the model, the data API and GitHub it calls, its subjects, its default
    window, its measures, its traces and the path of its OpenAPI given; without any key, POST
    /digests answers 401; without a path, neither the OpenAPI nor /docs is served."""
    app = FastAPI(
        title="K-B AI API",
        version=API_VERSION,
        # On the app, not on a router: no route of the model can leave it out. /docs,
        # /openapi.json and /health are routes of Starlette, outside: they hold no data. ReDoc
        # and the OAuth2 redirect of Swagger UI, which K-B does not use, are not served.
        # In this order: a request refused here consumes nothing of what comes after it.
        dependencies=[
            Depends(check_api_key),
            Depends(check_client_allowed),
            Depends(hold_route_slot),
            Depends(check_rate_limit),
        ],
        openapi_url=openapi_url,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        # /digests/ is an unknown route (404), not a redirection to /digests.
        redirect_slashes=False,
        exception_handlers=API_ERROR_HANDLERS,
        lifespan=stop_telemetry_on_shutdown,
        telemetry=NATIVE_TELEMETRY_OFF,
    )
    app.state.api_keys = dict(api_keys)
    app.state.client_by_route = dict(AI_API_CLIENT_BY_ROUTE)
    # threading.Lock, not asyncio.Lock: acquired without waiting, and tied to no event loop.
    app.state.slot_by_route = {route: Lock() for route in AI_API_CLIENT_BY_ROUTE}
    app.state.rate_limiter = RateLimiter(AI_API_RATE_LIMITS)
    app.state.llm_settings = llm_settings
    app.state.data_api_settings = data_api_settings
    app.state.github_settings = github_settings
    app.state.subjects = tuple(subjects)
    app.state.default_window_days = default_window_days
    app.state.model_metrics = model_metrics
    app.state.trace_export = trace_export
    app.state.tracing = trace_export.build_tracing()
    # The last added is the outermost: the 500 of an unexpected error has its line too, and so
    # has the 413 of a body beyond its bound, given before the key is checked. No
    # TrustedHostMiddleware: without the key, a request reaches only /health, /docs and
    # /openapi.json, which hold no data (docs/fiches-veille.md, "Sécurité").
    bound_request_bodies(app, MAX_AI_API_BODY_BYTES)
    app.middleware("http")(respond_to_unexpected_error)
    app.middleware("http")(log_request)
    app.include_router(api_router)
    # add_route, as FastAPI adds /docs: a route of Starlette, which the key of the app does not
    # reach (fastapi/applications.py, 0.143).
    app.add_route(HEALTH_PATH, answer_health, methods=["GET"], include_in_schema=False)
    # Last: after every route is added.
    remove_implicit_head(app)
    return app


@asynccontextmanager
async def stop_telemetry_on_shutdown(app: FastAPI) -> AsyncIterator[None]:
    """Send the measures, the spans and the log records not sent yet when the app stops, the
    three at once in the threadpool, as each export waits for the network: no code after
    uvicorn.run runs on SIGTERM."""
    yield
    await asyncio.gather(
        run_in_threadpool(app.state.model_metrics.stop),
        run_in_threadpool(app.state.trace_export.stop_traces),
        run_in_threadpool(app.state.trace_export.stop_logs),
    )
