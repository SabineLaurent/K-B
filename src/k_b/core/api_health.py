"""GET /health of both APIs, the probe of a container, served without key: it says the process
answers, nothing more; and the path of GET /health/database of the data API, never a probe.

A probe that opened the base would restart the container in a loop while the base is missing."""

from starlette.requests import Request
from starlette.responses import JSONResponse

HEALTH_PATH = "/health"
DATABASE_HEALTH_PATH = "/health/database"
# The body of both, checked by kb smoke-test (jobs/api_health.py).
HEALTHY_ANSWER = {"status": "ok"}


async def answer_health(request: Request) -> JSONResponse:
    return JSONResponse(HEALTHY_ANSWER)
