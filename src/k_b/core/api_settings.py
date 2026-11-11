"""Where kb serve-data, kb serve-ai and kb serve-web listen, the host and the port, each read by its
variable, the hosts kb serve-data and kb serve-web answer, and whether the APIs serve their
documentation."""

import ipaddress
import re
from collections.abc import Mapping
from typing import Literal

from k_b.core.quoting import quote_value

DEPLOYMENT_ENVIRONMENT_VARIABLE = "KB_DEPLOYMENT_ENVIRONMENT"
type DeploymentEnvironment = Literal["sandbox", "production"]
DEPLOYMENT_ENVIRONMENTS: tuple[DeploymentEnvironment, ...] = ("sandbox", "production")
# Where an API serves its OpenAPI, which its /docs reads.
OPENAPI_PATH = "/openapi.json"

# A host name in lowercase, without * nor port: TrustedHostMiddleware compares the Host received
# as it is (starlette/middleware/trustedhost.py), and an entry of this form has nothing to escape
# in the log.
ALLOWED_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")
# Digits only: int() would also read " 8000", "+8000" and "8_000".
PORT_DIGITS = re.compile(r"[0-9]{1,5}")
PORT_NUMBERS = range(1, 65536)


def find_host_refusal(variable: str, host: str) -> str | None:
    """Why the host is refused, or None. An IPv4 address only: uvicorn binds an empty host to
    every interface, and a client's IPv6 Host keeps brackets ([::1]) no allowed host can name."""
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return f"{variable}: {quote_value(host)} not an IPv4 address"
    return None


def find_port_refusal(variable: str, port: str) -> str | None:
    if PORT_DIGITS.fullmatch(port) and int(port) in PORT_NUMBERS:
        return None
    return (
        f"{variable}: {quote_value(port)} not an integer"
        f" from {PORT_NUMBERS.start} to {PORT_NUMBERS.stop - 1}"
    )


def split_allowed_hosts(allowed_hosts: str) -> tuple[str, ...]:
    return tuple(entry.strip() for entry in allowed_hosts.split(","))


def find_allowed_hosts_refusal(
    variable: str, allowed_hosts: tuple[str, ...]
) -> str | None:
    """Why the hosts allowed are refused, or None: TrustedHostMiddleware would serve any host for
    a *."""
    # A value empty or made of spaces gives one empty entry.
    if allowed_hosts == ("",):
        return f"{variable}: empty, set the hosts separated by commas"
    for position, entry in enumerate(allowed_hosts, start=1):
        where = f"{variable}: entry {position} of {len(allowed_hosts)}"
        if not entry:
            return f"{where} empty"
        if "*" in entry:
            return f"{where} {quote_value(entry)} with '*', name each host"
        if not ALLOWED_HOST.fullmatch(entry):
            return f"{where} {quote_value(entry)} not a lowercase host name"
    return None


def is_sandbox(environ: Mapping[str, str]) -> bool:
    """Whether KB_DEPLOYMENT_ENVIRONMENT is sandbox, written as is."""
    return environ.get(DEPLOYMENT_ENVIRONMENT_VARIABLE) == "sandbox"


def read_openapi_url(environ: Mapping[str, str]) -> str | None:
    """The path of the OpenAPI in the sandbox; None serves neither it nor /docs, whatever else the
    variable holds, or nothing: a value forgotten shows nothing (decision of Sabine of 2026-11-04)."""
    if is_sandbox(environ):
        return OPENAPI_PATH
    return None
