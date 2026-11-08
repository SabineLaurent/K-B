"""kb digest and kb smoke-test on both APIs served for real, by uvicorn on 127.0.0.1: the chain of
the digests from kb to the AI API, then to the data API of the test base, on the replay of the
model, without a key of a provider nor a network outside the machine."""

import json
import secrets
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import NamedTuple

import pytest
import uvicorn
from ai_api.test_digest_router import (
    AGENT_CLAIM,
    REQUEST_TIME,
    SECURITY_CLAIM,
    TEST_SUBJECTS,
    VALID_STEPS,
    WINDOW_DAYS,
)
from commands.cli_helpers import list_sheets
from fastapi import FastAPI
from jobs.storage_fakes import (
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    FakeTransport,
    answer_listing,
    answer_token,
    remove_online_variables,
    set_identity_endpoint,
)
from pydantic import SecretStr

from k_b import cli
from k_b.ai_api.app import create_app
from k_b.ai_api.connectors.data_api_settings import DataApiSettings
from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.connectors.llm_settings import read_llm_settings_or_refusal
from k_b.ai_api.connectors.metrics_export import build_resource
from k_b.ai_api.connectors.trace_export import TraceExport
from k_b.ai_api.dependencies import read_request_time
from k_b.ai_api.observability.metric_instruments import ModelMetrics
from k_b.commands import digest_command, smoke_test_command
from k_b.core.config import DIGEST_CLIENT
from k_b.data_api.app import create_app as create_data_app
from k_b.jobs.exchange_storage import (
    build_managed_identity_credential,
    open_container_client,
)

# The client of the data API that the AI API is, as kb serve-ai reads KB_DATA_API_KEY_AI_DIGEST.
DATA_API_CLIENT = "AI_DIGEST"
# The title of vulnerability 3 in the test base: only the data API gives it to the sheet.
SECURITY_SOURCE_TITLE = "Apple Multiple Products Out-of-Bounds Write Vulnerability"
SERVER_START_SECONDS = 10


class LiveApis(NamedTuple):
    """The base URLs of both APIs served, and the key kb digest sends to the AI API."""

    data_api_url: str
    ai_api_url: str
    digest_key: str


@contextmanager
def serving(app: FastAPI) -> Iterator[str]:
    """The app served by uvicorn in a thread, on a free port of 127.0.0.1; its base URL given."""
    listening = socket.create_server(("127.0.0.1", 0))
    port = listening.getsockname()[1]
    # Not in the main thread: uvicorn sets no signal handler, pytest keeps its own.
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listening]}, daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + SERVER_START_SECONDS
        while not server.started:
            assert thread.is_alive(), "uvicorn stopped before it served"
            assert time.monotonic() < deadline, "uvicorn did not start in time"
            time.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(SERVER_START_SECONDS)
        listening.close()


def create_ai_app(replay_file, data_api_url, data_api_key):
    """The AI API as kb serve-ai builds it, on the replay of replay_file and the data API at
    data_api_url, its export off; its clock set at REQUEST_TIME, so that its default window falls
    on the test base."""
    llm_settings = read_llm_settings_or_refusal(
        {"KB_LLM_PROVIDER": "replay", "KB_LLM_REPLAY_FILE": str(replay_file)}
    )
    assert not isinstance(llm_settings, str), llm_settings
    resource = build_resource(None)
    digest_key = secrets.token_urlsafe(32)
    app = create_app(
        {DIGEST_CLIENT: SecretStr(digest_key)},
        llm_settings,
        DataApiSettings(base_url=data_api_url, api_key=SecretStr(data_api_key)),
        GithubSettings(token=SecretStr(f"github_pat_{secrets.token_hex(41)}")),
        TEST_SUBJECTS,
        WINDOW_DAYS,
        ModelMetrics.from_settings(None, resource),
        TraceExport.from_settings(None, resource),
    )
    app.dependency_overrides[read_request_time] = lambda: REQUEST_TIME
    return app, digest_key


@pytest.fixture
def live_apis(items_database, tmp_path):
    """Both APIs served: the data API on the test base, the AI API on the replay of VALID_STEPS."""
    replay_file = tmp_path / "replay.json"
    replay_file.write_text(json.dumps(VALID_STEPS), "utf-8")
    data_api_key = secrets.token_urlsafe(32)
    data_app = create_data_app(
        items_database, {DATA_API_CLIENT: SecretStr(data_api_key)}
    )
    with serving(data_app) as data_api_url:
        ai_app, digest_key = create_ai_app(replay_file, data_api_url, data_api_key)
        with serving(ai_app) as ai_api_url:
            yield LiveApis(data_api_url, ai_api_url, digest_key)


@pytest.fixture
def digest_environment(monkeypatch, data_and_vault_dirs, live_apis):
    """kb digest on the AI API served, with its key, the subjects of the tests and the day of
    the request."""
    monkeypatch.setenv("KB_AI_API_URL", live_apis.ai_api_url)
    monkeypatch.setenv("KB_AI_API_KEY_KB_DIGEST", live_apis.digest_key)
    monkeypatch.setattr(digest_command, "DIGEST_SUBJECTS", TEST_SUBJECTS)
    monkeypatch.setattr(digest_command, "read_today", REQUEST_TIME.date)
    return data_and_vault_dirs


def test_digest_writes_the_sheets_through_the_ai_api_and_the_data_api(
    digest_environment, capsys
):
    _, vault_dir = digest_environment

    exit_code = cli.main(["digest"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert list_sheets(vault_dir) == [
        "veille/agent_tools/2026-10-08.md",
        "veille/research/2026-10-08.md",
        "veille/security_alerts/2026-10-08.md",
    ]
    security_sheet = (vault_dir / "veille/security_alerts/2026-10-08.md").read_text(
        "utf-8"
    )
    assert SECURITY_CLAIM["text"] in security_sheet
    assert SECURITY_SOURCE_TITLE in security_sheet
    agent_sheet = (vault_dir / "veille/agent_tools/2026-10-08.md").read_text("utf-8")
    assert AGENT_CLAIM["text"] in agent_sheet
    output = capsys.readouterr().out
    assert "Window: 2026-09-24 → 2026-10-08, 10 items read" in output
    assert "Model: replay" in output


@pytest.fixture
def smoke_test_environment(monkeypatch, tmp_path, live_apis):
    """kb smoke-test on both APIs served; only the identity and the exchange storage are
    simulated."""
    remove_online_variables(monkeypatch)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_DATA_API_URL", live_apis.data_api_url)
    monkeypatch.setenv("KB_AI_API_URL", live_apis.ai_api_url)
    monkeypatch.setenv("KB_EXCHANGE_BLOB_URL", TEST_ACCOUNT_URL)
    monkeypatch.setenv("AZURE_CLIENT_ID", TEST_CLIENT_ID)
    set_identity_endpoint(monkeypatch)
    monkeypatch.setattr(
        smoke_test_command,
        "build_managed_identity_credential",
        partial(
            build_managed_identity_credential, transport=FakeTransport(answer_token)
        ),
    )
    monkeypatch.setattr(
        smoke_test_command,
        "open_container_client",
        partial(
            open_container_client,
            transport=FakeTransport(answer_listing(SPOTTED_BLOB_NAME)),
        ),
    )


def test_smoke_test_reaches_the_health_of_both_apis_served(
    smoke_test_environment, capsys
):
    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    output = capsys.readouterr().out
    assert "data API          ok" in output
    assert "AI API            ok" in output
