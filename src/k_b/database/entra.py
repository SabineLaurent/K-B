"""The token of the managed identity for its PostgreSQL base (Microsoft Entra), which libpq sends as
the password of a new connection: asked for at each one, never logged.

The transport and the client id are those of exchange/storage.py, written a second time
rather than shared: the base may not import exchange (conventions.md, rule 5)."""

from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.core.pipeline.transport import RequestsTransport
from azure.identity import ManagedIdentityCredential

from k_b.core.config import (
    DATABASE_TOKEN_CONNECT_TIMEOUT_SECONDS,
    DATABASE_TOKEN_READ_TIMEOUT_SECONDS,
)

# The scope of a token for Azure Database for PostgreSQL (Microsoft Learn, "Connect with managed
# identity", read on 2026-11-06).
POSTGRESQL_TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"  # noqa: S105 — a scope, not a token
# The state of a token the identity did not give.
DATABASE_NO_TOKEN = "database_no_token"  # noqa: S105 — a state, not a token


class EntraTokenError(Exception):
    """The managed identity gave no token for the base; never the text of azure-identity, which
    may quote what the endpoint answered."""


def build_identity_transport() -> RequestsTransport:
    """The transport of the request for a token: it reads neither a proxy nor a certificate of the
    environment, and waits for its own delays."""
    return RequestsTransport(
        use_env_settings=False,
        connection_timeout=DATABASE_TOKEN_CONNECT_TIMEOUT_SECONDS,
        read_timeout=DATABASE_TOKEN_READ_TIMEOUT_SECONDS,
    )


def build_database_credential(
    client_id: str, transport: RequestsTransport | None = None
) -> ManagedIdentityCredential:
    """The credential of the user-assigned identity of client_id; it keeps its token and asks for a
    new one before it expires."""
    return ManagedIdentityCredential(
        client_id=client_id, transport=transport or build_identity_transport()
    )


def fetch_database_token(credential: TokenCredential) -> str:
    """A token of the base for the identity of the credential.

    Any failure is database_no_token, as for the exchange storage (exchange/storage.py): the
    class of an error of azure-identity does not tell a refusal from an outage. ValueError and
    AttributeError: an answer that is not a JSON object, which azure-identity does not turn into an
    AzureError."""
    try:
        return credential.get_token(POSTGRESQL_TOKEN_SCOPE).token
    except (AzureError, ValueError, AttributeError):
        raise EntraTokenError(DATABASE_NO_TOKEN) from None
