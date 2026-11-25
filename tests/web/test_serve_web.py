"""kb serve-web: its settings checked at the start, nothing served after a refusal, the access logged
without the object id, a log file of its own, and the data API woken at the start, never by the
network in a test."""

import logging
import threading

import httpx2
import pytest
from fastapi import FastAPI
from site_client import OPERATOR_ID, TEST_API_KEY

from k_b import cli
from k_b.commands import serve_web_command
from k_b.jobs.api_health import build_health_client

# The real wake-up, kept before any test replaces it.
WAKE_DATA_API = serve_web_command.wake_data_api


class WakeCalls(list):
    """The base URLs the simulated wake-up is given, and an event set at its first call."""

    def __init__(self):
        super().__init__()
        self.called = threading.Event()


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        serve_web_command.uvicorn,
        "run",
        lambda app, **options: calls.append((app, options)),
    )
    return calls


@pytest.fixture(autouse=True)
def wake_calls(monkeypatch):
    """The wake-up of the data API, simulated in every test: the base URLs it is given."""
    calls = WakeCalls()

    def wake(base_url):
        calls.append(base_url)
        calls.called.set()

    monkeypatch.setattr(serve_web_command, "wake_data_api", wake)
    return calls


@pytest.fixture
def data_api_key(monkeypatch):
    monkeypatch.setenv("KB_DATA_API_KEY_WEB", TEST_API_KEY)


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    return tmp_path


def read_log(data_dir):
    return (data_dir / "logs" / "kb-serve-web.log").read_text(encoding="utf-8")


def test_serve_web_listens_on_127_0_0_1_8002_by_default_without_uvicorn_logging_config(
    monkeypatch, data_dir, data_api_key, uvicorn_calls
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


def test_serve_web_gives_the_version_of_its_image_to_the_site(
    monkeypatch, data_dir, data_api_key, uvicorn_calls
):
    monkeypatch.setenv("KB_WEB_OPERATOR_ID", OPERATOR_ID)
    monkeypatch.setenv("KB_VERSION", "v0.1.9")

    cli.main(["serve-web"])

    [(app, _)] = uvicorn_calls
    assert app.state.version == "v0.1.9"


def test_serve_web_logs_its_access_and_hosts_in_its_own_file_never_the_object_id(
    monkeypatch, data_dir, data_api_key, uvicorn_calls
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
    monkeypatch, data_dir, data_api_key, uvicorn_calls
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


def test_serve_web_exits_2_without_the_key_of_its_client_never_waking_the_data_api(
    monkeypatch, data_dir, uvicorn_calls, wake_calls
):
    monkeypatch.setenv("KB_WEB_AUTH", "off")
    monkeypatch.delenv("KB_DATA_API_KEY_WEB", raising=False)

    exit_code = cli.main(["serve-web"])

    assert exit_code == 2
    assert uvicorn_calls == []
    assert wake_calls == []
    assert "KB_DATA_API_KEY_WEB: not set" in read_log(data_dir)


def test_serve_web_wakes_the_data_api_at_its_start(
    monkeypatch, data_dir, data_api_key, uvicorn_calls, wake_calls
):
    """The data API at zero replicas wakes in 20 to 26 s (#414): while the operator signs in."""
    monkeypatch.setenv("KB_WEB_AUTH", "off")

    cli.main(["serve-web"])

    assert wake_calls.called.wait(timeout=5)
    assert wake_calls == ["http://127.0.0.1:8000"]


def test_serve_web_closes_the_client_of_the_data_api_once_stopped(
    monkeypatch, data_dir, data_api_key, uvicorn_calls
):
    monkeypatch.setenv("KB_WEB_AUTH", "off")

    cli.main(["serve-web"])

    [(app, _)] = uvicorn_calls
    assert app.state.data_api_client.is_closed


@pytest.mark.parametrize(
    ("answer", "line", "level"),
    [
        (
            httpx2.Response(200, json={"status": "ok"}),
            "data API wake-up: health ok",
            logging.INFO,
        ),
        (
            httpx2.Response(503, json={"error": "query_timeout"}),
            "data API wake-up: health_failed, HTTP 503",
            logging.WARNING,
        ),
    ],
)
def test_the_wake_up_logs_its_state_never_the_url(
    monkeypatch, caplog, answer, line, level
):
    url = "https://ca-kb-data-api.internal.example.azurecontainerapps.io"
    monkeypatch.setattr(
        serve_web_command,
        "build_health_client",
        lambda base_url: build_health_client(
            base_url, transport=httpx2.MockTransport(lambda request: answer)
        ),
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        WAKE_DATA_API(url)

    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (level, line)
    ]
