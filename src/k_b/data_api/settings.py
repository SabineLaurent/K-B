"""The settings kb serve-data reads: the host and the port it listens on, the hosts it answers, the
exchange storage it reads watch in."""

from collections.abc import Mapping
from dataclasses import dataclass

from k_b.core.api_settings import (
    find_allowed_hosts_refusal,
    find_host_refusal,
    find_port_refusal,
    split_allowed_hosts,
)
from k_b.core.config import DATA_API_ALLOWED_HOSTS, DATA_API_HOST, DATA_API_PORT
from k_b.exchange.storage import (
    CLIENT_ID_VARIABLE,
    EXCHANGE_BLOB_URL_VARIABLE,
    ExchangeStorageSettings,
    read_exchange_storage_settings_or_refusal,
)

# Where kb serve-data listens and the hosts it answers; not set: the defaults of core/config.py.
DATA_API_HOST_VARIABLE = "KB_DATA_API_HOST"
DATA_API_PORT_VARIABLE = "KB_DATA_API_PORT"
DATA_API_ALLOWED_HOSTS_VARIABLE = "KB_DATA_API_ALLOWED_HOSTS"


@dataclass(frozen=True)
class ServeSettings:
    host: str
    port: int
    allowed_hosts: tuple[str, ...]


def read_serve_settings_or_refusal(environ: Mapping[str, str]) -> ServeSettings | str:
    """The host, the port and the hosts allowed of kb serve-data, or why the variable is refused, its
    value quoted."""
    host = environ.get(DATA_API_HOST_VARIABLE, DATA_API_HOST)
    port = environ.get(DATA_API_PORT_VARIABLE, str(DATA_API_PORT))
    allowed_hosts_value = environ.get(DATA_API_ALLOWED_HOSTS_VARIABLE)
    # Split once: the list checked is the list served.
    allowed_hosts = (
        DATA_API_ALLOWED_HOSTS
        if allowed_hosts_value is None
        else split_allowed_hosts(allowed_hosts_value)
    )
    refusal = (
        find_host_refusal(DATA_API_HOST_VARIABLE, host)
        or find_port_refusal(DATA_API_PORT_VARIABLE, port)
        or find_allowed_hosts_refusal(DATA_API_ALLOWED_HOSTS_VARIABLE, allowed_hosts)
    )
    if refusal is not None:
        return refusal
    return ServeSettings(host=host, port=int(port), allowed_hosts=allowed_hosts)


@dataclass(frozen=True)
class WatchUnconfigured:
    """kb serve-data reads no watch: the variables not set."""

    variables: tuple[str, ...]


def read_watch_settings_or_refusal(
    environ: Mapping[str, str],
) -> ExchangeStorageSettings | WatchUnconfigured | str:
    """The settings of the exchange storage that watch is read in; unconfigured when a variable is
    not set, the tops then answering 503 and the items still served (the Mac, a sandbox); a
    refusal when both are set and one is malformed."""
    not_set = tuple(
        variable
        for variable in (EXCHANGE_BLOB_URL_VARIABLE, CLIENT_ID_VARIABLE)
        if not environ.get(variable)
    )
    if not_set:
        return WatchUnconfigured(not_set)
    return read_exchange_storage_settings_or_refusal(environ)
