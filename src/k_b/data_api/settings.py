"""The settings kb serve reads: the host and the port it listens on, the hosts it answers. The
client of the data API has its own, ai_api/connectors/data_api_settings.py.

Not set: the local defaults of core/config.py (.claude/rules/poc.md, rule 2).
"""

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass

from k_b.core.config import DATA_API_ALLOWED_HOSTS, DATA_API_HOST, DATA_API_PORT
from k_b.core.quoting import quote_value

# Where kb serve listens and the hosts it answers; not set: the defaults of core/config.py.
DATA_API_HOST_VARIABLE = "KB_DATA_API_HOST"
DATA_API_PORT_VARIABLE = "KB_DATA_API_PORT"
DATA_API_ALLOWED_HOSTS_VARIABLE = "KB_DATA_API_ALLOWED_HOSTS"
# Digits only: int() would also read " 8000", "+8000" and "8_000".
PORT_DIGITS = re.compile(r"[0-9]{1,5}")
PORT_NUMBERS = range(1, 65536)
# A host name in lowercase, without * nor port: TrustedHostMiddleware compares the Host received
# as it is (starlette/middleware/trustedhost.py), and an entry of this form has nothing to escape
# in the log.
ALLOWED_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")


@dataclass(frozen=True)
class ServeSettings:
    host: str
    port: int
    allowed_hosts: tuple[str, ...]


def read_serve_settings_or_refusal(environ: Mapping[str, str]) -> ServeSettings | str:
    """The host, the port and the hosts allowed of kb serve, or why the variable is refused, with
    its value quoted. Not set: the default of core/config.py."""
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
        find_host_refusal(host)
        or find_port_refusal(port)
        or find_allowed_hosts_refusal(allowed_hosts)
    )
    if refusal is not None:
        return refusal
    return ServeSettings(host=host, port=int(port), allowed_hosts=allowed_hosts)


def find_host_refusal(host: str) -> str | None:
    """Why the host is refused, or None. An IPv4 address only: uvicorn would bind an empty host
    to every interface, and the Host of a client in IPv6 keeps its brackets ([::1]), which no
    allowed host can name."""
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return f"{DATA_API_HOST_VARIABLE}: {quote_value(host)} not an IPv4 address"
    return None


def find_port_refusal(port: str) -> str | None:
    if PORT_DIGITS.fullmatch(port) and int(port) in PORT_NUMBERS:
        return None
    return (
        f"{DATA_API_PORT_VARIABLE}: {quote_value(port)} not an integer"
        f" from {PORT_NUMBERS.start} to {PORT_NUMBERS.stop - 1}"
    )


def split_allowed_hosts(allowed_hosts: str) -> tuple[str, ...]:
    """The entries of the list, separated by commas, without the spaces around each."""
    return tuple(entry.strip() for entry in allowed_hosts.split(","))


def find_allowed_hosts_refusal(allowed_hosts: tuple[str, ...]) -> str | None:
    """Why the hosts allowed are refused, or None: TrustedHostMiddleware would serve any host for
    a * (docs/specs-api.md, API8)."""
    # A value empty or made of spaces gives one empty entry.
    if allowed_hosts == ("",):
        return f"{DATA_API_ALLOWED_HOSTS_VARIABLE}: empty, set the hosts separated by commas"
    for position, entry in enumerate(allowed_hosts, start=1):
        where = f"{DATA_API_ALLOWED_HOSTS_VARIABLE}: entry {position} of {len(allowed_hosts)}"
        if not entry:
            return f"{where} empty"
        if "*" in entry:
            return f"{where} {quote_value(entry)} with '*', name each host"
        if not ALLOWED_HOST.fullmatch(entry):
            return f"{where} {quote_value(entry)} not a lowercase host name"
    return None
