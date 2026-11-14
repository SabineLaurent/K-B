"""The exchange storage: its settings, the identity of the job, the listing and its errors, named
without the text the storage answers."""

import io
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from azure.core.credentials import AccessToken
from azure.identity import AzureCliCredential
from exchange.storage_fakes import (
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    TEST_IDENTITY_HEADER,
    TEST_TOKEN,
    FakeBlob,
    FakeContainer,
    FakeTransport,
    answer_error,
    answer_forbidden_naming_the_blob,
    answer_identity_refusal,
    answer_identity_with,
    answer_listing,
    answer_token,
    names_the_spotted_blob,
    open_fake_container_client,
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
    download_listed_version,
    find_exchange_blob_url_refusal,
    naming_storage_errors,
    open_container_client,
    read_exchange_storage_settings_or_refusal,
)

TEST_CONTAINER = "smoke-test"
SENT_ON = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
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


def test_an_error_of_the_storage_keeps_its_code():
    with pytest.raises(ExchangeStorageError) as raised:
        list_with(answer_error(404, "ContainerNotFound", "no container"))

    assert raised.value.error_code == "ContainerNotFound"


def test_a_listing_past_its_wait_is_a_timeout():
    def wait_too_long(request):
        raise requests.ReadTimeout(f"read timed out on {SPOTTED_BLOB_NAME}")

    with pytest.raises(ExchangeStorageError) as raised:
        list_with(wait_too_long)

    assert str(raised.value) == "exchange_storage_timeout"


def test_the_transport_waits_the_timeouts_it_is_given():
    configuration = build_transport(
        connect_timeout_seconds=5, read_timeout_seconds=10
    ).connection_config

    assert configuration.timeout == 5
    assert configuration.read_timeout == 10


def test_a_client_without_retries_sends_a_failed_listing_once():
    storage = FakeTransport(answer_error(503, "ServerBusy", "busy"))

    with (
        pytest.raises(ExchangeStorageError),
        naming_storage_errors(),
        open_container_client(
            TEST_ACCOUNT_URL,
            TEST_CONTAINER,
            FakeCredential(),
            transport=storage,
            retry_total=0,
        ) as container,
    ):
        count_listed_blobs(container)

    assert len(storage.adapter.requests) == 1


def test_a_credential_without_retries_asks_a_failed_token_once(monkeypatch):
    set_identity_endpoint(monkeypatch)
    identity = FakeTransport(
        answer_identity_with(500, "application/json", b'{"error": "busy"}')
    )

    with (
        build_managed_identity_credential(
            TEST_CLIENT_ID, transport=identity, retry_total=0
        ) as credential,
        pytest.raises(ExchangeStorageError),
    ):
        check_identity(credential)

    assert len(identity.adapter.requests) == 1


# A bound of the tests, smaller than the blobs below.
TEST_MAX_BYTES = 8
LISTED_NAME = "tops/most_starred/2026-11-11.json"


def download_with(container, max_bytes=TEST_MAX_BYTES, change=None):
    """Download the one blob of container as listed; change is applied after the listing."""
    with open_fake_container_client(container) as container_client:
        [listed] = list(container_client.list_blobs())
        if change is not None:
            change(container)
        return download_listed_version(container_client, listed, max_bytes)


def test_the_version_listed_is_downloaded_by_its_etag():
    container = FakeContainer(
        TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"12345", SENT_ON)}
    )

    content = download_with(container)

    assert content == b"12345"
    [download] = [request for request in container.requests if request.method == "GET"][
        1:
    ]
    assert download.headers["If-Match"] == container.blobs[LISTED_NAME].etag


def test_at_most_one_byte_past_the_bound_is_asked():
    container = FakeContainer(
        TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"12345", SENT_ON)}
    )

    download_with(container)

    download = container.requests[-1]
    assert download.headers["x-ms-range"] == f"bytes=0-{TEST_MAX_BYTES}"


def test_a_blob_listed_empty_is_downloaded_whole():
    """A range on an empty blob is answered 416 (azure/storage/blob/_download.py)."""
    container = FakeContainer(TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"", SENT_ON)})

    assert download_with(container) == b""
    assert "x-ms-range" not in container.requests[-1].headers


def test_a_blob_compressed_is_given_as_stored():
    container = FakeContainer(
        TEST_CONTAINER,
        {LISTED_NAME: FakeBlob(b"\x1f\x8b\x08\x00", SENT_ON, content_encoding="gzip")},
    )

    assert download_with(container) == b"\x1f\x8b\x08\x00"


@pytest.mark.parametrize("received", [b"123", b"1234567890123"])
def test_a_length_received_other_than_the_size_listed_gives_none(received):
    container = FakeContainer(
        TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"12345", SENT_ON)}
    )

    def send_another_length(container):
        listed = container.blobs[LISTED_NAME]
        container.blobs[LISTED_NAME] = FakeBlob(received, SENT_ON, etag=listed.etag)

    assert download_with(container, change=send_another_length) is None


@pytest.mark.parametrize(
    "status_and_code", [(404, "BlobNotFound"), (412, "ConditionNotMet")]
)
def test_a_blob_removed_or_changed_since_the_listing_gives_none(status_and_code):
    container = FakeContainer(
        TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"12345", SENT_ON)}
    )
    container.status_of_next_get[LISTED_NAME] = status_and_code

    assert download_with(container) is None


def test_a_container_removed_since_the_listing_raises_its_state():
    container = FakeContainer(
        TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"12345", SENT_ON)}
    )
    container.status_of_next_get[LISTED_NAME] = (404, "ContainerNotFound")

    with pytest.raises(ExchangeStorageError) as raised:
        download_with(container)

    assert raised.value.state == "exchange_storage_not_found"
    assert raised.value.error_code == "ContainerNotFound"


class BodyPastItsWait(io.RawIOBase):
    """A body whose read waits past its timeout, as a socket does (socket.timeout)."""

    def readable(self):
        return True

    def readinto(self, buffer):
        raise TimeoutError("read timed out")


def test_a_download_past_its_wait_on_its_body_is_a_timeout(monkeypatch):
    """The downloader tries 3 times, then wraps the timeout in an error without a status
    (azure/storage/blob/_download.py)."""
    monkeypatch.setattr("azure.storage.blob._download.time.sleep", lambda seconds: None)
    container = FakeContainer(
        TEST_CONTAINER, {LISTED_NAME: FakeBlob(b"12345", SENT_ON)}
    )
    answer = container.handle

    def wait_too_long_on_the_body(request):
        status, headers, body = answer(request)
        if request.method == "GET" and "comp=list" not in request.url:
            return (
                status,
                {**headers, "Content-Length": str(len(body))},
                BodyPastItsWait(),
            )
        return status, headers, body

    container.handle = wait_too_long_on_the_body

    with pytest.raises(ExchangeStorageError) as raised:
        download_with(container)

    assert raised.value.state == "exchange_storage_timeout"
