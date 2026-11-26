"""The data API on its test base, for the tests of the site that read it for real."""

import secrets

import pytest
from data_api.test_top_router import MonotonicClock, make_reader
from exchange.storage_fakes import FakeContainer
from fastapi.testclient import TestClient
from pydantic import SecretStr

from k_b.core.config import WATCH_CONTAINER
from k_b.data_api.app import create_app

# Made for the tests: never a real key.
DATA_API_KEY = secrets.token_urlsafe(32)


@pytest.fixture
def data_api(items_database):
    """The data API on the test base, its client WEB holding the test key, reading a fake watch,
    empty; on localhost, as TrustedHostMiddleware refuses the testserver host of TestClient. Its
    requests are kept, and its watch is given."""
    watch = FakeContainer(WATCH_CONTAINER)
    client = TestClient(
        create_app(
            items_database,
            {"WEB": SecretStr(DATA_API_KEY)},
            watch=make_reader(watch.handle, MonotonicClock()),
        ),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {DATA_API_KEY}"},
        follow_redirects=False,
        raise_server_exceptions=False,
    )
    requests = []
    client.event_hooks = {"request": [requests.append]}
    client.requests = requests
    client.watch = watch
    return client
