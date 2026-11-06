"""kb smoke-test: the health of both APIs, then the listing of the container of the test by the
identity of the job; only counts are written."""

import re
import signal
from functools import partial

import httpx2
import pytest
from jobs.storage_fakes import (
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    FakeTransport,
    answer_forbidden_naming_the_blob,
    answer_listing,
    answer_token,
    names_the_spotted_blob,
    remove_online_variables,
    set_identity_endpoint,
)

from k_b import cli
from k_b.commands import smoke_test_command
from k_b.jobs.api_health import build_health_client
from k_b.jobs.exchange_storage import (
    build_managed_identity_credential,
    open_container_client,
)

TEST_DATA_API_URL = "https://ca-kb-data-api.internal.test.example"
TEST_AI_API_URL = "https://ca-kb-ai-api.internal.test.example"
HEALTH_BODY = b'{"status":"ok"}'


@pytest.fixture(autouse=True)
def no_smoke_test_settings(monkeypatch):
    """A terminal that exports a setting of the job must not make the tests reach Azure;
    KB_AI_API_URL is removed by conftest.py."""
    remove_online_variables(monkeypatch)
    monkeypatch.delenv("KB_DATA_API_URL", raising=False)


@pytest.fixture
def smoke_test_environment(monkeypatch, tmp_path):
    """The settings of the job caj-kb-smoke-test, and the identity endpoint of its container."""
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_DATA_API_URL", TEST_DATA_API_URL)
    monkeypatch.setenv("KB_AI_API_URL", TEST_AI_API_URL)
    monkeypatch.setenv("KB_EXCHANGE_BLOB_URL", TEST_ACCOUNT_URL)
    monkeypatch.setenv("AZURE_CLIENT_ID", TEST_CLIENT_ID)
    set_identity_endpoint(monkeypatch)
    return tmp_path


def answer_health(status_by_host=None):
    """Both APIs; an API answers its status of status_by_host, 200 by default."""
    status_by_host = status_by_host or {}

    def handle(request):
        return httpx2.Response(
            status_by_host.get(request.url.host, 200), content=HEALTH_BODY
        )

    return handle


def simulate(monkeypatch, handle_api=None, handle_storage=None):
    """The two APIs, the identity endpoint and the storage of kb smoke-test; the requests each
    receives are returned."""
    api_requests = []

    def keep_and_handle(request):
        api_requests.append(request)
        return (handle_api or answer_health())(request)

    identity = FakeTransport(answer_token)
    storage = FakeTransport(handle_storage or answer_listing(SPOTTED_BLOB_NAME))
    monkeypatch.setattr(
        smoke_test_command,
        "build_health_client",
        partial(build_health_client, transport=httpx2.MockTransport(keep_and_handle)),
    )
    monkeypatch.setattr(
        smoke_test_command,
        "build_managed_identity_credential",
        partial(build_managed_identity_credential, transport=identity),
    )
    monkeypatch.setattr(
        smoke_test_command,
        "open_container_client",
        partial(open_container_client, transport=storage),
    )
    return api_requests, storage.adapter.requests


def read_kb_log(data_dir):
    return (data_dir / "logs" / "kb.log").read_text("utf-8")


def test_smoke_test_passes_once_both_apis_answer_and_the_container_is_listed(
    monkeypatch, smoke_test_environment, capsys
):
    api_requests, storage_requests = simulate(monkeypatch)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert [str(request.url) for request in api_requests] == [
        f"{TEST_DATA_API_URL}/health",
        f"{TEST_AI_API_URL}/health",
    ]
    assert len(storage_requests) == 1
    output = capsys.readouterr().out
    assert "data API          ok" in output
    assert "AI API            ok" in output
    assert "exchange storage  1 blob listed in smoke-test" in output
    log = read_kb_log(smoke_test_environment)
    assert "exchange storage: 1 blob listed in smoke-test" in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 3 of 3 checks passed\n", log
    )


def test_the_name_of_a_blob_listed_is_written_nowhere(
    monkeypatch, smoke_test_environment, capsys
):
    simulate(monkeypatch)

    cli.main(["smoke-test"])

    captured = capsys.readouterr()
    assert not names_the_spotted_blob(captured.out)
    assert not names_the_spotted_blob(captured.err)
    assert not names_the_spotted_blob(read_kb_log(smoke_test_environment))


def test_a_403_of_the_storage_fails_the_smoke_test_without_the_name_its_body_gives(
    monkeypatch, smoke_test_environment, capsys
):
    simulate(monkeypatch, handle_storage=answer_forbidden_naming_the_blob)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    captured = capsys.readouterr()
    log = read_kb_log(smoke_test_environment)
    assert (
        "exchange storage: not listed: exchange_storage_forbidden, HTTP 403,"
        " AuthenticationFailed"
    ) in log
    assert "exchange storage  failed" in captured.out
    assert not names_the_spotted_blob(captured.out)
    assert not names_the_spotted_blob(captured.err)
    assert not names_the_spotted_blob(log)


def test_an_api_that_fails_its_health_fails_the_smoke_test_and_the_other_checks_still_run(
    monkeypatch, smoke_test_environment, capsys
):
    api_requests, storage_requests = simulate(
        monkeypatch,
        handle_api=answer_health({"ca-kb-data-api.internal.test.example": 503}),
    )

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    assert len(api_requests) == 2
    assert len(storage_requests) == 1
    output = capsys.readouterr().out
    assert "data API          failed" in output
    assert "AI API            ok" in output
    log = read_kb_log(smoke_test_environment)
    assert "data API: /health failed: health_failed, HTTP 503" in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 2 of 3 checks passed\n", log
    )


@pytest.mark.parametrize(
    ("variable", "value", "refusal"),
    [
        ("AZURE_CLIENT_ID", None, "AZURE_CLIENT_ID: not set"),
        ("KB_EXCHANGE_BLOB_URL", None, "KB_EXCHANGE_BLOB_URL: not set"),
        (
            "KB_DATA_API_URL",
            "ftp://kb-data",
            "KB_DATA_API_URL: scheme not http nor https",
        ),
        (
            "KB_AI_API_URL",
            "http://kb-ai?key=1",
            "KB_AI_API_URL: with a query or a fragment",
        ),
    ],
)
def test_a_refused_setting_runs_no_check(
    monkeypatch, smoke_test_environment, variable, value, refusal
):
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)
    api_requests, storage_requests = simulate(monkeypatch)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.NOT_STARTED
    assert api_requests == []
    assert storage_requests == []
    assert refusal in read_kb_log(smoke_test_environment)


def test_a_sigterm_during_a_check_stops_kb_smoke_test(
    monkeypatch, smoke_test_environment, sigterm_handler_of_the_test
):
    def receive_sigterm(request):
        signal.raise_signal(signal.SIGTERM)
        return httpx2.Response(200, content=HEALTH_BODY)

    _, storage_requests = simulate(monkeypatch, handle_api=receive_sigterm)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert storage_requests == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def test_kb_smoke_test_help_exits_with_0_without_any_setting(monkeypatch, capsys):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)

    with pytest.raises(SystemExit) as raised:
        cli.main(["smoke-test", "--help"])

    assert raised.value.code == 0
    assert "usage: kb smoke-test" in capsys.readouterr().out
