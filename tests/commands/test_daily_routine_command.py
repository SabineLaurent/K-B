"""kb daily-routine, the command of the job caj-kb-daily-routine: the mirror of the clips, kb collect,
kb import unless kb collect exits with 1 or 2, kb purge, kb write-tops, then the publication of
veille."""

import signal

import pytest
from jobs.storage_fakes import TEST_ACCOUNT_URL, TEST_CLIENT_ID, remove_online_variables

from k_b import cli
from k_b.commands import daily_routine_command
from k_b.commands.sigterm import COMMANDS_STOPPED_BY_SIGTERM

ExitCode = cli.ExitCode
STEP_FUNCTIONS = (
    "mirror_the_clips",
    "run_collect",
    "run_import",
    "run_purge",
    "run_write_tops",
    "publish_the_watch",
)


@pytest.fixture
def routine_environment(monkeypatch, data_and_vault_dirs):
    """The settings of the job caj-kb-daily-routine, the identity endpoint aside."""
    remove_online_variables(monkeypatch)
    monkeypatch.setenv("KB_EXCHANGE_BLOB_URL", TEST_ACCOUNT_URL)
    monkeypatch.setenv("AZURE_CLIENT_ID", TEST_CLIENT_ID)
    return data_and_vault_dirs


def replace_steps(monkeypatch, codes=None):
    """Each step of the routine by a function that records its name and returns its code, 0 by
    default; a code that is a callable is called instead."""
    ran = []

    def make_step(function_name):
        def step(*arguments):
            ran.append(function_name)
            code = (codes or {}).get(function_name, ExitCode.SUCCEEDED)
            return code() if callable(code) else code

        return step

    for function_name in STEP_FUNCTIONS:
        monkeypatch.setattr(
            daily_routine_command, function_name, make_step(function_name)
        )
    return ran


@pytest.mark.parametrize("collect_code", [ExitCode.SUCCEEDED, ExitCode.PARTIAL_FAILURE])
def test_kb_import_runs_after_kb_collect_exits_with_0_or_4(
    monkeypatch, routine_environment, capsys, collect_code
):
    ran = replace_steps(monkeypatch, {"run_collect": collect_code})

    exit_code = cli.main(["daily-routine"])

    assert ran == list(STEP_FUNCTIONS)
    assert exit_code == collect_code


@pytest.mark.parametrize("collect_code", [ExitCode.FAILED, ExitCode.NOT_STARTED])
def test_kb_import_does_not_run_after_kb_collect_exits_with_1_or_2_the_rest_does(
    monkeypatch, routine_environment, capsys, collect_code
):
    ran = replace_steps(monkeypatch, {"run_collect": collect_code})

    exit_code = cli.main(["daily-routine"])

    assert ran == [
        "mirror_the_clips",
        "run_collect",
        "run_purge",
        "run_write_tops",
        "publish_the_watch",
    ]
    assert exit_code == collect_code
    assert "kb import          not run" in capsys.readouterr().out


def test_kb_purge_comes_right_after_kb_import_without_a_rule():
    names = [step.name for step in daily_routine_command.DAILY_ROUTINE_STEPS]
    purge_step = daily_routine_command.DAILY_ROUTINE_STEPS[names.index("kb purge")]

    assert names.index("kb purge") == names.index("kb import") + 1
    assert purge_step.not_run_after is None


@pytest.mark.parametrize("import_code", [ExitCode.FAILED, ExitCode.NOT_STARTED])
def test_kb_purge_runs_after_kb_import_exits_with_1_or_2(
    monkeypatch, routine_environment, capsys, import_code
):
    """A failed import committed nothing: the purge reads the base of the last one committed."""
    ran = replace_steps(monkeypatch, {"run_import": import_code})

    exit_code = cli.main(["daily-routine"])

    assert ran == list(STEP_FUNCTIONS)
    assert exit_code == import_code


def test_a_failed_mirror_does_not_stop_the_routine(
    monkeypatch, routine_environment, capsys
):
    ran = replace_steps(monkeypatch, {"mirror_the_clips": ExitCode.FAILED})

    exit_code = cli.main(["daily-routine"])

    assert ran == list(STEP_FUNCTIONS)
    assert exit_code == ExitCode.FAILED


def test_a_sigterm_during_kb_collect_stops_the_routine_with_143(
    monkeypatch, routine_environment, capsys, sigterm_handler_of_the_test
):
    def receive_sigterm():
        signal.raise_signal(signal.SIGTERM)
        return ExitCode.SUCCEEDED

    ran = replace_steps(monkeypatch, {"run_collect": receive_sigterm})

    exit_code = cli.main(["daily-routine"])

    assert exit_code == ExitCode.STOPPED_BY_SIGTERM
    assert ran == ["mirror_the_clips", "run_collect"]
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def test_daily_routine_digest_watch_and_kb_purge_stop_on_sigterm():
    assert {"daily-routine", "digest-watch", "purge"} <= COMMANDS_STOPPED_BY_SIGTERM


@pytest.mark.parametrize(
    "variable", ["KB_EXCHANGE_BLOB_URL", "AZURE_CLIENT_ID", "KB_VAULT_DIR"]
)
def test_a_setting_refused_runs_no_step_and_exits_with_2(
    monkeypatch, routine_environment, capsys, variable
):
    ran = replace_steps(monkeypatch)
    monkeypatch.delenv(variable)

    assert cli.main(["daily-routine"]) == ExitCode.NOT_STARTED
    assert ran == []


def test_the_dry_run_lists_the_steps_runs_none_and_exits_with_0(
    monkeypatch, tmp_path, capsys
):
    remove_online_variables(monkeypatch)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    ran = replace_steps(monkeypatch)

    exit_code = cli.main(["daily-routine", "--dry-run"])

    assert exit_code == ExitCode.SUCCEEDED
    assert ran == []
    assert capsys.readouterr().out == (
        "kb daily-routine, dry run: 6 steps, none run\n"
        "  1. clip mirror\n"
        "  2. kb collect\n"
        "  3. kb import, not run when kb collect exits with 1 or 2\n"
        "  4. kb purge\n"
        "  5. kb write-tops\n"
        "  6. watch publication\n"
    )
