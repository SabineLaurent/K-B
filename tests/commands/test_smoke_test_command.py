"""kb smoke-test: the health and the probes without key of both APIs, the health of the base of the
data API, then the listing of the container of the test by the identity of the job; only counts are
written."""

import re
import signal
from functools import partial

import httpx2
import pytest
from exchange.storage_fakes import (
    FORGED_LOG_LINE,
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    FakeTransport,
    answer_forbidden_naming_the_blob,
    answer_identity_refusal,
    answer_listing,
    answer_token,
    names_the_spotted_blob,
    remove_online_variables,
    set_identity_endpoint,
)

from k_b import cli
from k_b.commands import smoke_test_command
from k_b.exchange.storage import (
    build_managed_identity_credential,
    open_container_client,
)
from k_b.jobs.api_health import build_health_client
from k_b.jobs.api_probes import build_probe_client

TEST_DATA_API_HOST = "ca-kb-data-api.internal.test.example"
TEST_AI_API_HOST = "ca-kb-ai-api.internal.test.example"
TEST_DATA_API_URL = f"https://{TEST_DATA_API_HOST}"
TEST_AI_API_URL = f"https://{TEST_AI_API_HOST}"
HEALTH_BODY = b'{"status":"ok"}'
# What both APIs answer without a key, out of the sandbox; tests/ai_api and tests/data_api send
# each probe to the apps themselves.
STATUS_WITHOUT_KEY = {
    ("GET", "/health"): 200,
    ("GET", "/health/database"): 200,
    ("GET", "/items"): 401,
    ("POST", "/digests"): 401,
    ("GET", "/docs"): 404,
    ("HEAD", "/health"): 405,
}
# Each probe: the API, its host, the request, and the row of the summary.
PROBES = [
    ("data API", TEST_DATA_API_HOST, "GET", "/items"),
    ("data API", TEST_DATA_API_HOST, "GET", "/docs"),
    ("data API", TEST_DATA_API_HOST, "HEAD", "/health"),
    ("AI API", TEST_AI_API_HOST, "POST", "/digests"),
    ("AI API", TEST_AI_API_HOST, "GET", "/docs"),
    ("AI API", TEST_AI_API_HOST, "HEAD", "/health"),
]


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


def answer_as_the_apis(changed_statuses=None):
    """Both APIs as they answer without a key out of the sandbox; changed_statuses gives another
    status to a request, by its host, method and path."""
    changed_statuses = changed_statuses or {}

    def handle(request):
        status = changed_statuses.get(
            (request.url.host, request.method, request.url.path),
            STATUS_WITHOUT_KEY[(request.method, request.url.path)],
        )
        return httpx2.Response(status, content=HEALTH_BODY)

    return handle


def simulate(monkeypatch, handle_api=None, handle_storage=None):
    """The two APIs, the identity endpoint and the storage of kb smoke-test; the requests each
    receives are returned."""
    api_requests = []

    def keep_and_handle(request):
        api_requests.append(request)
        return (handle_api or answer_as_the_apis())(request)

    def handle_health(request):
        assert (request.method, request.url.path) == ("GET", "/health")
        return keep_and_handle(request)

    def handle_probe(request):
        assert (request.method, request.url.path) != ("GET", "/health")
        return keep_and_handle(request)

    identity = FakeTransport(answer_token)
    storage = FakeTransport(handle_storage or answer_listing(SPOTTED_BLOB_NAME))
    monkeypatch.setattr(
        smoke_test_command,
        "build_health_client",
        partial(build_health_client, transport=httpx2.MockTransport(handle_health)),
    )
    monkeypatch.setattr(
        smoke_test_command,
        "build_probe_client",
        partial(build_probe_client, transport=httpx2.MockTransport(handle_probe)),
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


def read_summary(output):
    """The rows of the summary kb smoke-test prints, its header included: check -> result."""
    return dict(re.findall(r"^(\S.*?)  +(\S.*)$", output, re.MULTILINE))


def test_smoke_test_passes_once_both_apis_answer_and_the_container_is_listed(
    monkeypatch, smoke_test_environment, capsys
):
    api_requests, storage_requests = simulate(monkeypatch)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert [(request.method, str(request.url)) for request in api_requests] == [
        ("GET", f"{TEST_DATA_API_URL}/health"),
        ("GET", f"{TEST_DATA_API_URL}/items"),
        ("GET", f"{TEST_DATA_API_URL}/docs"),
        ("HEAD", f"{TEST_DATA_API_URL}/health"),
        ("GET", f"{TEST_DATA_API_URL}/health/database"),
        ("GET", f"{TEST_AI_API_URL}/health"),
        ("POST", f"{TEST_AI_API_URL}/digests"),
        ("GET", f"{TEST_AI_API_URL}/docs"),
        ("HEAD", f"{TEST_AI_API_URL}/health"),
    ]
    assert not any("authorization" in request.headers for request in api_requests)
    assert len(storage_requests) == 1
    assert read_summary(capsys.readouterr().out) == {
        "check": "result",
        "data API": "ok",
        "data API GET /items": "401 as expected",
        "data API GET /docs": "404 as expected",
        "data API HEAD /health": "405 as expected",
        "data API GET /health/database": "ok",
        "AI API": "ok",
        "AI API POST /digests": "401 as expected",
        "AI API GET /docs": "404 as expected",
        "AI API HEAD /health": "405 as expected",
        "exchange storage": "1 blob listed in smoke-test",
    }
    log = read_kb_log(smoke_test_environment)
    assert "data API: /health/database answered" in log
    assert "AI API: POST /digests without key answered 401" in log
    assert "exchange storage: 1 blob listed in smoke-test" in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 10 of 10 checks passed\n", log
    )


@pytest.mark.parametrize(("name", "host", "method", "path"), PROBES)
def test_a_probe_that_gets_another_status_fails_and_the_other_checks_still_run(
    monkeypatch, smoke_test_environment, capsys, name, host, method, path
):
    api_requests, storage_requests = simulate(
        monkeypatch, handle_api=answer_as_the_apis({(host, method, path): 200})
    )

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    assert len(api_requests) == 9
    assert len(storage_requests) == 1
    summary = read_summary(capsys.readouterr().out)
    assert summary[f"{name} {method} {path}"] == "failed"
    assert sum(result == "failed" for result in summary.values()) == 1
    log = read_kb_log(smoke_test_environment)
    assert (
        f"ERROR k_b.cli: {name}: {method} {path} without key failed: "
        "probe_unexpected_status, HTTP 200\n"
    ) in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 9 of 10 checks passed\n", log
    )


@pytest.mark.parametrize(
    ("error_type", "state"),
    [(httpx2.ReadTimeout, "probe_timeout"), (httpx2.ConnectError, "probe_unavailable")],
)
def test_a_probe_without_answer_fails_by_its_state_without_the_url(
    monkeypatch, smoke_test_environment, error_type, state
):
    def fail_the_digests(request):
        if request.method == "POST":
            raise error_type("refused by the test", request=request)
        return answer_as_the_apis()(request)

    simulate(monkeypatch, handle_api=fail_the_digests)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    log = read_kb_log(smoke_test_environment)
    assert f"ERROR k_b.cli: AI API: POST /digests without key failed: {state}\n" in log
    assert TEST_AI_API_HOST not in log
    assert "refused by the test" not in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 9 of 10 checks passed\n", log
    )


class UnreadStream(httpx2.SyncByteStream):
    """A body that fails the test if it is read."""

    def __iter__(self):
        raise AssertionError("the body was read")


def test_the_body_of_an_answer_to_a_probe_is_never_read(
    monkeypatch, smoke_test_environment
):
    def answer_probes_with_an_unread_body(request):
        answer = answer_as_the_apis()(request)
        if request.method == "GET" and request.url.path.startswith("/health"):
            return answer
        return httpx2.Response(answer.status_code, stream=UnreadStream())

    simulate(monkeypatch, handle_api=answer_probes_with_an_unread_body)

    assert cli.main(["smoke-test"]) == cli.ExitCode.SUCCEEDED


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
    assert read_summary(captured.out)["exchange storage"] == "failed"
    assert not names_the_spotted_blob(captured.out)
    assert not names_the_spotted_blob(captured.err)
    assert not names_the_spotted_blob(log)


def test_a_token_refused_is_logged_once_by_kb_without_what_the_endpoint_says(
    monkeypatch, smoke_test_environment, capsys
):
    simulate(monkeypatch)
    identity = FakeTransport(answer_identity_refusal)
    monkeypatch.setattr(
        smoke_test_command,
        "build_managed_identity_credential",
        partial(build_managed_identity_credential, transport=identity),
    )

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    log = read_kb_log(smoke_test_environment)
    assert "exchange storage: not listed: exchange_storage_no_token\n" in log
    assert "get_token failed" not in log
    assert FORGED_LOG_LINE not in log
    assert FORGED_LOG_LINE not in capsys.readouterr().err


def test_an_api_that_fails_its_health_fails_the_smoke_test_and_the_other_checks_still_run(
    monkeypatch, smoke_test_environment, capsys
):
    api_requests, storage_requests = simulate(
        monkeypatch,
        handle_api=answer_as_the_apis({(TEST_DATA_API_HOST, "GET", "/health"): 503}),
    )

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    assert len(api_requests) == 9
    assert len(storage_requests) == 1
    summary = read_summary(capsys.readouterr().out)
    assert summary["data API"] == "failed"
    assert summary["data API GET /items"] == "401 as expected"
    assert summary["AI API"] == "ok"
    log = read_kb_log(smoke_test_environment)
    assert "data API: /health failed: health_failed, HTTP 503" in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 9 of 10 checks passed\n", log
    )


@pytest.mark.parametrize(
    ("answer", "description"),
    [
        (
            httpx2.Response(503, content=b'{"error":"database_unavailable"}'),
            "health_failed, HTTP 503",
        ),
        (httpx2.Response(200, content=b'{"status":"down"}'), "health_invalid_response"),
    ],
)
def test_a_base_the_data_api_does_not_read_fails_the_smoke_test_and_the_other_checks_still_run(
    monkeypatch, smoke_test_environment, capsys, answer, description
):
    def answer_without_the_base(request):
        if request.url.path == "/health/database":
            return answer
        return answer_as_the_apis()(request)

    api_requests, storage_requests = simulate(
        monkeypatch, handle_api=answer_without_the_base
    )

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    assert len(api_requests) == 9
    assert len(storage_requests) == 1
    summary = read_summary(capsys.readouterr().out)
    assert summary["data API GET /health/database"] == "failed"
    assert sum(result == "failed" for result in summary.values()) == 1
    log = read_kb_log(smoke_test_environment)
    assert f"ERROR k_b.cli: data API: /health/database failed: {description}\n" in log
    assert TEST_DATA_API_HOST not in log
    assert re.search(
        r"INFO k_b\.cli: smoke test finished in \d+ s: 9 of 10 checks passed\n", log
    )


def test_smoke_test_reaches_the_compose_services_in_http_in_the_sandbox(
    monkeypatch, smoke_test_environment
):
    monkeypatch.setenv("KB_DEPLOYMENT_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("KB_DATA_API_URL", "http://api-donnees:8000")
    monkeypatch.setenv("KB_AI_API_URL", "http://api-ia:8001")
    api_requests, _ = simulate(
        monkeypatch,
        handle_api=answer_as_the_apis(
            {("api-donnees", "GET", "/docs"): 200, ("api-ia", "GET", "/docs"): 200}
        ),
    )

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert [str(request.url) for request in api_requests] == [
        "http://api-donnees:8000/health",
        "http://api-donnees:8000/items",
        "http://api-donnees:8000/docs",
        "http://api-donnees:8000/health",
        "http://api-donnees:8000/health/database",
        "http://api-ia:8001/health",
        "http://api-ia:8001/digests",
        "http://api-ia:8001/docs",
        "http://api-ia:8001/health",
    ]


def test_in_the_sandbox_a_docs_not_served_fails_its_probe(
    monkeypatch, smoke_test_environment, capsys
):
    """In the sandbox both APIs serve /docs (read_openapi_url), out of it neither does."""
    monkeypatch.setenv("KB_DEPLOYMENT_ENVIRONMENT", "sandbox")
    simulate(monkeypatch)

    exit_code = cli.main(["smoke-test"])

    assert exit_code == cli.ExitCode.FAILED
    summary = read_summary(capsys.readouterr().out)
    assert summary["data API GET /docs"] == "failed"
    assert summary["AI API GET /docs"] == "failed"
    log = read_kb_log(smoke_test_environment)
    assert (
        "AI API: GET /docs without key failed: probe_unexpected_status, HTTP 404\n"
    ) in log


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
        (
            "KB_DATA_API_URL",
            "http://ca-kb-data-api.internal.test.example",
            "KB_DATA_API_URL: https required; http only to the machine (127.0.0.1 or localhost) or, in the sandbox, a compose service (api-donnees or api-ia)",
        ),
        (
            "KB_AI_API_URL",
            "http://ca-kb-ai-api.internal.test.example",
            "KB_AI_API_URL: https required; http only to the machine (127.0.0.1 or localhost) or, in the sandbox, a compose service (api-donnees or api-ia)",
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
