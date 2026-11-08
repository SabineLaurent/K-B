"""The sandbox of the alerts of the model: requests to the AI API on the replay, whose measures are
sent to the real OTLP endpoint, labelled sandbox, one test per alert; skipped without the endpoint
and the headers.

Run by make sandbox-alerts (documentation/monitoring_pour_docu.md), with KB_OTLP_ENDPOINT and
KB_OTLP_HEADERS of .env.e2e_test; the environment is sandbox whatever the terminal gives. Each test
is one process of the AI API, with its own service.instance.id, as after a wake online; its alert
is read in Grafana Cloud."""

import os
import secrets
import time

import pytest
from ai_api.test_digest_router import (
    AGENT_CLAIM,
    INVALID_OUTPUT,
    REQUEST_TIME,
    SECURITY_CLAIM,
    TEST_SUBJECTS,
    VALID_STEPS,
    WINDOW_DAYS,
    classified,
    read_metric_lines,
    written,
)
from fastapi.testclient import TestClient
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import MetricExportResult
from pydantic import SecretStr

from k_b.ai_api.app import create_app
from k_b.ai_api.connectors import metrics_export
from k_b.ai_api.connectors.data_api_settings import DataApiSettings
from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.connectors.llm_replay import REPLAY_STEPS
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.connectors.metrics_export import (
    build_resource,
    read_metrics_export_settings_or_refusal,
)
from k_b.ai_api.connectors.trace_export import TraceExport
from k_b.ai_api.dependencies import open_data_api_client, read_request_time
from k_b.ai_api.observability.metric_instruments import ModelMetrics
from k_b.core.api_settings import DEPLOYMENT_ENVIRONMENT_VARIABLE
from k_b.core.config import (
    DIGEST_CLIENT,
    LLM_REPLAY_BASE_URL,
    METRICS_EXPORT_INTERVAL_SECONDS,
)
from k_b.data_api.app import create_app as create_data_app

SANDBOX = "sandbox"
OK_STATUS = 200
# The status of a request whose classification fails (tests/ai_api/test_digest_router.py).
FAILED_MODEL_STATUS = 502
# Versions in no item of the test base: the fidelity finds one fact of five in this claim, three of
# seven in the request.
INVENTED_VERSIONS_CLAIM = {
    "text": "Claude Code publie v2.1.287, v2.1.299, v2.1.300, v2.1.301 et v2.1.302.",
    "item_ids": ["i6"],
    "facts": [
        {"value": version, "item_id": "i6"}
        for version in ("v2.1.287", "v2.1.299", "v2.1.300", "v2.1.301", "v2.1.302")
    ],
}
LOW_FIDELITY_STEPS = [
    classified(),
    written(SECURITY_CLAIM),
    written(AGENT_CLAIM, INVENTED_VERSIONS_CLAIM),
    written(),
]
# The budget of the alert on the cost of the model, in USD over 7 days (choice of Sabine of the
# 2026-11-08), and enough input tokens on the classification for one request to cost more, at the
# prices of core/config.py.
BUDGET_USD = 1
OVER_BUDGET_INPUT_TOKENS = 10_000_000
OVER_BUDGET_STEPS = [
    classified() | {"prompt_tokens": OVER_BUDGET_INPUT_TOKENS},
    *VALID_STEPS[1:],
]
# Requests further apart than an export: the series has a point before the second one, so that
# Grafana shows whether increase() counts the first.
SPACED_REQUESTS = 3
REQUEST_SPACING_SECONDS = METRICS_EXPORT_INTERVAL_SECONDS + 5


def read_sandbox_export_settings():
    """The export of the terminal, its environment set to sandbox; skipped without the endpoint and
    the headers, which are never quoted."""
    settings = read_metrics_export_settings_or_refusal(
        {**os.environ, DEPLOYMENT_ENVIRONMENT_VARIABLE: SANDBOX}
    )
    if settings is None:
        pytest.skip("KB_OTLP_ENDPOINT and KB_OTLP_HEADERS not set")
    assert not isinstance(settings, str), settings
    return settings


def record_export_results(monkeypatch):
    """The result of each export of the SDK, kept in the list returned."""
    results = []

    class RecordingExporter(OTLPMetricExporter):
        def export(self, metrics_data, timeout_millis=10_000, **kwargs):
            result = super().export(metrics_data, timeout_millis, **kwargs)
            results.append(result)
            return result

    monkeypatch.setattr(metrics_export, "OTLPMetricExporter", RecordingExporter)
    return results


def build_ai_app(steps, client_key, data_api_key, metrics):
    return create_app(
        {DIGEST_CLIENT: SecretStr(client_key)},
        LlmSettings(
            provider="replay",
            base_url=LLM_REPLAY_BASE_URL,
            model="replay",
            api_key=None,
            reasoning_effort=None,
            replay_steps=tuple(REPLAY_STEPS.validate_python(steps)),
        ),
        DataApiSettings(base_url="http://localhost", api_key=SecretStr(data_api_key)),
        GithubSettings(token=SecretStr(f"github_pat_{secrets.token_hex(41)}")),
        TEST_SUBJECTS,
        WINDOW_DAYS,
        metrics,
        # The traces are tried by Sabine on kb serve-ai (docs/fiches-veille.md, "Traces").
        TraceExport.from_settings(None, build_resource(SANDBOX)),
    )


def run_sandbox_requests(
    items_database, monkeypatch, record_property, steps, request_count=1
):
    """The statuses of request_count requests on the replay of steps, one app for them all, its
    measures exported when it stops; every export must succeed."""
    settings = read_sandbox_export_settings()
    results = record_export_results(monkeypatch)
    data_api_key = secrets.token_urlsafe(32)
    client_key = secrets.token_urlsafe(32)
    metrics = ModelMetrics.from_settings(settings, build_resource(SANDBOX))
    app = build_ai_app(steps, client_key, data_api_key, metrics)
    statuses = []
    with TestClient(
        create_data_app(items_database, {"AI_DIGEST": SecretStr(data_api_key)}),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {data_api_key}"},
    ) as data_api:
        app.dependency_overrides[open_data_api_client] = lambda: data_api
        app.dependency_overrides[read_request_time] = lambda: REQUEST_TIME
        # Leaving the block ends the lifespan: the last export.
        with TestClient(app) as client:
            for index in range(request_count):
                if index:
                    time.sleep(REQUEST_SPACING_SECONDS)
                response = client.post(
                    "/digests",
                    json={"window_days": WINDOW_DAYS},
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                statuses.append(response.status_code)
    record_property("environment", settings.environment)
    record_property("statuses", ", ".join(str(status) for status in statuses))
    record_property("export_results", ", ".join(result.name for result in results))
    assert settings.environment == SANDBOX
    assert results
    assert all(result is MetricExportResult.SUCCESS for result in results)
    return statuses


@pytest.mark.e2e
def test_valid_requests_spaced_beyond_an_export_reach_the_sandbox(
    items_database, monkeypatch, record_property
):
    statuses = run_sandbox_requests(
        items_database, monkeypatch, record_property, VALID_STEPS, SPACED_REQUESTS
    )

    assert statuses == [OK_STATUS] * SPACED_REQUESTS


@pytest.mark.e2e
def test_an_invalid_output_reaches_the_sandbox(
    items_database, monkeypatch, record_property, capsys
):
    statuses = run_sandbox_requests(
        items_database, monkeypatch, record_property, [INVALID_OUTPUT, INVALID_OUTPUT]
    )

    assert statuses == [FAILED_MODEL_STATUS]
    [line] = read_metric_lines(capsys)
    assert line["outcome"] == "llm_invalid_output"


@pytest.mark.e2e
def test_a_low_fidelity_reaches_the_sandbox(
    items_database, monkeypatch, record_property, capsys
):
    statuses = run_sandbox_requests(
        items_database, monkeypatch, record_property, LOW_FIDELITY_STEPS
    )

    assert statuses == [OK_STATUS]
    lines = read_metric_lines(capsys)
    facts_found = sum(line["facts_found"] or 0 for line in lines)
    facts_checked = sum(line["facts_checked"] or 0 for line in lines)
    record_property("fidelity", f"{facts_found}/{facts_checked}")
    assert (facts_found, facts_checked) == (3, 7)


@pytest.mark.e2e
def test_a_cost_over_the_budget_reaches_the_sandbox(
    items_database, monkeypatch, record_property, capsys
):
    statuses = run_sandbox_requests(
        items_database, monkeypatch, record_property, OVER_BUDGET_STEPS
    )

    assert statuses == [OK_STATUS]
    cost = sum(line["cost_estimated"] for line in read_metric_lines(capsys))
    record_property("cost_usd", f"{cost:.6f}")
    assert cost > BUDGET_USD
