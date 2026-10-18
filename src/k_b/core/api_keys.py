"""The key of each client of the data API: one variable KB_API_KEY_<CLIENT> per client
(docs/specs-api.md, "Accès par clé"), read by kb serve.
"""

import re
from collections.abc import Mapping

from pydantic import SecretStr

from k_b.core.config import API_KEY_CHARACTERS, MIN_API_KEY_LENGTH
from k_b.core.quoting import quote_value

API_KEY_VARIABLE_PREFIX = "KB_API_KEY_"
CLIENT_NAME = re.compile(r"[A-Z0-9_]+")


def read_api_keys_or_refusal(environ: Mapping[str, str]) -> dict[str, SecretStr] | str:
    """The key of each client, by its name, or why the variable is refused: the name of the
    variable, never its value."""
    variables = sorted(
        name for name in environ if name.startswith(API_KEY_VARIABLE_PREFIX)
    )
    if not variables:
        return f"no API key: set {API_KEY_VARIABLE_PREFIX}<CLIENT>"
    api_keys: dict[str, SecretStr] = {}
    variable_by_key: dict[str, str] = {}
    for variable in variables:
        key = environ[variable]
        refusal = find_api_key_refusal(variable, key, variable_by_key)
        if refusal is not None:
            return refusal
        variable_by_key[key] = variable
        api_keys[variable.removeprefix(API_KEY_VARIABLE_PREFIX)] = SecretStr(key)
    return api_keys


def find_api_key_refusal(
    variable: str, key: str, variable_by_key: Mapping[str, str]
) -> str | None:
    """Why the variable of a client is refused, or None; variable_by_key holds the keys already
    read. The variable is quoted: its name comes from the environment."""
    client_name = variable.removeprefix(API_KEY_VARIABLE_PREFIX)
    if not CLIENT_NAME.fullmatch(client_name):
        return f"{quote_value(variable)}: client name empty or not [A-Z0-9_]+"
    if len(key) < MIN_API_KEY_LENGTH:
        return (
            f"{quote_value(variable)}: key of {len(key)} characters,"
            f" minimum {MIN_API_KEY_LENGTH}"
        )
    if not API_KEY_CHARACTERS.fullmatch(key):
        return f"{quote_value(variable)}: key with a character outside [A-Za-z0-9_-]"
    if key in variable_by_key:
        return (
            f"{quote_value(variable_by_key[key])} and {quote_value(variable)}: same key"
        )
    return None
