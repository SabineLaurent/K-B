"""kb serve: serve the database, read only, with the keys and the settings of the environment."""

import logging
import os
from collections.abc import Mapping
from pathlib import Path

import uvicorn
from pydantic import SecretStr

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME
from k_b.core.api_keys import read_api_keys_or_refusal
from k_b.data_api.app import create_app
from k_b.data_api.settings import ServeSettings, read_serve_settings_or_refusal
from k_b.database.connection import DATABASE_FILE_NAME

logger = logging.getLogger(LOGGER_NAME)


def run_serve(data_dir: Path) -> int:
    """Serve the base with the keys and the settings of the environment; the log of uvicorn is
    the one of kb."""
    api_keys = read_api_keys(os.environ)
    settings = read_serve_settings(os.environ)
    if api_keys is None or settings is None:
        return ExitCode.NOT_STARTED
    logger.info("API clients loaded: %s", ", ".join(sorted(api_keys)))
    logger.info("API allowed hosts: %s", ", ".join(settings.allowed_hosts))
    uvicorn.run(
        create_app(
            data_dir / DATABASE_FILE_NAME,
            api_keys,
            allowed_hosts=settings.allowed_hosts,
        ),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )
    return ExitCode.SUCCEEDED


def read_serve_settings(environ: Mapping[str, str]) -> ServeSettings | None:
    """The host, the port and the hosts allowed of kb serve, or None after logging the variable
    refused, with its value quoted. Not set: the default of core/config.py."""
    settings_or_refusal = read_serve_settings_or_refusal(environ)
    if isinstance(settings_or_refusal, str):
        logger.error("%s", settings_or_refusal)
        return None
    return settings_or_refusal


def read_api_keys(environ: Mapping[str, str]) -> dict[str, SecretStr] | None:
    """The key of each client, by its name, or None after logging the variable refused: the
    name of the variable, never its value."""
    api_keys_or_refusal = read_api_keys_or_refusal(environ)
    if isinstance(api_keys_or_refusal, str):
        logger.error("%s", api_keys_or_refusal)
        return None
    return api_keys_or_refusal
