"""kb smoke-test: GET /health of both APIs, then the listing of the container of the test of the
exchange storage by the identity of the job, the proof that a job online reaches all three; only
counts are written."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from typing import NamedTuple

from k_b.ai_api.connectors.data_api_settings import (
    DATA_API_SCHEMES,
    DATA_API_URL_VARIABLE,
)
from k_b.commands.batch_summary import (
    describe_count,
    describe_duration,
    render_table,
)
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.core.config import AI_API_URL, DATA_API_URL, SMOKE_TEST_CONTAINER
from k_b.core.outbound import find_url_refusal
from k_b.jobs.api_health import HealthCheckError, build_health_client, check_health
from k_b.jobs.exchange_storage import (
    ExchangeStorageError,
    ExchangeStorageSettings,
    build_managed_identity_credential,
    check_identity,
    count_listed_blobs,
    naming_storage_errors,
    open_container_client,
    read_exchange_storage_settings_or_refusal,
)
from k_b.post.ai_api_client import AI_API_SCHEMES, AI_API_URL_VARIABLE

logger = logging.getLogger(LOGGER_NAME)

DATA_API_NAME = "data API"
AI_API_NAME = "AI API"
EXCHANGE_STORAGE_NAME = "exchange storage"
CHECK_PASSED = "ok"
CHECK_FAILED = "failed"
SUMMARY_HEADER = ("check", "result")
SUMMARY_TITLE = "Smoke test"


@dataclass(frozen=True)
class SmokeTestSettings:
    """The URLs of both APIs, and the exchange storage with the identity of the job."""

    data_api_url: str
    ai_api_url: str
    exchange_storage: ExchangeStorageSettings


class CheckResult(NamedTuple):
    """A check of kb smoke-test: what it reached, and its result as the summary shows it."""

    check: str
    result: str

    @property
    def has_passed(self) -> bool:
        """Whether the check passed: any result but failed."""
        return self.result != CHECK_FAILED


def run_smoke_test(environ: Mapping[str, str]) -> int:
    """Read the settings, then run each check, a failed one not stopping the others; nothing is
    checked while a setting is refused."""
    settings = value_or_log_refusal(read_smoke_test_settings_or_refusal(environ))
    if settings is None:
        return ExitCode.NOT_STARTED
    logger.info(
        "smoke test started: /health of 2 APIs, then the listing of %s",
        SMOKE_TEST_CONTAINER,
    )
    started = monotonic()
    results = [
        check_api(DATA_API_NAME, settings.data_api_url),
        check_api(AI_API_NAME, settings.ai_api_url),
        check_exchange_storage(settings.exchange_storage),
    ]
    # A count, at INFO: each failed check has its own line already.
    logger.info(
        "smoke test finished in %s: %d of %d checks passed",
        describe_duration(monotonic() - started),
        sum(1 for result in results if result.has_passed),
        len(results),
    )
    print(render_smoke_test_summary(results))
    # A blank line after the result, as for kb digest (decision of Sabine of 2026-10-29).
    print()
    if all(result.has_passed for result in results):
        return ExitCode.SUCCEEDED
    return ExitCode.FAILED


def read_smoke_test_settings_or_refusal(
    environ: Mapping[str, str],
) -> SmokeTestSettings | str:
    """The settings of kb smoke-test, or why a variable is refused: never a URL."""
    # Empty is not set, as for kb digest and the AI API.
    data_api_url = environ.get(DATA_API_URL_VARIABLE) or DATA_API_URL
    ai_api_url = environ.get(AI_API_URL_VARIABLE) or AI_API_URL
    refusal = find_url_refusal(
        DATA_API_URL_VARIABLE, data_api_url, DATA_API_SCHEMES
    ) or find_url_refusal(AI_API_URL_VARIABLE, ai_api_url, AI_API_SCHEMES)
    if refusal is not None:
        return refusal
    exchange_storage = read_exchange_storage_settings_or_refusal(environ)
    if isinstance(exchange_storage, str):
        return exchange_storage
    return SmokeTestSettings(data_api_url, ai_api_url, exchange_storage)


def check_api(name: str, base_url: str) -> CheckResult:
    """GET /health of the API at base_url."""
    try:
        with build_health_client(base_url) as http_client:
            check_health(http_client)
    except HealthCheckError as error:
        logger.error("%s: /health failed: %s", name, error)
        return CheckResult(name, CHECK_FAILED)
    logger.info("%s: /health answered", name)
    return CheckResult(name, CHECK_PASSED)


def check_exchange_storage(settings: ExchangeStorageSettings) -> CheckResult:
    """The token of the identity of the job, then the first page of the container of the test,
    counted."""
    try:
        with (
            naming_storage_errors(),
            build_managed_identity_credential(settings.client_id) as credential,
            open_container_client(
                settings.account_url, SMOKE_TEST_CONTAINER, credential
            ) as container_client,
        ):
            check_identity(credential)
            count = count_listed_blobs(container_client)
    except ExchangeStorageError as error:
        logger.error("%s: not listed: %s", EXCHANGE_STORAGE_NAME, error)
        return CheckResult(EXCHANGE_STORAGE_NAME, CHECK_FAILED)
    listed = describe_listed_blobs(count)
    logger.info("%s: %s", EXCHANGE_STORAGE_NAME, listed)
    return CheckResult(EXCHANGE_STORAGE_NAME, listed)


def describe_listed_blobs(count: int) -> str:
    """1 blob listed in smoke-test, or 3 blobs."""
    return f"{describe_count(count, 'blob')} listed in {SMOKE_TEST_CONTAINER}"


def render_smoke_test_summary(results: list[CheckResult]) -> str:
    """The summary after the end line of the log: a row per check, with its result."""
    table = render_table([SUMMARY_HEADER, *[(r.check, r.result) for r in results]])
    # Underlined, the title of the block, as for kb digest (decision of Sabine of 2026-10-29).
    return "\n".join(["", SUMMARY_TITLE, "-" * len(SUMMARY_TITLE), *table])
