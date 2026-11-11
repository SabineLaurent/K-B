"""kb serve-web: its settings checked at the start, nothing served after a refusal, the access logged
without the object id, and a log file of its own."""

import pytest
from fastapi import FastAPI
from site_client import OPERATOR_ID

from k_b import cli
from k_b.commands import serve_web_command


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        serve_web_command.uvicorn,
        "run",
        lambda app, **options: calls.append((app, options)),
    )
    return calls


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    return tmp_path


def read_log(data_dir):
    return (data_dir / "logs" / "kb-serve-web.log").read_text(encoding="utf-8")


def test_serve_web_listens_on_127_0_0_1_8002_by_default_without_uvicorn_logging_config(
    monkeypatch, data_dir, uvicorn_calls
):
    monkeypatch.setenv("KB_WEB_OPERATOR_ID", OPERATOR_ID)

    exit_code = cli.main(["serve-web"])

    [(app, options)] = uvicorn_calls
    assert exit_code == 0
    assert isinstance(app, FastAPI)
    assert options == {
        "host": "127.0.0.1",
        "port": 8002,
        "log_config": None,
        "access_log": False,
        "server_header": False,
    }


def test_serve_web_logs_its_access_and_hosts_in_its_own_file_never_the_object_id(
    monkeypatch, data_dir, uvicorn_calls
):
    """kb serve-web runs for long: a rotation done by kb collect in kb.log would leave it writing in
    the file of the day before."""
    monkeypatch.setenv("KB_WEB_OPERATOR_ID", OPERATOR_ID)

    cli.main(["serve-web"])

    log = read_log(data_dir)
    assert (
        "site access: the object id of the operator checked in X-MS-CLIENT-PRINCIPAL-ID"
        in log
    )
    assert "site allowed hosts: 127.0.0.1, localhost" in log
    assert OPERATOR_ID not in log
    assert not (data_dir / "logs" / "kb.log").exists()


def test_serve_web_off_says_that_no_header_is_checked(
    monkeypatch, data_dir, uvicorn_calls
):
    monkeypatch.setenv("KB_WEB_AUTH", "off")

    exit_code = cli.main(["serve-web"])

    assert exit_code == 0
    assert "site access: off, no header checked, on the machine only" in read_log(
        data_dir
    )


def test_serve_web_exits_2_and_serves_nothing_on_a_setting_refused(
    monkeypatch, data_dir, uvicorn_calls
):
    exit_code = cli.main(["serve-web"])

    assert exit_code == 2
    assert uvicorn_calls == []
    assert "KB_WEB_OPERATOR_ID: not set" in read_log(data_dir)
