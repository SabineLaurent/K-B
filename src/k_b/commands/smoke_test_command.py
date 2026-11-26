"""kb smoke-test: GET /health of both APIs and their probes without key, GET /health/database of the
data API, then the listing of the container of the test of the exchange storage by the identity of
the job, the proof that a job online reaches all three, that the data API reads its base and that
both APIs refuse what they must; only counts are written."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import monotonic
from typing import NamedTuple

import httpx2

from k_b.ai_api.connectors.data_api_settings import (
    DATA_API_URL_VARIABLE,
)
from k_b.commands.batch_summary import (
    describe_count,
    describe_duration,
    render_table,
)
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.core.api_health import DATABASE_HEALTH_PATH
from k_b.core.api_settings import is_sandbox
from k_b.core.config import AI_API_URL, DATA_API_URL, SMOKE_TEST_CONTAINER
from k_b.core.outbound import find_internal_api_url_refusal
from k_b.exchange.storage import (
    ExchangeStorageError,
    ExchangeStorageSettings,
    build_managed_identity_credential,
    check_identity,
    count_listed_blobs,
    naming_storage_errors,
    open_container_client,
    read_exchange_storage_settings_or_refusal,
)
from k_b.jobs.api_health import HealthCheckError, build_health_client, check_health
from k_b.jobs.api_probes import (
    AI_API_ROUTE_WITH_KEY,
    DATA_API_ROUTE_WITH_KEY,
    Probe,
    ProbeError,
    build_probe_client,
    list_probes,
    send_probe,
)
from k_b.post.ai_api_client import AI_API_URL_VARIABLE

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
    """The URLs of both APIs, whether they run in the sandbox, and the exchange storage with the
    identity of the job."""

    data_api_url: str
    ai_api_url: str
    is_sandbox: bool
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
        "smoke test started: /health and the probes without key of 2 APIs, %s of the data"
        " API, then the listing of %s",
        DATABASE_HEALTH_PATH,
        SMOKE_TEST_CONTAINER,
    )
    started = monotonic()
    # The /health of an API first: it wakes the API before its probes.
    results = [
        check_api(DATA_API_NAME, settings.data_api_url),
        *probe_api(
            DATA_API_NAME,
            settings.data_api_url,
            list_probes(DATA_API_ROUTE_WITH_KEY, settings.is_sandbox),
        ),
        check_data_api_database(settings.data_api_url),
        check_api(AI_API_NAME, settings.ai_api_url),
        *probe_api(
            AI_API_NAME,
            settings.ai_api_url,
            list_probes(AI_API_ROUTE_WITH_KEY, settings.is_sandbox),
        ),
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
    refusal = find_internal_api_url_refusal(
        DATA_API_URL_VARIABLE, data_api_url, environ
    ) or find_internal_api_url_refusal(AI_API_URL_VARIABLE, ai_api_url, environ)
    if refusal is not None:
        return refusal
    exchange_storage = read_exchange_storage_settings_or_refusal(environ)
    if isinstance(exchange_storage, str):
        return exchange_storage
    return SmokeTestSettings(
        data_api_url, ai_api_url, is_sandbox(environ), exchange_storage
    )


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


def check_data_api_database(base_url: str) -> CheckResult:
    """GET /health/database of the data API at base_url, by a client with the waits of a probe:
    its /health has woken it."""
    check = f"{DATA_API_NAME} GET {DATABASE_HEALTH_PATH}"
    try:
        with build_probe_client(base_url) as http_client:
            check_health(http_client, DATABASE_HEALTH_PATH)
    except HealthCheckError as error:
        logger.error("%s: %s failed: %s", DATA_API_NAME, DATABASE_HEALTH_PATH, error)
        return CheckResult(check, CHECK_FAILED)
    logger.info("%s: %s answered", DATA_API_NAME, DATABASE_HEALTH_PATH)
    return CheckResult(check, CHECK_PASSED)


def probe_api(name: str, base_url: str, probes: Sequence[Probe]) -> list[CheckResult]:
    """Each probe without key of the API at base_url, a failed one not stopping the others."""
    with build_probe_client(base_url) as http_client:
        return [check_probe(name, http_client, probe) for probe in probes]


def check_probe(name: str, http_client: httpx2.Client, probe: Probe) -> CheckResult:
    """A probe of the API, as a row of the summary: data API GET /items, 401 as expected."""
    request = f"{probe.method} {probe.path}"
    check = f"{name} {request}"
    try:
        send_probe(http_client, probe)
    except ProbeError as error:
        logger.error("%s: %s without key failed: %s", name, request, error)
        return CheckResult(check, CHECK_FAILED)
    logger.info("%s: %s without key answered %d", name, request, probe.expected_status)
    return CheckResult(check, f"{probe.expected_status} as expected")


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
