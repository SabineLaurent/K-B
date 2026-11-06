"""The exchange storage of the jobs, Azure Blob Storage, reached by the managed identity of the job:
its settings, its clients, and its errors named without what the storage answers.

A blob is named by its path, the title of a clip for one (etl/sources/clipping.py): K-B never
writes it, and keeps the SDK, which logs the URL of a request at INFO, at ERROR
(commands/run_log.py)."""

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from azure.core.credentials import TokenCredential
from azure.core.exceptions import (
    AzureError,
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.core.pipeline.transport import RequestsTransport
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import ContainerClient

from k_b.core.config import (
    EXCHANGE_STORAGE_CONNECT_TIMEOUT_SECONDS,
    EXCHANGE_STORAGE_READ_TIMEOUT_SECONDS,
    MAX_LISTED_BLOBS,
)
from k_b.core.outbound import find_url_refusal

EXCHANGE_BLOB_URL_VARIABLE = "KB_EXCHANGE_BLOB_URL"
# The client id of the user-assigned identity of the job: without it, ManagedIdentityCredential asks
# for the system-assigned identity, which a job of K-B does not have.
CLIENT_ID_VARIABLE = "AZURE_CLIENT_ID"
# A bearer token goes over HTTPS only.
EXCHANGE_BLOB_SCHEMES = ("https",)
# A client id as Azure gives it: a GUID, without braces.
CLIENT_ID = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
# The scope of a token for Blob Storage.
STORAGE_SCOPE = "https://storage.azure.com/.default"
# The code of an error of Blob Storage (x-ms-error-code), a word of letters: an input of the
# storage, written in a log only when it matches.
ERROR_CODE = re.compile(r"[A-Za-z]{1,64}")

type ExchangeStorageState = Literal[
    "exchange_storage_unavailable",
    "exchange_storage_no_token",
    "exchange_storage_unauthorized",
    "exchange_storage_forbidden",
    "exchange_storage_not_found",
    "exchange_storage_failed",
]

# By status rather than by class: the SDK raises ClientAuthenticationError for a 403 whose code is
# AuthenticationFailed (azure/storage/blob/_shared/response_handlers.py).
STATE_BY_STATUS: dict[int, ExchangeStorageState] = {
    401: "exchange_storage_unauthorized",
    403: "exchange_storage_forbidden",
    404: "exchange_storage_not_found",
}


@dataclass(frozen=True)
class ExchangeStorageSettings:
    """The account of the exchange storage, and the identity of the job that reaches it."""

    account_url: str
    client_id: str


class ExchangeStorageError(Exception):
    """A request to the exchange storage that failed: its state, the HTTP status and the code of
    the error, never the message of the SDK, which may give the path of a blob."""

    def __init__(
        self,
        state: ExchangeStorageState,
        http_status: int | None = None,
        error_code: str | None = None,
    ) -> None:
        """Name the failure by its state, then its HTTP status and its code when known."""
        details: list[str] = [state]
        if http_status is not None:
            details.append(f"HTTP {http_status}")
        if error_code is not None:
            details.append(error_code)
        super().__init__(", ".join(details))
        self.state: ExchangeStorageState = state
        self.http_status = http_status


def read_exchange_storage_settings_or_refusal(
    environ: Mapping[str, str],
) -> ExchangeStorageSettings | str:
    """The settings of the exchange storage, or why a variable is refused; neither has a default:
    no local value exists for them."""
    account_url = environ.get(EXCHANGE_BLOB_URL_VARIABLE)
    if not account_url:
        return f"{EXCHANGE_BLOB_URL_VARIABLE}: not set"
    refusal = find_url_refusal(
        EXCHANGE_BLOB_URL_VARIABLE, account_url, EXCHANGE_BLOB_SCHEMES
    )
    if refusal is not None:
        return refusal
    client_id = environ.get(CLIENT_ID_VARIABLE)
    if not client_id:
        return f"{CLIENT_ID_VARIABLE}: not set"
    if not CLIENT_ID.fullmatch(client_id):
        return f"{CLIENT_ID_VARIABLE}: not a GUID"
    return ExchangeStorageSettings(account_url=account_url, client_id=client_id)


def build_transport() -> RequestsTransport:
    """The transport of the SDK: it reads neither a proxy nor a certificate of the environment, as
    open_http_client (core/outbound.py), and waits as the SDK of the storage does without one."""
    return RequestsTransport(
        use_env_settings=False,
        connection_timeout=EXCHANGE_STORAGE_CONNECT_TIMEOUT_SECONDS,
        read_timeout=EXCHANGE_STORAGE_READ_TIMEOUT_SECONDS,
    )


def build_managed_identity_credential(
    client_id: str, transport: RequestsTransport | None = None
) -> ManagedIdentityCredential:
    """The credential of the user-assigned identity of client_id."""
    return ManagedIdentityCredential(
        client_id=client_id, transport=transport or build_transport()
    )


def open_container_client(
    account_url: str,
    container_name: str,
    credential: TokenCredential,
    transport: RequestsTransport | None = None,
) -> ContainerClient:
    """A client of one container of the account, which follows no redirection."""
    return ContainerClient(
        account_url,
        container_name,
        credential=credential,
        transport=transport or build_transport(),
        permit_redirects=False,
    )


def check_identity(credential: TokenCredential) -> None:
    """Ask the token of the storage for the identity of the job, which the credential keeps for the
    requests that follow. Any failure is exchange_storage_no_token: the class of an error of
    azure-identity does not tell a refusal from an outage (a 500 in JSON is
    CredentialUnavailableError, as a client id it does not know), and none carries the HTTP status
    of the endpoint (azure-identity 1.27.0: 400, 401, 403, 404, seen on 2026-11-06; review of
    #412)."""
    try:
        credential.get_token(STORAGE_SCOPE)
    # ValueError and AttributeError: an answer that is not a JSON object (a 500 in HTML, a list),
    # which azure-identity does not turn into an AzureError.
    except (AzureError, ValueError, AttributeError):
        raise ExchangeStorageError("exchange_storage_no_token") from None


def count_listed_blobs(container_client: ContainerClient) -> int:
    """The blobs of the first page of the container, MAX_LISTED_BLOBS at most: their names are
    counted, never kept."""
    pages = container_client.list_blob_names(
        results_per_page=MAX_LISTED_BLOBS
    ).by_page()
    return sum(1 for _ in next(pages, ()))


@contextmanager
def naming_storage_errors() -> Iterator[None]:
    """Turn an error of the SDK into ExchangeStorageError; nothing of the SDK is chained, as a
    traceback would print its message."""
    try:
        yield
    except AzureError as error:
        raise describe_storage_error(error) from None


def describe_storage_error(error: AzureError) -> ExchangeStorageError:
    """The state, the status and the code of an error of the SDK."""
    if isinstance(error, HttpResponseError) and error.status_code is not None:
        state = STATE_BY_STATUS.get(error.status_code, "exchange_storage_failed")
        return ExchangeStorageError(state, error.status_code, read_error_code(error))
    if isinstance(error, ServiceRequestError | ServiceResponseError):
        return ExchangeStorageError("exchange_storage_unavailable")
    return ExchangeStorageError("exchange_storage_failed")


def read_error_code(error: HttpResponseError) -> str | None:
    """The code of the error, when it is a word of letters; the SDK of the storage sets it on the
    error it raises (azure/storage/blob/_shared/response_handlers.py), not azure-core."""
    code = getattr(error, "error_code", None)
    if not isinstance(code, str) or not ERROR_CODE.fullmatch(code):
        return None
    return code
