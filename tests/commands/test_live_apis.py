"""kb digest, kb trend-report and kb smoke-test on both APIs served for real, by uvicorn on
127.0.0.1: the chains of the digests and of the trend reports from kb to the AI API, then to the
data API of the test base, on the replay of the model and a simulated GitHub, without a key of a
provider nor a network outside the machine."""

import json
import secrets
import socket
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
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
from ai_api.test_trend_report_router import (
    REMOVED_SECTOR,
    SimulatedGithub,
    answer,
    writing,
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
from k_b.ai_api.dependencies import open_github_client, read_request_time
from k_b.ai_api.settings import DIGEST_WINDOW_DAYS_VARIABLE
from k_b.commands import (
    digest_command,
    serve_ai_command,
    serve_data_command,
    smoke_test_command,
    trend_report_command,
)
from k_b.exchange.storage import (
    build_managed_identity_credential,
    open_container_client,
)
from k_b.post import trend_report_client
from k_b.post.ai_api_client import AI_API_URL_VARIABLE, DIGEST_KEY_VARIABLE
from k_b.post.trend_report_client import TREND_REPORT_KEY_VARIABLE

# The title of vulnerability 3 in the test base: only the data API gives it to the sheet.
SECURITY_SOURCE_TITLE = "Apple Multiple Products Out-of-Bounds Write Vulnerability"
SERVER_START_SECONDS = 10


class LiveApis(NamedTuple):
    """The base URLs of both APIs served, and the keys kb digest and kb trend-report send to the
    AI API."""

    data_api_url: str
    ai_api_url: str
    digest_key: str
    trend_report_key: str


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
def replay_steps():
    """The steps the AI API replays: those of the digests, unless a test gives its own by
    parametrize."""
    return VALID_STEPS


def simulate_github_of(database_path):
    """The GitHub of the trend reports, serving a card for each repository of the trend table."""
    connection = sqlite3.connect(database_path)
    try:
        ids = dict(
            connection.execute("SELECT repository_name, repository_id FROM trend")
        )
    finally:
        connection.close()
    return SimulatedGithub(None, ids=ids)


@pytest.fixture
def live_apis(monkeypatch, items_database, tmp_path, replay_steps):
    """Both APIs built by kb serve-data and kb serve-ai from their environment, then served: the
    data API on the test base, the AI API on the replay of replay_steps. Three settings of the
    test only: the subjects of the tests; the clock of the AI API at REQUEST_TIME, so that the
    window of the digests falls on the test base (the trend reports date with it only the
    cautions of a card, and the card of the fixtures is of 2018); GitHub simulated on the
    repositories of the test base."""
    replay_file = tmp_path / "replay.json"
    replay_file.write_text(json.dumps(replay_steps), "utf-8")
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
        # A key per client: kb serve-ai refuses one key for two.
        trend_report_key = secrets.token_urlsafe(32)
        monkeypatch.setattr(serve_ai_command, "DIGEST_SUBJECTS", TEST_SUBJECTS)
        ai_environ = {
            DIGEST_KEY_VARIABLE: digest_key,
            TREND_REPORT_KEY_VARIABLE: trend_report_key,
            PROVIDER_VARIABLE: "replay",
            REPLAY_FILE_VARIABLE: str(replay_file),
            DIGEST_WINDOW_DAYS_VARIABLE: str(WINDOW_DAYS),
            DATA_API_URL_VARIABLE: data_api_url,
            DATA_API_KEY_VARIABLE: data_api_key,
            # Read at the start, never sent: GitHub is simulated below.
            GITHUB_TOKEN_VARIABLE: f"github_pat_{secrets.token_hex(41)}",
        }
        ai_app = build_app_as_served(
            monkeypatch, partial(serve_ai_command.run_serve_ai, ai_environ)
        )
        ai_app.dependency_overrides[read_request_time] = lambda: REQUEST_TIME
        ai_app.dependency_overrides[open_github_client] = simulate_github_of(
            items_database
        ).client
        with serving(ai_app) as ai_api_url:
            yield LiveApis(data_api_url, ai_api_url, digest_key, trend_report_key)


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


# The instant of kb trend-report: the client refuses a window after its day, and the latest of the
# test base is 2026-10-10.
TREND_REPORT_TIME = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
TREND_REPORT_SHEET = "veille/tendances/2026-10-10.md"
# The test base gives no criterion: the model chooses 2 of its 3 candidates by a subject of the
# tests alone, c2 then c1, and writes each one; the controls remove the sector of the second.
TREND_REPORT_STEPS = [
    answer(
        {"ref": "c2", "criteria": ["watch_subject"], "watch_subjects": ["agent_tools"]},
        {"ref": "c1", "criteria": ["watch_subject"], "watch_subjects": ["agent_tools"]},
    ),
    writing("c2"),
    writing("c1", sector=REMOVED_SECTOR),
]
# The card of the fixtures, served by the simulated GitHub for every repository.
CARD_FACTS = (
    "  Créé le 2018-12-08 ; Python ; MIT ; 104367 étoiles ; api, async, asyncio, fastapi,"
    " framework, json, json-schema, openapi, openapi3, pydantic, python, python-types, python3,"
    " redoc, rest, starlette, swagger, swagger-ui, uvicorn, web"
)
README_SUMMARY = "  D'après son README : Selon son auteur, FastAPI s'appuie sur Starlette et Pydantic."
PROMISE = "  Promesse : Il promet la high performance."
CHOSEN_SECTION = [
    "## Choisis par le modèle",
    "",
    "replay en a retenu 2 sur 3 candidats :",
    "",
    "- <https://github.com/storytold/photocraft> : sujet de la veille (agent_tools)",
    CARD_FACTS,
    "  Secteur : Framework web pour python.",
    README_SUMMARY,
    PROMISE,
    "- <https://github.com/morluto/rea> : sujet de la veille (agent_tools)",
    CARD_FACTS,
    "  Secteur : non retenu par les contrôles.",
    README_SUMMARY,
    PROMISE,
    "",
]


@pytest.fixture
def trend_report_environment(monkeypatch, data_and_vault_dirs, live_apis):
    """kb trend-report on the AI API served, with its key, the subjects of the tests and the
    instant of the run."""
    monkeypatch.setenv(AI_API_URL_VARIABLE, live_apis.ai_api_url)
    monkeypatch.setenv(TREND_REPORT_KEY_VARIABLE, live_apis.trend_report_key)
    monkeypatch.setattr(
        trend_report_client,
        "SUBJECT_NAMES",
        tuple(subject.name for subject in TEST_SUBJECTS),
    )
    monkeypatch.setattr(trend_report_command, "read_now", lambda: TREND_REPORT_TIME)
    return data_and_vault_dirs


def read_chosen_section(sheet):
    """The lines of the sheet from its title of the chosen to the next title."""
    lines = sheet.splitlines()
    start = lines.index("## Choisis par le modèle")
    return lines[start : lines.index("## Dépôts qui ressortent")]


@pytest.mark.parametrize("replay_steps", [TREND_REPORT_STEPS], ids=["two-chosen"])
def test_trend_report_writes_the_chosen_through_the_ai_api_and_the_data_api(
    trend_report_environment, capsys
):
    _, vault_dir = trend_report_environment

    exit_code = cli.main(["trend-report"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert list_sheets(vault_dir) == [TREND_REPORT_SHEET]
    sheet = (vault_dir / TREND_REPORT_SHEET).read_text("utf-8")
    assert read_chosen_section(sheet) == CHOSEN_SECTION
    output = capsys.readouterr().out
    # The windows of the test base, read by the data API.
    assert "Period: 2026-10-07 → 2026-10-10, 4 windows, 2 missing" in output
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
