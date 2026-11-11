"""The exchange storage, Azure Blob Storage, reached by the managed identity of a job or of the data
API, or on the Mac by the account of az login: its settings, its clients, the download of a blob as
listed, and its errors named without what the storage answers.

A blob is named by its path, the title of a clip for one (etl/sources/clipping.py): K-B never
writes it, and keeps the SDK, which logs the URL of a request at INFO, at ERROR
(commands/run_log.py)."""

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from azure.core import MatchConditions
from azure.core.credentials import TokenCredential
from azure.core.exceptions import (
    AzureError,
    HttpResponseError,
    ServiceRequestError,
    ServiceRequestTimeoutError,
    ServiceResponseError,
    ServiceResponseTimeoutError,
)
from azure.core.pipeline.transport import RequestsTransport
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from azure.storage.blob import BlobProperties, ContainerClient

from k_b.core.config import (
    EXCHANGE_STORAGE_CONNECT_TIMEOUT_SECONDS,
    EXCHANGE_STORAGE_READ_TIMEOUT_SECONDS,
    GUID,
    MAX_LISTED_BLOBS,
)
from k_b.core.outbound import find_url_refusal

EXCHANGE_BLOB_URL_VARIABLE = "KB_EXCHANGE_BLOB_URL"
# The client id of the user-assigned identity of the job or of the data API: without it,
# ManagedIdentityCredential asks for the system-assigned identity, which neither has.
CLIENT_ID_VARIABLE = "AZURE_CLIENT_ID"
# A bearer token goes over HTTPS only.
EXCHANGE_BLOB_SCHEMES = ("https",)
# The scope of a token for Blob Storage.
STORAGE_SCOPE = "https://storage.azure.com/.default"
# The code of an error of Blob Storage (x-ms-error-code), a word of letters: an input of the
# storage, written in a log only when it matches.
ERROR_CODE = re.compile(r"[A-Za-z]{1,64}")

type ExchangeStorageState = Literal[
    "exchange_storage_unavailable",
    "exchange_storage_timeout",
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
# A download answered 412, or 404 for its blob: the blob was changed or removed since the listing. A
# 404 ContainerNotFound is not: the container itself is gone.
STATUS_CHANGED_SINCE_LISTING = 412
BLOB_NOT_FOUND = (404, "BlobNotFound")
# The errors of a wait past its timeout, on the connection or on the answer (azure-core 1.41.0).
TIMEOUT_ERRORS = (ServiceRequestTimeoutError, ServiceResponseTimeoutError)


@dataclass(frozen=True)
class ExchangeStorageSettings:
    """The account of the exchange storage, and the identity of the job or of the data API that
    reaches it."""

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
        self.error_code = error_code


def read_exchange_storage_settings_or_refusal(
    environ: Mapping[str, str],
) -> ExchangeStorageSettings | str:
    """The settings of the exchange storage, or why a variable is refused; neither has a default:
    no local value exists for them."""
    refusal = find_exchange_blob_url_refusal(environ)
    if refusal is not None:
        return refusal
    account_url = environ[EXCHANGE_BLOB_URL_VARIABLE]
    client_id = environ.get(CLIENT_ID_VARIABLE)
    if not client_id:
        return f"{CLIENT_ID_VARIABLE}: not set"
    if not GUID.fullmatch(client_id):
        return f"{CLIENT_ID_VARIABLE}: not a GUID"
    return ExchangeStorageSettings(account_url=account_url, client_id=client_id)


def find_exchange_blob_url_refusal(environ: Mapping[str, str]) -> str | None:
    """Why the URL of the account is refused, or None; read by a job and by the Mac."""
    account_url = environ.get(EXCHANGE_BLOB_URL_VARIABLE)
    if not account_url:
        return f"{EXCHANGE_BLOB_URL_VARIABLE}: not set"
    return find_url_refusal(
        EXCHANGE_BLOB_URL_VARIABLE, account_url, EXCHANGE_BLOB_SCHEMES
    )


def build_transport(
    connect_timeout_seconds: float = EXCHANGE_STORAGE_CONNECT_TIMEOUT_SECONDS,
    read_timeout_seconds: float = EXCHANGE_STORAGE_READ_TIMEOUT_SECONDS,
) -> RequestsTransport:
    """The transport of the SDK: it reads neither a proxy nor a certificate of the environment, as
    open_http_client (core/outbound.py), and waits as the SDK of the storage does without one,
    unless given shorter waits."""
    return RequestsTransport(
        use_env_settings=False,
        connection_timeout=connect_timeout_seconds,
        read_timeout=read_timeout_seconds,
    )


def build_managed_identity_credential(
    client_id: str,
    transport: RequestsTransport | None = None,
    retry_total: int | None = None,
) -> ManagedIdentityCredential:
    """The credential of the user-assigned identity of client_id; retry_total, when given, replaces
    the retries of azure-identity, which hands it to its RetryPolicy (_internal/pipeline.py)."""
    return ManagedIdentityCredential(
        client_id=client_id,
        transport=transport or build_transport(),
        **retry_options(retry_total),
    )


def build_cli_credential() -> AzureCliCredential:
    """The credential of the Entra account az login opened on the Mac, in the tenant of that
    account: az is run for each token, found on the PATH, and keeps none."""
    return AzureCliCredential()


def open_container_client(
    account_url: str,
    container_name: str,
    credential: TokenCredential,
    transport: RequestsTransport | None = None,
    retry_total: int | None = None,
) -> ContainerClient:
    """A client of one container of the account, which follows no redirection; retry_total, when
    given, replaces the retries of the SDK (ExponentialRetry, 3)."""
    return ContainerClient(
        account_url,
        container_name,
        credential=credential,
        transport=transport or build_transport(),
        permit_redirects=False,
        **retry_options(retry_total),
    )


def retry_options(retry_total: int | None) -> dict[str, Any]:
    """The keyword of the retries, left out when not given: the default stays that of the SDK."""
    return {} if retry_total is None else {"retry_total": retry_total}


def check_identity(credential: TokenCredential) -> None:
    """Ask the token of the storage for the identity, which ManagedIdentityCredential keeps for the
    requests that follow; AzureCliCredential asks az again at the first request. Any failure is
    exchange_storage_no_token: the class of an error of azure-identity does not tell a refusal from
    an outage (a 500 in JSON is CredentialUnavailableError, as a client id it does not know), and
    none carries the HTTP status of the endpoint (azure-identity 1.27.0: 400, 401, 403, 404, seen on
    2026-11-06; review of #412)."""
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


def download_listed_version(
    container_client: ContainerClient, blob: BlobProperties, max_bytes: int
) -> bytes | None:
    """The bytes of the version listed, as stored: never decompressed, as a blob sent with
    Content-Encoding: gzip would pass any bound once inflated. None when the blob was removed or
    changed since the listing, or when the length received is not the size listed.

    At most max_bytes + 1 bytes are asked: without a range, the SDK reads up to 32 MiB at once
    (max_single_get_size). A blob listed empty is asked whole, as a range on it is answered 416."""
    try:
        with naming_storage_errors():
            downloader = container_client.download_blob(
                blob.name,
                offset=0 if blob.size else None,
                length=max_bytes + 1 if blob.size else None,
                etag=blob.etag,
                match_condition=MatchConditions.IfNotModified,
                decompress=False,
            )
            content = downloader.readall()
    except ExchangeStorageError as error:
        if is_changed_since_listing(error):
            return None
        raise
    if len(content) != blob.size:
        return None
    return content


def is_changed_since_listing(error: ExchangeStorageError) -> bool:
    """Whether the download was refused because its blob was changed or removed."""
    return error.http_status == STATUS_CHANGED_SINCE_LISTING or (
        (error.http_status, error.error_code) == BLOB_NOT_FOUND
    )


@contextmanager
def naming_storage_errors() -> Iterator[None]:
    """Turn an error of the SDK into ExchangeStorageError; nothing of the SDK is chained, as a
    traceback would print its message."""
    try:
        yield
    except AzureError as error:
        raise describe_storage_error(error) from None


def describe_storage_error(error: AzureError) -> ExchangeStorageError:
    """The state, the status and the code of an error of the SDK; a timeout the downloader wraps
    in an error without a status (azure/storage/blob/_download.py) is still a timeout."""
    if isinstance(error, TIMEOUT_ERRORS) or isinstance(
        error.inner_exception, TIMEOUT_ERRORS
    ):
        return ExchangeStorageError("exchange_storage_timeout")
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
