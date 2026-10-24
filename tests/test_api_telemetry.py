"""The native OpenTelemetry of FastAPI is off in both APIs (core/api_telemetry.py, #162): with
FASTAPI_OTEL_AUTO_CONFIGURE=true, neither sets a global provider. In a subprocess: a global
provider is set once per process."""

import os
import subprocess
import sys

import pytest

# Builds the app, runs its lifespan and prints the class of the global tracer provider. The key
# and the base are made in the subprocess: none comes from the environment.
CHECK_APP = """
import secrets, sqlite3, sys, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from opentelemetry import trace
from pydantic import SecretStr
api = sys.argv[1]
if api == "data_api":
    from k_b.data_api.app import create_app
    app = create_app(Path(tempfile.mkdtemp()) / "k-b.db", {"T": SecretStr(secrets.token_urlsafe(32))})
else:
    from k_b.ai_api.app import create_app
    from k_b.ai_api.connectors.data_api_settings import DataApiSettings
    from k_b.ai_api.connectors.llm_settings import REPLAY_MODEL, LlmSettings
    from k_b.ai_api.metric_instruments import ModelMetrics
    from k_b.core.config import DIGEST_SUBJECTS, LLM_REPLAY_BASE_URL
    app = create_app(
        {},
        LlmSettings("replay", LLM_REPLAY_BASE_URL, REPLAY_MODEL, None, None, ()),
        DataApiSettings("http://127.0.0.1:8000", SecretStr("")),
        DIGEST_SUBJECTS,
        3,
        ModelMetrics.from_settings(None),
    )
with TestClient(app):
    pass
print(type(trace.get_tracer_provider()).__name__)
"""


@pytest.mark.parametrize("api", ["data_api", "ai_api"])
def test_auto_configure_sets_no_global_provider(api):
    result = subprocess.run(  # noqa: S603 — this interpreter, fixed arguments
        [sys.executable, "-c", CHECK_APP, api],
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "FASTAPI_OTEL_AUTO_CONFIGURE": "true",
            # Unreachable: nothing would leave even if a provider were set.
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9",
        },
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ProxyTracerProvider"
