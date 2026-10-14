"""The data API: the items of the base, read only, for the clients of Sabine on her machine
(docs/specs-api.md). create_app gathers the routers, the key and the errors."""

from collections.abc import Mapping
from pathlib import Path

from fastapi import Depends, FastAPI
from pydantic import SecretStr
from starlette.middleware.trustedhost import TrustedHostMiddleware

from k_b.data_api.dependencies import check_api_key
from k_b.data_api.errors import ERROR_HANDLERS
from k_b.data_api.request_log import log_request
from k_b.data_api.routers import item_router

# The version of docs/specs-api.md: a change a client can see changes both.
API_VERSION = "0.1.0"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


def create_app(database_path: Path, api_keys: Mapping[str, SecretStr]) -> FastAPI:
    """The app, its keys and its base given: a test makes its own, kb serve gives the keys of
    the environment. Without any key, every data route answers 401."""
    app = FastAPI(
        title="K-B data API",
        version=API_VERSION,
        # On the app, not on a router: no data route can leave it out. /docs and /openapi.json
        # are routes of Starlette, outside: they hold no data. ReDoc is not served.
        dependencies=[Depends(check_api_key)],
        redoc_url=None,
        exception_handlers=ERROR_HANDLERS,
    )
    app.state.database_path = database_path
    app.state.api_keys = dict(api_keys)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    # Added last, the outermost: the 400 of TrustedHostMiddleware has its line too.
    app.middleware("http")(log_request)
    app.include_router(item_router.router)
    return app
