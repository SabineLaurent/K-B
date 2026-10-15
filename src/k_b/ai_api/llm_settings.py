"""The settings of the model, read from the environment: the provider, its URL, its model, its key.

No default for the provider, its URL nor its model (ADR of 2026-10-15, "Appel du modèle"): a
default replay would give digests made up without saying it, and a default provider would send the
watch to a service nobody chose. Without them, the AI API does not start (fail closed).
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr

from k_b.core.config import LLM_REASONING_EFFORT, LLM_REPLAY_BASE_URL
from k_b.core.quoting import quote_value

logger = logging.getLogger(__name__)

PROVIDER_VARIABLE = "KB_LLM_PROVIDER"
BASE_URL_VARIABLE = "KB_LLM_BASE_URL"
MODEL_VARIABLE = "KB_LLM_MODEL"
API_KEY_VARIABLE = "KB_LLM_API_KEY"
REASONING_EFFORT_VARIABLE = "KB_LLM_REASONING_EFFORT"
REPLAY_FILE_VARIABLE = "KB_LLM_REPLAY_FILE"

type LlmProvider = Literal["openai_compatible", "replay"]
PROVIDERS: tuple[LlmProvider, ...] = ("openai_compatible", "replay")
# The model of the replay, in the metrics: no deployment answers.
REPLAY_MODEL = "replay"
# A deployment name of Azure, a model of OpenAI or of Mistral; quoted in a log as it is.
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")
# Printable ASCII without space: the key goes into an HTTP header as it is.
API_KEY_CHARACTERS = re.compile(r"[!-~]+")


@dataclass(frozen=True)
class LlmSettings:
    provider: LlmProvider
    base_url: str
    model: str
    # None for the replay, which sends no key.
    api_key: SecretStr | None
    reasoning_effort: Literal["none"] | None
    replay_file: Path | None


def read_llm_settings(environ: Mapping[str, str]) -> LlmSettings | None:
    """The settings of the model, or None after logging the variable refused; logs the provider
    and the model chosen, never the URL nor the key."""
    settings_or_refusal = read_settings_or_refusal(environ)
    if isinstance(settings_or_refusal, str):
        logger.error("%s", settings_or_refusal)
        return None
    logger.info(
        "LLM provider %s, model %s",
        settings_or_refusal.provider,
        settings_or_refusal.model,
    )
    return settings_or_refusal


def read_settings_or_refusal(environ: Mapping[str, str]) -> LlmSettings | str:
    provider = environ.get(PROVIDER_VARIABLE)
    if not provider:
        return f"{PROVIDER_VARIABLE}: not set, {' or '.join(PROVIDERS)}"
    reasoning_effort = environ.get(REASONING_EFFORT_VARIABLE)
    if reasoning_effort is not None and reasoning_effort != "none":
        return f"{REASONING_EFFORT_VARIABLE}: {quote_value(reasoning_effort)} not none"
    effort: Literal["none"] | None = (
        "none" if reasoning_effort else LLM_REASONING_EFFORT
    )
    if provider == "replay":
        return read_replay_settings(environ, effort)
    if provider == "openai_compatible":
        return read_provider_settings(environ, effort)
    return f"{PROVIDER_VARIABLE}: {quote_value(provider)} not {' nor '.join(PROVIDERS)}"


def read_replay_settings(
    environ: Mapping[str, str], reasoning_effort: Literal["none"] | None
) -> LlmSettings | str:
    replay_file = environ.get(REPLAY_FILE_VARIABLE)
    if not replay_file:
        return (
            f"{REPLAY_FILE_VARIABLE}: not set, required by {PROVIDER_VARIABLE}=replay"
        )
    return LlmSettings(
        provider="replay",
        base_url=LLM_REPLAY_BASE_URL,
        model=REPLAY_MODEL,
        api_key=None,
        reasoning_effort=reasoning_effort,
        replay_file=Path(replay_file),
    )


def read_provider_settings(
    environ: Mapping[str, str], reasoning_effort: Literal["none"] | None
) -> LlmSettings | str:
    for variable in (BASE_URL_VARIABLE, MODEL_VARIABLE, API_KEY_VARIABLE):
        if not environ.get(variable):
            return f"{variable}: not set, required by {PROVIDER_VARIABLE}=openai_compatible"
    base_url = environ[BASE_URL_VARIABLE]
    model = environ[MODEL_VARIABLE]
    api_key = environ[API_KEY_VARIABLE]
    refusal = (
        find_base_url_refusal(base_url)
        or find_model_refusal(model)
        or find_api_key_refusal(api_key)
    )
    if refusal is not None:
        return refusal
    return LlmSettings(
        provider="openai_compatible",
        base_url=base_url,
        model=model,
        api_key=SecretStr(api_key),
        reasoning_effort=reasoning_effort,
        replay_file=None,
    )


def find_base_url_refusal(base_url: str) -> str | None:
    """Why the URL is refused, or None. The URL is never quoted: a URL refused may carry a key
    (`https://user:key@host`, `?api-key=…`)."""
    try:
        parts = urlsplit(base_url)
        has_user_information = parts.username is not None or parts.password is not None
    except ValueError:
        return f"{BASE_URL_VARIABLE}: not a URL"
    if parts.scheme != "https":
        return f"{BASE_URL_VARIABLE}: scheme not https"
    if not parts.hostname:
        return f"{BASE_URL_VARIABLE}: no host"
    if has_user_information:
        return f"{BASE_URL_VARIABLE}: with user information"
    if parts.query or parts.fragment or "?" in base_url or "#" in base_url:
        return f"{BASE_URL_VARIABLE}: with a query or a fragment"
    return None


def find_model_refusal(model: str) -> str | None:
    if MODEL_NAME.fullmatch(model):
        return None
    return f"{MODEL_VARIABLE}: {quote_value(model)} not {MODEL_NAME.pattern}"


def find_api_key_refusal(api_key: str) -> str | None:
    """Why the key is refused, or None; the key is never quoted."""
    if API_KEY_CHARACTERS.fullmatch(api_key):
        return None
    return f"{API_KEY_VARIABLE}: a character outside printable ASCII, or a space"
