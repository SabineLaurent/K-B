"""kb serve-web: serve the site, for its operator only, with the settings of the environment
(docs/site-web.md)."""

import logging
from collections.abc import Mapping

import uvicorn

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.web.app import create_app
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
    uvicorn.run(
        create_app(
            operator_id=settings.operator_id, allowed_hosts=settings.allowed_hosts
        ),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
        # No header Server: uvicorn, which names the software (Opquast 2025, rule 213).
        server_header=False,
    )
    return ExitCode.SUCCEEDED
