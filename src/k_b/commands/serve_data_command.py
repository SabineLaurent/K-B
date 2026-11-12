"""kb serve-data: serve the database, read only, and the tops of watch, with the keys and the settings
of the environment."""

import logging
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import uvicorn

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.core.api_keys import API_KEY_VARIABLE_PREFIX, read_api_keys_or_refusal
from k_b.core.api_settings import read_openapi_url
from k_b.core.config import DATA_API_QUERY_TIMEOUT_SECONDS
from k_b.data_api.app import create_app
from k_b.data_api.settings import (
    WatchUnconfigured,
    read_serve_settings_or_refusal,
    read_watch_settings_or_refusal,
)
from k_b.data_api.watch_reading import WatchReader, open_watch_reader
from k_b.database.engine import open_readers
from k_b.database.location import (
    UnreadableDatabaseUrlError,
    read_database_location_or_refusal,
)
from k_b.exchange.storage import ExchangeStorageSettings

logger = logging.getLogger(LOGGER_NAME)


def run_serve_data(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Serve the base the environment names with its keys and its settings, uvicorn logging as kb.

    On SIGTERM, uvicorn ends the requests under way, then raises the signal again: the process ends
    in uvicorn.run, and the system closes the connections of the pool, which hold no write."""
    api_keys = value_or_log_refusal(
        read_api_keys_or_refusal(environ, API_KEY_VARIABLE_PREFIX)
    )
    settings = value_or_log_refusal(read_serve_settings_or_refusal(environ))
    # Not value_or_log_refusal: mypy would join the two kinds of location into object.
    location = read_database_location_or_refusal(environ, data_dir)
    if isinstance(location, str):
        logger.error("%s", location)
        return ExitCode.NOT_STARTED
    watch_settings = read_watch_settings_or_refusal(environ)
    if isinstance(watch_settings, str):
        logger.error("%s", watch_settings)
        return ExitCode.NOT_STARTED
    if api_keys is None or settings is None:
        return ExitCode.NOT_STARTED
    logger.info("API clients loaded: %s", ", ".join(sorted(api_keys)))
    logger.info("API allowed hosts: %s", ", ".join(settings.allowed_hosts))
    if isinstance(watch_settings, WatchUnconfigured):
        logger.info(
            "watch unconfigured: %s not set; the tops answer 503 watch_unconfigured",
            watch_settings.variable,
        )
    try:
        with (
            open_readers(location, DATA_API_QUERY_TIMEOUT_SECONDS) as readers,
            open_watch(watch_settings) as watch,
        ):
            uvicorn.run(
                create_app(
                    readers,
                    api_keys,
                    allowed_hosts=settings.allowed_hosts,
                    openapi_url=read_openapi_url(environ),
                    query_timeout_seconds=DATA_API_QUERY_TIMEOUT_SECONDS,
                    watch=watch,
                ),
                host=settings.host,
                port=settings.port,
                log_config=None,
                access_log=False,
                # No header Server: uvicorn, which names the software (Opquast 2025, rule 213).
                server_header=False,
            )
    except UnreadableDatabaseUrlError as error:
        logger.error("%s", error)
        return ExitCode.NOT_STARTED
    return ExitCode.SUCCEEDED


def open_watch(
    settings: ExchangeStorageSettings | WatchUnconfigured,
) -> AbstractContextManager[WatchReader | None]:
    """The reader of watch, or none when unconfigured."""
    if isinstance(settings, WatchUnconfigured):
        return nullcontext()
    return open_watch_reader(settings)
