"""The token of the managed identity for the PostgreSQL base, asked for on a simulated identity
endpoint: its scope, its identity, and a failure named without what the endpoint answered."""

from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from exchange.storage_fakes import (
    FORGED_LOG_LINE,
    TEST_CLIENT_ID,
    TEST_TOKEN,
    FakeTransport,
    answer_identity_refusal,
    answer_identity_with,
    answer_token,
    remove_online_variables,
    set_identity_endpoint,
)

from k_b.core.config import (
    DATA_API_READ_TIMEOUT_SECONDS,
    DATABASE_TOKEN_CONNECT_TIMEOUT_SECONDS,
    DATABASE_TOKEN_READ_TIMEOUT_SECONDS,
)
from k_b.database.entra import (
    POSTGRESQL_TOKEN_SCOPE,
    EntraTokenError,
    build_database_credential,
    build_identity_transport,
    fetch_database_token,
)


@pytest.fixture(autouse=True)
def identity_endpoint(monkeypatch):
    """The identity endpoint of a container app, and nothing else of a run online."""
    remove_online_variables(monkeypatch)
    set_identity_endpoint(monkeypatch)


def test_the_token_is_asked_for_the_base_by_the_identity_of_its_client_id():
    transport = FakeTransport(answer_token)

    token = fetch_database_token(
        build_database_credential(TEST_CLIENT_ID, transport=transport)
    )

    assert token == TEST_TOKEN
    (request,) = transport.adapter.requests
    query = parse_qs(urlsplit(request.url).query)
    assert query["resource"] == [POSTGRESQL_TOKEN_SCOPE.removesuffix("/.default")]
    assert query["client_id"] == [TEST_CLIENT_ID]


@pytest.mark.parametrize(
    "answer",
    [
        answer_identity_refusal,
        answer_identity_with(500, "text/html", b"<html>down</html>"),
        answer_identity_with(200, "application/json", b"[]"),
    ],
    ids=["refused", "html 500", "not an object"],
)
def test_an_identity_that_gives_no_token_is_named_without_what_it_answered(answer):
    credential = build_database_credential(
        TEST_CLIENT_ID, transport=FakeTransport(answer)
    )

    with pytest.raises(EntraTokenError) as raised:
        fetch_database_token(credential)

    assert str(raised.value) == "database_no_token"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    assert FORGED_LOG_LINE not in str(raised.value)


def raise_read_timeout(request):
    """The identity endpoint that takes the request and does not answer within the wait."""
    raise requests.exceptions.ReadTimeout("read timed out")


def raise_connection_refused(request):
    """The identity endpoint that refuses the connection."""
    raise requests.exceptions.ConnectionError("connection refused")


@pytest.mark.parametrize(
    "answer",
    [
        answer_identity_with(500, "application/json", b"{}"),
        answer_identity_with(503, "application/json", b"{}"),
        raise_read_timeout,
        raise_connection_refused,
    ],
    ids=["500", "503", "no answer", "refused"],
)
def test_a_failed_request_for_the_token_is_not_asked_again(answer):
    """azure-core would ask three times more, and wait between them."""
    transport = FakeTransport(answer)
    credential = build_database_credential(TEST_CLIENT_ID, transport=transport)

    with pytest.raises(EntraTokenError):
        fetch_database_token(credential)

    assert len(transport.adapter.requests) == 1


def test_a_token_that_does_not_come_fails_before_the_client_of_the_ai_api_stops_waiting():
    assert (
        DATABASE_TOKEN_CONNECT_TIMEOUT_SECONDS + DATABASE_TOKEN_READ_TIMEOUT_SECONDS
        < DATA_API_READ_TIMEOUT_SECONDS
    )


def test_the_transport_of_the_token_waits_for_its_own_delays():
    """azure-core would otherwise wait 300 s for the endpoint to answer."""
    configuration = build_identity_transport().connection_config

    assert configuration.timeout == DATABASE_TOKEN_CONNECT_TIMEOUT_SECONDS
    assert configuration.read_timeout == DATABASE_TOKEN_READ_TIMEOUT_SECONDS


def test_the_transport_of_the_token_reads_neither_a_proxy_nor_a_certificate_of_the_environment():
    transport = build_identity_transport()
    transport.open()
    try:
        assert transport.session.trust_env is False
    finally:
        transport.close()
