"""The exchange storage: its settings, the identity of the job, the listing and its errors, named
without the text the storage answers."""

from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from azure.core.credentials import AccessToken
from azure.identity import AzureCliCredential
from jobs.storage_fakes import (
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    TEST_IDENTITY_HEADER,
    TEST_TOKEN,
    FakeTransport,
    answer_error,
    answer_forbidden_naming_the_blob,
    answer_identity_refusal,
    answer_identity_with,
    answer_listing,
    answer_token,
    names_the_spotted_blob,
    set_identity_endpoint,
)

from k_b.core.config import MAX_LISTED_BLOBS
from k_b.exchange import storage as exchange_storage
from k_b.exchange.storage import (
    ExchangeStorageError,
    ExchangeStorageSettings,
    build_cli_credential,
    build_managed_identity_credential,
    build_transport,
    check_identity,
    count_listed_blobs,
    find_exchange_blob_url_refusal,
    naming_storage_errors,
    open_container_client,
    read_exchange_storage_settings_or_refusal,
)

TEST_CONTAINER = "smoke-test"
TEST_ENVIRON = {
    "KB_EXCHANGE_BLOB_URL": TEST_ACCOUNT_URL,
    "AZURE_CLIENT_ID": TEST_CLIENT_ID,
}


def test_the_settings_are_the_url_of_the_account_and_the_client_id_of_the_identity():
    assert read_exchange_storage_settings_or_refusal(
        TEST_ENVIRON
    ) == ExchangeStorageSettings(account_url=TEST_ACCOUNT_URL, client_id=TEST_CLIENT_ID)


@pytest.mark.parametrize(
    ("variable", "value", "refusal"),
    [
        ("KB_EXCHANGE_BLOB_URL", None, "KB_EXCHANGE_BLOB_URL: not set"),
        ("KB_EXCHANGE_BLOB_URL", "", "KB_EXCHANGE_BLOB_URL: not set"),
        (
            "KB_EXCHANGE_BLOB_URL",
            "http://stkbexchangetest.blob.core.windows.net",
            "KB_EXCHANGE_BLOB_URL: scheme not https",
        ),
        ("AZURE_CLIENT_ID", None, "AZURE_CLIENT_ID: not set"),
        ("AZURE_CLIENT_ID", "id-kb-smoke-test", "AZURE_CLIENT_ID: not a GUID"),
        # A GUID in braces, accepted by uuid.UUID: the client id Azure gives has none.
        ("AZURE_CLIENT_ID", "{" + TEST_CLIENT_ID + "}", "AZURE_CLIENT_ID: not a GUID"),
    ],
)
def test_a_setting_missing_or_refused_is_named_without_its_value(
    variable, value, refusal
):
    environ = {name: text for name, text in TEST_ENVIRON.items() if name != variable}
    if value is not None:
        environ[variable] = value

    assert read_exchange_storage_settings_or_refusal(environ) == refusal


@pytest.mark.parametrize(
    ("value", "refusal"),
    [
        (TEST_ACCOUNT_URL, None),
        (None, "KB_EXCHANGE_BLOB_URL: not set"),
        (
            "http://stkbexchangetest.blob.core.windows.net",
            "KB_EXCHANGE_BLOB_URL: scheme not https",
        ),
    ],
)
def test_the_url_of_the_account_is_read_without_the_identity_of_a_job(value, refusal):
    environ = {} if value is None else {"KB_EXCHANGE_BLOB_URL": value}

    assert find_exchange_blob_url_refusal(environ) == refusal


def test_the_mac_reaches_the_storage_by_the_account_of_az_login():
    assert isinstance(build_cli_credential(), AzureCliCredential)


def test_the_token_is_asked_for_the_identity_of_its_client_id_and_sent_to_the_storage(
    monkeypatch,
):
    set_identity_endpoint(monkeypatch)
    identity = FakeTransport(answer_token)
    storage = FakeTransport(answer_listing("a.md"))

    with (
        build_managed_identity_credential(
            TEST_CLIENT_ID, transport=identity
        ) as credential,
        open_container_client(
            TEST_ACCOUNT_URL, TEST_CONTAINER, credential, transport=storage
        ) as container,
    ):
        check_identity(credential)
        count_listed_blobs(container)

    # One request: the credential keeps the token it asked for the requests that follow.
    [token_request] = identity.adapter.requests
    assert parse_qs(urlsplit(token_request.url).query)["client_id"] == [TEST_CLIENT_ID]
    assert token_request.headers["X-IDENTITY-HEADER"] == TEST_IDENTITY_HEADER
    [listing] = storage.adapter.requests
    assert listing.headers["Authorization"] == f"Bearer {TEST_TOKEN}"


class FakeCredential:
    """A token for the storage, without the identity endpoint."""

    def get_token(self, *scopes, **kwargs):
        return AccessToken(TEST_TOKEN, 4102444800)


def list_with(handle):
    """Count the blobs of the container of the test, its storage answered by handle."""
    storage = FakeTransport(handle)
    with (
        naming_storage_errors(),
        open_container_client(
            TEST_ACCOUNT_URL, TEST_CONTAINER, FakeCredential(), transport=storage
        ) as container,
    ):
        return count_listed_blobs(container), storage.adapter.requests


def test_the_blobs_listed_are_counted_on_one_page_at_most():
    count, requests_sent = list_with(answer_listing("a.md", "b.md", "c.md"))

    assert count == 3
    [listing] = requests_sent
    parts = urlsplit(listing.url)
    assert parts.path == f"/{TEST_CONTAINER}"
    assert parse_qs(parts.query)["maxresults"] == [str(MAX_LISTED_BLOBS)]


def test_an_empty_container_counts_0():
    count, _ = list_with(answer_listing())

    assert count == 0


@pytest.mark.parametrize(
    ("handle", "description"),
    [
        (
            answer_forbidden_naming_the_blob,
            "exchange_storage_forbidden, HTTP 403, AuthenticationFailed",
        ),
        (
            answer_error(404, "ContainerNotFound", f"no {SPOTTED_BLOB_NAME}"),
            "exchange_storage_not_found, HTTP 404, ContainerNotFound",
        ),
        (
            answer_error(401, "InvalidAuthenticationInfo", f"no {SPOTTED_BLOB_NAME}"),
            "exchange_storage_unauthorized, HTTP 401, InvalidAuthenticationInfo",
        ),
        (
            answer_error(500, "InternalError", f"failed on {SPOTTED_BLOB_NAME}"),
            "exchange_storage_failed, HTTP 500, InternalError",
        ),
        # A code that is not a word of letters is left out: it is an input of the storage.
        (
            answer_error(403, f"Denied {SPOTTED_BLOB_NAME}", "denied"),
            "exchange_storage_forbidden, HTTP 403",
        ),
    ],
)
def test_an_error_of_the_storage_is_named_without_what_its_body_says(
    handle, description
):
    with pytest.raises(ExchangeStorageError) as raised:
        list_with(handle)

    assert str(raised.value) == description
    assert not names_the_spotted_blob(str(raised.value))
    # Nothing of the SDK is chained: a traceback would print its message.
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_an_error_of_the_storage_keeps_its_state_and_its_status():
    with pytest.raises(ExchangeStorageError) as raised:
        list_with(answer_forbidden_naming_the_blob)

    assert raised.value.state == "exchange_storage_forbidden"
    assert raised.value.http_status == 403


def test_a_storage_out_of_reach_is_unavailable():
    def refuse(request):
        raise requests.ConnectionError(
            f"no route to /{TEST_CONTAINER}/{SPOTTED_BLOB_NAME}"
        )

    with pytest.raises(ExchangeStorageError) as raised:
        list_with(refuse)

    assert str(raised.value) == "exchange_storage_unavailable"


def test_a_token_refused_by_the_identity_endpoint_is_no_token(monkeypatch):
    set_identity_endpoint(monkeypatch)
    identity = FakeTransport(answer_identity_refusal)

    with (
        pytest.raises(ExchangeStorageError) as raised,
        build_managed_identity_credential(
            TEST_CLIENT_ID, transport=identity
        ) as credential,
    ):
        check_identity(credential)

    # The identity, not the storage: refused or out of reach, which the class of the error of
    # azure-identity does not tell.
    assert str(raised.value) == "exchange_storage_no_token"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_an_identity_endpoint_out_of_reach_gives_no_token(monkeypatch):
    set_identity_endpoint(monkeypatch)

    def refuse(request):
        raise requests.ConnectionError("connection refused")

    with (
        pytest.raises(ExchangeStorageError) as raised,
        build_managed_identity_credential(
            TEST_CLIENT_ID, transport=FakeTransport(refuse)
        ) as credential,
    ):
        check_identity(credential)

    assert str(raised.value) == "exchange_storage_no_token"


@pytest.mark.parametrize(
    "handle",
    [
        answer_identity_with(500, "text/html", b"<html>Internal Server Error</html>"),
        answer_identity_with(200, "application/json", b"[]"),
        answer_identity_with(200, "application/json", b'"a token"'),
        # The same outage in JSON: azure-identity raises CredentialUnavailableError, an AzureError.
        answer_identity_with(500, "application/json", b'{"error": "unavailable"}'),
    ],
)
def test_an_identity_endpoint_that_answers_no_token_gives_no_token(monkeypatch, handle):
    set_identity_endpoint(monkeypatch)

    with (
        pytest.raises(ExchangeStorageError) as raised,
        build_managed_identity_credential(
            TEST_CLIENT_ID, transport=FakeTransport(handle)
        ) as credential,
    ):
        check_identity(credential)

    assert str(raised.value) == "exchange_storage_no_token"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_a_redirection_of_the_storage_is_not_followed():
    def redirect(request):
        return 307, {"Location": "https://elsewhere.example/smoke-test"}, b""

    with pytest.raises(ExchangeStorageError) as raised:
        list_with(redirect)

    assert str(raised.value) == "exchange_storage_failed, HTTP 307"


def test_the_transport_waits_as_the_sdk_of_the_storage_does_without_one():
    """The SDK sets its own timeouts only when it builds the transport (base_client.py)."""
    configuration = build_transport().connection_config

    assert configuration.timeout == 20
    assert configuration.read_timeout == 60


def test_the_transport_reads_neither_a_proxy_nor_a_certificate_of_the_environment():
    transport = build_transport()
    transport.open()
    try:
        assert transport.session.trust_env is False
    finally:
        transport.close()


def test_the_clients_take_the_transport_of_k_b_by_default(monkeypatch):
    built = []

    def keep_transport():
        transport = FakeTransport(answer_listing())
        built.append(transport)
        return transport

    monkeypatch.setattr(exchange_storage, "build_transport", keep_transport)

    with open_container_client(
        TEST_ACCOUNT_URL, TEST_CONTAINER, FakeCredential()
    ) as container:
        count_listed_blobs(container)
    set_identity_endpoint(monkeypatch)
    build_managed_identity_credential(TEST_CLIENT_ID)

    assert len(built) == 2
    assert len(built[0].adapter.requests) == 1
