"""The token of the managed identity for the PostgreSQL base, asked for on a simulated identity
endpoint: its scope, its identity, and a failure named without what the endpoint answered."""

from urllib.parse import parse_qs, urlsplit

import pytest
from jobs.storage_fakes import (
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
from k_b.database.entra import (
    POSTGRESQL_TOKEN_SCOPE,
    EntraTokenError,
    build_database_credential,
    build_identity_transport,
    fetch_database_token,
)

from k_b.core.config import (
    DATABASE_TOKEN_CONNECT_TIMEOUT_SECONDS,
    DATABASE_TOKEN_READ_TIMEOUT_SECONDS,
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
