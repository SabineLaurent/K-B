"""The dependencies of POST /digests: the HTTP clients of the request, to the model and to the data
API, and the time of the request. The key of the client is checked by core/api_access.py, on the
whole app; a test replaces these by app.dependency_overrides."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

import httpx2
from fastapi import Depends, Request

from k_b.ai_api.connectors.data_api_client import build_data_api_client
from k_b.ai_api.connectors.llm_client import build_http_client


def open_llm_client(request: Request) -> Iterator[httpx2.Client]:
    """A client of the model per request, closed once the response is sent: nothing is kept
    between two requests (.claude/rules/poc.md, rule 7), and the replay starts again from its
    first step."""
    with build_http_client(request.app.state.llm_settings) as http_client:
        yield http_client


def open_data_api_client(request: Request) -> Iterator[httpx2.Client]:
    """A client of the data API per request, closed once the response is sent."""
    with build_data_api_client(request.app.state.data_api_settings) as http_client:
        yield http_client


def read_request_time() -> datetime:
    return datetime.now(UTC)


LlmClient = Annotated[httpx2.Client, Depends(open_llm_client)]
DataApiClient = Annotated[httpx2.Client, Depends(open_data_api_client)]
RequestTime = Annotated[datetime, Depends(read_request_time)]
