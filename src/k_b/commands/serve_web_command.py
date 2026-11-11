"""kb serve-web: serve the site, for its operator only, with the settings of the environment, and
wake the data API it reads at its start (docs/site-web.md)."""

import logging
import threading
from collections.abc import Mapping

import uvicorn

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.jobs.api_health import HealthCheckError, build_health_client, check_health
from k_b.web.app import create_app
from k_b.web.data_api_client import build_data_api_client
from k_b.web.settings import read_web_settings_or_refusal

logger = logging.getLogger(LOGGER_NAME)


def run_serve_web(environ: Mapping[str, str]) -> int:
    """Serve the site with the settings of the environment, uvicorn logging as kb; a setting
    refused, nothing is served."""
    settings = value_or_log_refusal(read_web_settings_or_refusal(environ))
    if settings is None:
        return ExitCode.NOT_STARTED
    # The access, never the object id.
    logger.info(
        "site access: %s",
        "off, no header checked, on the machine only"
        if settings.operator_id is None
        else "the object id of the operator checked in X-MS-CLIENT-PRINCIPAL-ID",
    )
    logger.info("site allowed hosts: %s", ", ".join(settings.allowed_hosts))
    base_url = settings.data_api.base_url
    # A lambda: a test replaces wake_data_api in the module.
    threading.Thread(
        target=lambda: wake_data_api(base_url), name="wake-data-api", daemon=True
    ).start()
    # Closed once uvicorn stops, on SIGTERM too.
    with build_data_api_client(settings.data_api) as data_api_client:
        uvicorn.run(
            create_app(
                operator_id=settings.operator_id,
                data_api_client=data_api_client,
                allowed_hosts=settings.allowed_hosts,
            ),
            host=settings.host,
            port=settings.port,
            log_config=None,
            access_log=False,
            # No header Server: uvicorn, which names the software (Opquast 2025, rule 213).
            server_header=False,
        )
    return ExitCode.SUCCEEDED


def wake_data_api(base_url: str) -> None:
    """One GET /health of the data API: at zero replicas, it wakes in 20 to 26 s (#414), while the
    operator signs in. Its state is logged, never the URL; a failure stops nothing."""
    try:
        with build_health_client(base_url) as http_client:
            check_health(http_client)
    except HealthCheckError as error:
        logger.warning("data API wake-up: %s", error)
        return
    logger.info("data API wake-up: health ok")
