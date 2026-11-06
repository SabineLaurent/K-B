"""The transfers of the jobs, by the identity of the job: the mirror of the clips from the container
clippings, and the publication of veille to the container watch; each returns its exit code."""

import logging
from pathlib import Path
from time import sleep

from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.run_log import LOGGER_NAME
from k_b.core.config import (
    CLIP_CHANGE_MARGIN,
    CLIP_MIRROR_CLOCK_SLACK,
    CLIPPINGS_CONTAINER,
    WATCH_CONTAINER,
    WATCH_DIR_NAME,
)
from k_b.etl.sources.clipping import CLIP_EXTENSION, CLIPPINGS_DIR_NAME
from k_b.items import CLIP_MAX_BYTES
from k_b.jobs.clip_mirror import ClippingsFolderRefusedError, ClipRules, mirror_clips
from k_b.jobs.exchange_storage import (
    ExchangeStorageError,
    ExchangeStorageSettings,
    build_managed_identity_credential,
    check_identity,
    naming_storage_errors,
    open_container_client,
)
from k_b.jobs.watch_publication import WatchFolderRefusedError, publish_watch

logger = logging.getLogger(LOGGER_NAME)

# The clips as etl/sources/clipping.py reads them, given to jobs/, which imports only core.
CLIP_RULES = ClipRules(extension=CLIP_EXTENSION, max_bytes=CLIP_MAX_BYTES)
# The wait after a copy: the margin of etl/sources/clipping.py, and the gap of the clocks.
CLIP_MIRROR_WAIT = CLIP_CHANGE_MARGIN + CLIP_MIRROR_CLOCK_SLACK


def mirror_the_clips(settings: ExchangeStorageSettings, vault_dir: Path) -> int:
    """Mirror the container clippings to the Clippings folder of the vault; once a clip is copied,
    wait CLIP_MIRROR_WAIT, so that the kb collect that follows reads it the same day."""
    try:
        with (
            naming_storage_errors(),
            build_managed_identity_credential(settings.client_id) as credential,
            open_container_client(
                settings.account_url, CLIPPINGS_CONTAINER, credential
            ) as container_client,
        ):
            check_identity(credential)
            result = mirror_clips(
                container_client, vault_dir / CLIPPINGS_DIR_NAME, CLIP_RULES
            )
    except (ExchangeStorageError, ClippingsFolderRefusedError) as error:
        logger.error("clip mirror: not run: %s", error)
        return ExitCode.FAILED
    if result.copied:
        # etl/sources/clipping.py leaves to the next collection a clip changed less than the margin
        # before it reads it: without the wait, a clip copied now is read today or tomorrow,
        # depending on how long the sources before it take.
        logger.info(
            "clip mirror: waiting %d seconds, so that kb collect reads the clips copied",
            CLIP_MIRROR_WAIT.total_seconds(),
        )
        sleep(CLIP_MIRROR_WAIT.total_seconds())
    return find_exit_code(has_failed=result.has_failed, has_done=result.has_done)


def publish_the_watch(settings: ExchangeStorageSettings, vault_dir: Path) -> int:
    """Publish veille of the vault to the container watch, without replacing a blob."""
    try:
        with (
            naming_storage_errors(),
            build_managed_identity_credential(settings.client_id) as credential,
            open_container_client(
                settings.account_url, WATCH_CONTAINER, credential
            ) as container_client,
        ):
            check_identity(credential)
            result = publish_watch(container_client, vault_dir / WATCH_DIR_NAME)
    except (ExchangeStorageError, WatchFolderRefusedError) as error:
        logger.error("watch publication: not run: %s", error)
        return ExitCode.FAILED
    return find_exit_code(has_failed=result.has_failed, has_done=result.has_done)
