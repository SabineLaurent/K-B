"""kb serve and kb openapi: the keys checked at the start, the host, the log of the API, the
OpenAPI written without data directory."""

import os
import secrets
from pathlib import Path

import pytest

from k_b import cli

VERSIONED_OPENAPI = Path(__file__).parents[2] / "docs" / "api" / "openapi-donnees.json"


@pytest.fixture(autouse=True)
def no_api_key_of_the_terminal(monkeypatch):
    """A terminal that exports a key must not give it to the tests."""
    for name in os.environ:
        if name.startswith("KB_API_KEY_"):
            monkeypatch.delenv(name)


@pytest.fixture
def uvicorn_calls(monkeypatch):
    """The calls kb serve makes to uvicorn.run, which is not run."""
    calls = []
    monkeypatch.setattr(
        cli.uvicorn, "run", lambda app, **options: calls.append((app, options))
    )
    return calls


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    return tmp_path


def make_key(length=43):
    """A key of the test; token_urlsafe(32) gives 43 characters."""
    return secrets.token_urlsafe(32)[:length]


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({}, "no API key: set KB_API_KEY_<CLIENT>"),
        (
            {"KB_API_KEY_": make_key()},
            "'KB_API_KEY_': client name empty or not [A-Z0-9_]+",
        ),
        (
            {"KB_API_KEY_terminal": make_key()},
            "'KB_API_KEY_terminal': client name empty or not [A-Z0-9_]+",
        ),
        (
            {"KB_API_KEY_TERMINAL": make_key(31)},
            "'KB_API_KEY_TERMINAL': key of 31 characters, minimum 32",
        ),
        (
            {"KB_API_KEY_TERMINAL": ""},
            "'KB_API_KEY_TERMINAL': key of 0 characters, minimum 32",
        ),
    ],
)
def test_serve_exits_2_and_names_the_variable_without_its_value(
    monkeypatch, capsys, data_dir, uvicorn_calls, variables, message
):
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    exit_code = cli.main(["serve"])

    error_output = capsys.readouterr().err
    assert exit_code == 2
    assert message in error_output
    for value in variables.values():
        if value:
            assert value not in error_output
    assert uvicorn_calls == []


def test_serve_exits_2_when_two_clients_have_the_same_key(
    monkeypatch, capsys, data_dir, uvicorn_calls
):
    key = make_key()
    monkeypatch.setenv("KB_API_KEY_TERMINAL", key)
    monkeypatch.setenv("KB_API_KEY_AGENT", key)

    exit_code = cli.main(["serve"])

    error_output = capsys.readouterr().err
    assert exit_code == 2
    assert "'KB_API_KEY_AGENT' and 'KB_API_KEY_TERMINAL': same key" in error_output
    assert key not in error_output
    assert uvicorn_calls == []


def test_serve_logs_the_names_of_the_clients_never_their_keys(
    monkeypatch, capsys, data_dir, uvicorn_calls
):
    keys = {"KB_API_KEY_TERMINAL": make_key(), "KB_API_KEY_AGENT": make_key()}
    for name, value in keys.items():
        monkeypatch.setenv(name, value)

    exit_code = cli.main(["serve"])

    error_output = capsys.readouterr().err
    assert exit_code == 0
    assert "API clients loaded: AGENT, TERMINAL" in error_output
    for value in keys.values():
        assert value not in error_output


def test_serve_listens_on_127_0_0_1_without_uvicorn_logging_config(
    monkeypatch, data_dir, uvicorn_calls
):
    monkeypatch.setenv("KB_API_KEY_TERMINAL", make_key())

    cli.main(["serve"])

    [(_, options)] = uvicorn_calls
    assert options == {
        "host": "127.0.0.1",
        "port": 8000,
        "log_config": None,
        "access_log": False,
    }


def test_serve_writes_its_own_log_file(monkeypatch, data_dir, uvicorn_calls):
    """kb serve runs for long: a rotation done by kb collect in kb.log would leave it writing in
    the file of the day before (docs/specs-api.md, "Journal")."""
    monkeypatch.setenv("KB_API_KEY_TERMINAL", make_key())

    cli.main(["serve"])

    assert "API clients loaded: TERMINAL" in (
        data_dir / "logs" / "kb-serve.log"
    ).read_text(encoding="utf-8")
    assert not (data_dir / "logs" / "kb.log").exists()


def test_openapi_writes_the_document_without_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["openapi"])

    written = tmp_path / "docs" / "api" / "openapi-donnees.json"
    assert exit_code == 0
    assert written.read_text(encoding="utf-8") == VERSIONED_OPENAPI.read_text(
        encoding="utf-8"
    )
    assert not (tmp_path / "logs").exists()
