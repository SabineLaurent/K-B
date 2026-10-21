"""GET /health of both APIs: the probe of a container, served without key (docs/specs-api.md,
"Santé").

It says the process answers, and nothing else: neither a version, a path, nor the state of the
base or of the model. A probe that opened the base would restart the container in a loop while
the base is missing."""

from starlette.requests import Request
from starlette.responses import JSONResponse

HEALTH_PATH = "/health"


async def answer_health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})
