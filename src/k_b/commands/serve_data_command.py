"""kb serve-data: serve the database, read only, with the keys and the settings of the environment."""

import logging
import os
from pathlib import Path

import uvicorn

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.core.api_keys import API_KEY_VARIABLE_PREFIX, read_api_keys_or_refusal
from k_b.data_api.app import create_app
from k_b.data_api.settings import read_serve_settings_or_refusal
from k_b.database.connection import DATABASE_FILE_NAME

logger = logging.getLogger(LOGGER_NAME)


def run_serve_data(data_dir: Path) -> int:
    """Serve the base with the keys and the settings of the environment, uvicorn logging as kb."""
    api_keys = value_or_log_refusal(
        read_api_keys_or_refusal(os.environ, API_KEY_VARIABLE_PREFIX)
    )
    settings = value_or_log_refusal(read_serve_settings_or_refusal(os.environ))
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
