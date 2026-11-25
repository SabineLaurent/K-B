"""The site in a TestClient, its data API simulated, and the header Azure Container Apps sets once its
operator is signed in."""

import secrets
from datetime import UTC, datetime

import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from feed_fixture import ITEMS_PAGE
from pydantic import SecretStr

from k_b.core.config import WEB_ALLOWED_HOSTS
from k_b.web.app import create_app
from k_b.web.data_api_client import build_data_api_client
from k_b.web.settings import DataApiAccess

# An object id of the form Microsoft Entra gives, made for the tests.
OPERATOR_ID = "0f1e2d3c-4b5a-4968-8776-a5b4c3d2e1f0"
OPERATOR_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
OPERATOR_HEADERS = {OPERATOR_HEADER: OPERATOR_ID}
# The pages of the site, each with the header that lets it through.
PAGE_PATHS = ("/", "/sources", "/accessibilite")
# Made for the tests: never a real key.
TEST_API_KEY = secrets.token_urlsafe(32)
# The moment of the tests: "1 jour" asks since 2026-11-10T00:00:00Z.
NOW = datetime(2026, 11, 11, 17, 40, tzinfo=UTC)
# The version tag of an image built by deploy.yml, which the footer of every page gives.
TEST_VERSION = "v0.1.9"


def serve(body, status_code=200):
    """A data API that answers every request with body, never by the network."""
    return lambda request: httpx2.Response(status_code, json=body)


def make_app(
    operator_id: str | None = OPERATOR_ID,
    handler=None,
    allowed_hosts=WEB_ALLOWED_HOSTS,
    version: str | None = TEST_VERSION,
) -> FastAPI:
    """The site, its data API answering by handler, the page of the fixture by default."""
    access = DataApiAccess(
        base_url="http://127.0.0.1:8000", api_key=SecretStr(TEST_API_KEY)
    )
    transport = httpx2.MockTransport(handler or serve(ITEMS_PAGE))
    return create_app(
        operator_id=operator_id,
        data_api_client=build_data_api_client(access, transport),
        clock=lambda: NOW,
        allowed_hosts=allowed_hosts,
        version=version,
    )


def make_client(operator_id: str | None = OPERATOR_ID, handler=None) -> TestClient:
    """A client of the site; base_url localhost, a host the site answers by default."""
    return TestClient(
        make_app(operator_id, handler),
        base_url="http://localhost",
        raise_server_exceptions=False,
    )
