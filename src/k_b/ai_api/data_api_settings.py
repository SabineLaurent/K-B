"""The settings of the data API the AI API reads the watch from: its URL and the key of the client
AI_DIGEST (docs/fiches-veille.md, "Le parcours d'une demande").

The key is read from KB_API_KEY_AI_DIGEST, the variable kb serve reads for this client: one value
for both sides. It has no default (a secret: fail closed); the URL has the local one of kb serve
(.claude/rules/poc.md, rule 2).
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SecretStr

from k_b.ai_api.outbound import find_url_refusal
from k_b.core.config import API_KEY_CHARACTERS, DATA_API_URL, MIN_API_KEY_LENGTH

logger = logging.getLogger(__name__)

DATA_API_URL_VARIABLE = "KB_DATA_API_URL"
DATA_API_KEY_VARIABLE = "KB_API_KEY_AI_DIGEST"
# No TLS before Azure Container Apps (docs/specs-api.md, OWASP API8): http on the machine and in
# the compose network.
DATA_API_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class DataApiSettings:
    base_url: str
    api_key: SecretStr


def read_data_api_settings(environ: Mapping[str, str]) -> DataApiSettings | None:
    """The settings of the data API, or None after logging the variable refused, never its
    value."""
    settings_or_refusal = read_settings_or_refusal(environ)
    if isinstance(settings_or_refusal, str):
        logger.error("%s", settings_or_refusal)
        return None
    return settings_or_refusal


def read_settings_or_refusal(environ: Mapping[str, str]) -> DataApiSettings | str:
    # Empty is not set, as for the settings of the model.
    base_url = environ.get(DATA_API_URL_VARIABLE) or DATA_API_URL
    api_key = environ.get(DATA_API_KEY_VARIABLE)
    if not api_key:
        return f"{DATA_API_KEY_VARIABLE}: not set"
    refusal = find_url_refusal(
        DATA_API_URL_VARIABLE, base_url, DATA_API_SCHEMES
    ) or find_api_key_refusal(api_key)
    if refusal is not None:
        return refusal
    return DataApiSettings(base_url=base_url, api_key=SecretStr(api_key))


def find_api_key_refusal(api_key: str) -> str | None:
    """Why the key is refused, by the rule kb serve applies, or None; the key is never quoted."""
    if len(api_key) < MIN_API_KEY_LENGTH:
        return (
            f"{DATA_API_KEY_VARIABLE}: key of {len(api_key)} characters,"
            f" minimum {MIN_API_KEY_LENGTH}"
        )
    if not API_KEY_CHARACTERS.fullmatch(api_key):
        return (
            f"{DATA_API_KEY_VARIABLE}: key with a character outside"
            f" {API_KEY_CHARACTERS.pattern}"
        )
    return None
