"""The data API on the test base of the readers (tests/conftest.py), with two clients; on each
engine for the routes that read the base."""

import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from k_b.core.api_settings import OPENAPI_PATH
from k_b.data_api.app import create_app


@pytest.fixture
def api_keys():
    """The key of each client, made for the test as kb serve-data would read them, never from .env."""
    return {
        "TERMINAL": SecretStr(secrets.token_urlsafe(32)),
        "AGENT": SecretStr(secrets.token_urlsafe(32)),
    }


@pytest.fixture
def make_client():
    """A client of a new app, on localhost, as TrustedHostMiddleware refuses the testserver host
    of TestClient; the app reads the SQLite file, or the pool of a PostgreSQL base, it is given."""

    def make(readers, api_keys):
        return TestClient(
            create_app(readers, api_keys, openapi_url=OPENAPI_PATH),
            base_url="http://localhost",
            raise_server_exceptions=False,
        )

    return make


@pytest.fixture
def client(make_client, items_database, api_keys):
    """The data API on the test base of the readers, on SQLite: for what does not read the base."""
    return make_client(items_database, api_keys)


@pytest.fixture
def reading_client(make_client, items_readers, api_keys):
    """The data API on the test base of the readers, on each engine: for what reads the base."""
    return make_client(items_readers, api_keys)


@pytest.fixture
def authorization(api_keys):
    return {"Authorization": f"Bearer {api_keys['TERMINAL'].get_secret_value()}"}
