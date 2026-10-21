"""Where an API of K-B listens, kb serve and kb serve-ai: the host and the port, checked by one
rule, each read by its variable (.claude/rules/poc.md, rule 2)."""

import ipaddress
import re

from k_b.core.quoting import quote_value

# Digits only: int() would also read " 8000", "+8000" and "8_000".
PORT_DIGITS = re.compile(r"[0-9]{1,5}")
PORT_NUMBERS = range(1, 65536)


def find_host_refusal(variable: str, host: str) -> str | None:
    """Why the host is refused, or None. An IPv4 address only: uvicorn would bind an empty host
    to every interface, and the Host of a client in IPv6 keeps its brackets ([::1]), which no
    allowed host can name."""
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
