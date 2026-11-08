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

from k_b import cli
from k_b.ai_api.connectors.data_api_settings import (
    DATA_API_KEY_VARIABLE,
    DATA_API_URL_VARIABLE,
)
from k_b.ai_api.connectors.github_settings import GITHUB_TOKEN_VARIABLE
from k_b.ai_api.connectors.llm_settings import PROVIDER_VARIABLE, REPLAY_FILE_VARIABLE
from k_b.ai_api.dependencies import read_request_time
from k_b.ai_api.settings import DIGEST_WINDOW_DAYS_VARIABLE
from k_b.commands import (
    digest_command,
    serve_ai_command,
    serve_data_command,
    smoke_test_command,
)
from k_b.jobs.exchange_storage import (
    build_managed_identity_credential,
    open_container_client,
)
from k_b.post.ai_api_client import AI_API_URL_VARIABLE, DIGEST_KEY_VARIABLE

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
        assert not thread.is_alive(), "uvicorn did not stop in time"
        listening.close()


def build_app_as_served(monkeypatch, run_command):
    """The app a kb serve command builds from its environment and gives uvicorn.run, which is
    not run."""
    apps = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: apps.append(app))
    assert run_command() == cli.ExitCode.SUCCEEDED
    [app] = apps
    return app


@pytest.fixture
def live_apis(monkeypatch, items_database, tmp_path):
    """Both APIs built by kb serve-data and kb serve-ai from their environment, then served: the
    data API on the test base, the AI API on the replay of VALID_STEPS. Two settings of the test
    only: the subjects of the tests, and the clock of the AI API at REQUEST_TIME, so that its
    window falls on the test base."""
    replay_file = tmp_path / "replay.json"
    replay_file.write_text(json.dumps(VALID_STEPS), "utf-8")
    data_api_key = secrets.token_urlsafe(32)
    data_app = build_app_as_served(
        monkeypatch,
        # The test base is the SQLite file of its folder, as in a data directory.
        partial(
            serve_data_command.run_serve_data,
            items_database.parent,
            {DATA_API_KEY_VARIABLE: data_api_key},
        ),
    )
    with serving(data_app) as data_api_url:
        digest_key = secrets.token_urlsafe(32)
        monkeypatch.setattr(serve_ai_command, "DIGEST_SUBJECTS", TEST_SUBJECTS)
        ai_environ = {
            DIGEST_KEY_VARIABLE: digest_key,
            PROVIDER_VARIABLE: "replay",
            REPLAY_FILE_VARIABLE: str(replay_file),
            DIGEST_WINDOW_DAYS_VARIABLE: str(WINDOW_DAYS),
            DATA_API_URL_VARIABLE: data_api_url,
            DATA_API_KEY_VARIABLE: data_api_key,
            # Read at the start, never sent: no route of the digests calls GitHub.
            GITHUB_TOKEN_VARIABLE: f"github_pat_{secrets.token_hex(41)}",
        }
        ai_app = build_app_as_served(
            monkeypatch, partial(serve_ai_command.run_serve_ai, ai_environ)
        )
        ai_app.dependency_overrides[read_request_time] = lambda: REQUEST_TIME
        with serving(ai_app) as ai_api_url:
            yield LiveApis(data_api_url, ai_api_url, digest_key)


@pytest.fixture
def digest_environment(monkeypatch, data_and_vault_dirs, live_apis):
    """kb digest on the AI API served, with its key, the subjects of the tests and the day of
    the request."""
    monkeypatch.setenv(AI_API_URL_VARIABLE, live_apis.ai_api_url)
    monkeypatch.setenv(DIGEST_KEY_VARIABLE, live_apis.digest_key)
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
    monkeypatch.setenv(DATA_API_URL_VARIABLE, live_apis.data_api_url)
    monkeypatch.setenv(AI_API_URL_VARIABLE, live_apis.ai_api_url)
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
