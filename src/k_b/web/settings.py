"""The settings kb serve-web reads: where it listens, the hosts it answers, and whose header it
checks; the check is off on the machine only, outside Azure Container Apps (docs/site-web.md,
"Réglages")."""

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass

from k_b.core.api_settings import (
    find_allowed_hosts_refusal,
    find_host_refusal,
    find_port_refusal,
    split_allowed_hosts,
)
from k_b.core.config import GUID, WEB_ALLOWED_HOSTS, WEB_HOST, WEB_PORT
from k_b.core.quoting import quote_value

# Where kb serve-web listens and the hosts it answers; not set: the defaults of core/config.py.
WEB_HOST_VARIABLE = "KB_WEB_HOST"
WEB_PORT_VARIABLE = "KB_WEB_PORT"
WEB_ALLOWED_HOSTS_VARIABLE = "KB_WEB_ALLOWED_HOSTS"
# entra, the default: each request but /health carries the object id of the operator, in the header
# Azure Container Apps sets once Microsoft Entra has signed her in; off: no header checked.
WEB_AUTH_VARIABLE = "KB_WEB_AUTH"
ENTRA_AUTH = "entra"
OFF_AUTH = "off"
# The object id of the operator in Microsoft Entra, the operatorObjectId of infra/main.bicep.
WEB_OPERATOR_ID_VARIABLE = "KB_WEB_OPERATOR_ID"
# Set by Azure Container Apps in each container of an app (Microsoft Learn, "Manage environment
# variables on Azure Container Apps", read on 2026-11-11): a fact of the platform, never a setting.
CONTAINER_APP_NAME_VARIABLE = "CONTAINER_APP_NAME"


@dataclass(frozen=True)
class WebSettings:
    host: str
    port: int
    allowed_hosts: tuple[str, ...]
    # In lowercase; None under KB_WEB_AUTH=off: no header checked.
    operator_id: str | None


def read_web_settings_or_refusal(environ: Mapping[str, str]) -> WebSettings | str:
    """The settings of kb serve-web, or why a variable is refused, its value quoted, but the
    object id."""
    host = environ.get(WEB_HOST_VARIABLE, WEB_HOST)
    port = environ.get(WEB_PORT_VARIABLE, str(WEB_PORT))
    allowed_hosts_value = environ.get(WEB_ALLOWED_HOSTS_VARIABLE)
    # Split once: the list checked is the list served.
    allowed_hosts = (
        WEB_ALLOWED_HOSTS
        if allowed_hosts_value is None
        else split_allowed_hosts(allowed_hosts_value)
    )
    refusal = (
        find_host_refusal(WEB_HOST_VARIABLE, host)
        or find_port_refusal(WEB_PORT_VARIABLE, port)
        or find_allowed_hosts_refusal(WEB_ALLOWED_HOSTS_VARIABLE, allowed_hosts)
    )
    if refusal is not None:
        return refusal
    access = read_access_or_refusal(environ, host)
    if isinstance(access, str):
        return access
    return WebSettings(
        host=host,
        port=int(port),
        allowed_hosts=allowed_hosts,
        operator_id=access.operator_id,
    )


@dataclass(frozen=True)
class OperatorAccess:
    # In lowercase; None under KB_WEB_AUTH=off: no header checked.
    operator_id: str | None


def read_access_or_refusal(
    environ: Mapping[str, str], host: str
) -> OperatorAccess | str:
    """The access KB_WEB_AUTH sets, read once, or why it is refused on this host, an IPv4
    address."""
    auth = environ.get(WEB_AUTH_VARIABLE, ENTRA_AUTH)
    is_loopback = ipaddress.IPv4Address(host).is_loopback
    is_in_container_apps = bool(environ.get(CONTAINER_APP_NAME_VARIABLE))
    if auth == OFF_AUTH:
        refusal = find_off_refusal(host, is_loopback, is_in_container_apps)
        return OperatorAccess(operator_id=None) if refusal is None else refusal
    if auth == ENTRA_AUTH:
        return read_entra_access_or_refusal(
            environ, host, is_loopback, is_in_container_apps
        )
    return (
        f"{WEB_AUTH_VARIABLE}: {quote_value(auth)} neither {ENTRA_AUTH} nor {OFF_AUTH}"
    )


def find_off_refusal(
    host: str, is_loopback: bool, is_in_container_apps: bool
) -> str | None:
    """Why no check is refused: off serves the site to any request, so on the machine only."""
    if is_in_container_apps:
        return (
            f"{WEB_AUTH_VARIABLE}: {OFF_AUTH} in Azure Container Apps"
            f" ({CONTAINER_APP_NAME_VARIABLE} set)"
        )
    if not is_loopback:
        return (
            f"{WEB_AUTH_VARIABLE}: {OFF_AUTH} with {WEB_HOST_VARIABLE} {quote_value(host)},"
            " not a loopback address"
        )
    return None


def read_entra_access_or_refusal(
    environ: Mapping[str, str], host: str, is_loopback: bool, is_in_container_apps: bool
) -> OperatorAccess | str:
    """The object id of the operator in lowercase, or why the check is refused: a GUID, never
    quoted; outside the machine, only Azure Container Apps keeps a client from sending the header
    itself."""
    operator_id = environ.get(WEB_OPERATOR_ID_VARIABLE)
    if not operator_id:
        return f"{WEB_OPERATOR_ID_VARIABLE}: not set"
    if not GUID.fullmatch(operator_id):
        return f"{WEB_OPERATOR_ID_VARIABLE}: not a GUID"
    if not is_loopback and not is_in_container_apps:
        return (
            f"{WEB_HOST_VARIABLE}: {quote_value(host)} not a loopback address outside Azure"
            f" Container Apps ({CONTAINER_APP_NAME_VARIABLE} not set): any device of the network"
            " could send the header of the operator"
        )
    return OperatorAccess(operator_id=operator_id.lower())
