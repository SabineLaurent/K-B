"""kb digest-watch, the command of the job caj-kb-digest-watch: the wake of both APIs, kb digest, the
wake again, kb trend-report, then the publication of veille."""

import signal

import pytest
from jobs.storage_fakes import TEST_ACCOUNT_URL, TEST_CLIENT_ID, remove_online_variables

from k_b import cli
from k_b.commands import digest_watch_command
from k_b.commands.smoke_test_command import CHECK_FAILED, CHECK_PASSED, CheckResult

ExitCode = cli.ExitCode
TEST_DATA_API_URL = "https://ca-kb-data-api.internal.test.example"
TEST_AI_API_URL = "https://ca-kb-ai-api.internal.test.example"


@pytest.fixture
def routine_environment(monkeypatch, data_and_vault_dirs):
    """The settings of the job caj-kb-digest-watch, the identity endpoint aside."""
    remove_online_variables(monkeypatch)
    monkeypatch.setenv("KB_EXCHANGE_BLOB_URL", TEST_ACCOUNT_URL)
    monkeypatch.setenv("AZURE_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("KB_DATA_API_URL", TEST_DATA_API_URL)
    monkeypatch.setenv("KB_AI_API_URL", TEST_AI_API_URL)
    return data_and_vault_dirs


def replace_steps(monkeypatch, codes=None, failed_apis=()):
    """The checks of the APIs and each step, recorded in order; a step returns its code of codes,
    0 by default, or calls it."""
    ran = []

    def check_api(name, base_url):
        ran.append(f"wake {base_url}")
        return CheckResult(
            name, CHECK_FAILED if base_url in failed_apis else CHECK_PASSED
        )

    def make_step(function_name):
        def step(*arguments):
            ran.append(function_name)
            code = (codes or {}).get(function_name, ExitCode.SUCCEEDED)
            return code() if callable(code) else code

        return step

    monkeypatch.setattr(digest_watch_command, "check_api", check_api)
    for function_name in ("run_digest", "run_trend_report", "publish_the_watch"):
        monkeypatch.setattr(
            digest_watch_command, function_name, make_step(function_name)
        )
    return ran


def test_both_apis_are_woken_before_kb_digest_and_again_before_kb_trend_report(
    monkeypatch, routine_environment, capsys
):
    ran = replace_steps(monkeypatch)

    exit_code = cli.main(["digest-watch"])

    assert exit_code == ExitCode.SUCCEEDED
    assert ran == [
        f"wake {TEST_DATA_API_URL}",
        f"wake {TEST_AI_API_URL}",
        "run_digest",
        f"wake {TEST_DATA_API_URL}",
        f"wake {TEST_AI_API_URL}",
        "run_trend_report",
        "publish_the_watch",
    ]


@pytest.mark.parametrize(
    "digest_code",
    [ExitCode.FAILED, ExitCode.PARTIAL_FAILURE, ExitCode.NOT_STARTED],
)
def test_kb_trend_report_and_the_publication_run_after_kb_digest_fails(
    monkeypatch, routine_environment, capsys, digest_code
):
    ran = replace_steps(monkeypatch, {"run_digest": digest_code})

    exit_code = cli.main(["digest-watch"])

    assert "run_trend_report" in ran
    assert ran[-1] == "publish_the_watch"
    assert exit_code == digest_code


def test_a_failed_wake_does_not_stop_kb_digest(
    monkeypatch, routine_environment, capsys
):
    ran = replace_steps(monkeypatch, failed_apis={TEST_DATA_API_URL})

    exit_code = cli.main(["digest-watch"])

    assert ran.count("run_digest") == 1
    assert "run_trend_report" in ran
    # One API answered, the other did not.
    assert exit_code == ExitCode.PARTIAL_FAILURE


def test_a_sigterm_during_kb_digest_stops_the_routine_with_143(
    monkeypatch, routine_environment, capsys, sigterm_handler_of_the_test
):
    def receive_sigterm():
        signal.raise_signal(signal.SIGTERM)
        return ExitCode.SUCCEEDED

    ran = replace_steps(monkeypatch, {"run_digest": receive_sigterm})

    exit_code = cli.main(["digest-watch"])

    assert exit_code == ExitCode.STOPPED_BY_SIGTERM
    assert ran[-1] == "run_digest"
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


@pytest.mark.parametrize(
    "variable", ["KB_EXCHANGE_BLOB_URL", "AZURE_CLIENT_ID", "KB_VAULT_DIR"]
)
def test_a_setting_refused_runs_no_step_and_exits_with_2(
    monkeypatch, routine_environment, capsys, variable
):
    ran = replace_steps(monkeypatch)
    monkeypatch.delenv(variable)

    assert cli.main(["digest-watch"]) == ExitCode.NOT_STARTED
    assert ran == []


def test_the_dry_run_lists_the_steps_runs_none_and_exits_with_0(
    monkeypatch, tmp_path, capsys
):
    remove_online_variables(monkeypatch)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    ran = replace_steps(monkeypatch)

    exit_code = cli.main(["digest-watch", "--dry-run"])

    assert exit_code == ExitCode.SUCCEEDED
    assert ran == []
    assert capsys.readouterr().out == (
        "kb digest-watch, dry run: 5 steps, none run\n"
        "  1. wake of the APIs before kb digest\n"
        "  2. kb digest\n"
        "  3. wake of the APIs before kb trend-report\n"
        "  4. kb trend-report\n"
        "  5. watch publication\n"
    )


def test_the_dry_run_is_refused_for_another_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as stop:
        cli.main(["collect", "--dry-run"])

    assert stop.value.code == ExitCode.NOT_STARTED
