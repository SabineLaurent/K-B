"""Ctrl-C (SIGINT): what kb collect and kb import keep when they are stopped, and how kb dies."""

import os
import re
import signal
import subprocess
import sys

import pytest
from commands.cli_helpers import (
    COLLECT_WAITING_FOR_A_SIGNAL,
    LOG_LINE_DATE,
    collected_kinds,
    dump_database,
    list_hidden_files,
)
from etl.test_extract import WorkingSource
from etl.test_transform import copy_fixture

from k_b import cli
from k_b.commands import collect_command
from k_b.commands.sigint import (
    COMMANDS_STOPPED_BY_SIGINT,
    raise_keyboard_interrupt_once,
    stopping_on_sigint,
)
from k_b.etl import load

CTRL_C_LINE = rf"^{LOG_LINE_DATE} ERROR k_b\.cli: kb stopped by Ctrl-C \(SIGINT\)$"


class CtrlCSource(WorkingSource):
    """A source during which Sabine presses Ctrl-C."""

    def fetch(self, last_collected_at):
        signal.raise_signal(signal.SIGINT)
        return super().fetch(last_collected_at)


def test_a_ctrl_c_during_a_source_stops_kb_collect_and_keeps_the_collection_state(
    monkeypatch, tmp_path, sigint_handler_of_the_test, deaths_by_sigint
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )
    cli.main(["collect"])
    state_before = (tmp_path / "collection_state.json").read_bytes()
    monkeypatch.setattr(
        collect_command,
        "SOURCE_KINDS",
        collected_kinds(
            WorkingSource("before"), CtrlCSource("stopped"), WorkingSource("after")
        ),
    )

    exit_code = cli.main(["collect"])

    assert deaths_by_sigint == [True]
    assert exit_code == cli.ExitCode.STOPPED_BY_SIGINT == 130
    assert (tmp_path / "collection_state.json").read_bytes() == state_before
    assert list((tmp_path / "raw" / "automated_watch" / "before").iterdir())
    assert not (tmp_path / "raw" / "automated_watch" / "after").exists()
    assert list_hidden_files(tmp_path) == []
    log = (tmp_path / "logs" / "kb.log").read_text("utf-8")
    assert re.search(CTRL_C_LINE, log, re.MULTILINE)
    assert "Traceback" not in log


def test_a_ctrl_c_during_kb_import_leaves_neither_the_import_nor_its_log(
    monkeypatch, tmp_path, sigint_handler_of_the_test, deaths_by_sigint
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    tables_before = dump_database(tmp_path)
    write_import_log = load.write_import_log

    def write_then_receive_ctrl_c(log_path, *arguments):
        write_import_log(log_path, *arguments)
        signal.raise_signal(signal.SIGINT)

    monkeypatch.setattr(load, "write_import_log", write_then_receive_ctrl_c)

    exit_code = cli.main(["import"])

    assert deaths_by_sigint == [True]
    assert exit_code == cli.ExitCode.STOPPED_BY_SIGINT
    assert dump_database(tmp_path) == tables_before
    assert list(tmp_path.glob("import-log-*.jsonl")) == []
    assert list_hidden_files(tmp_path) == []
    assert re.search(
        CTRL_C_LINE,
        (tmp_path / "logs" / "kb.log").read_text("utf-8"),
        re.MULTILINE,
    )


@pytest.mark.parametrize("command", sorted(COMMANDS_STOPPED_BY_SIGINT))
def test_kb_stops_on_the_first_ctrl_c_ignores_the_next_and_sets_the_handler_back(
    command, sigint_handler_of_the_test
):
    assert {"collect", "import", "write-tops", "digest"} == COMMANDS_STOPPED_BY_SIGINT
    with stopping_on_sigint(command):
        assert signal.getsignal(signal.SIGINT) is raise_keyboard_interrupt_once
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGINT)
        # The second one would cut the clean-up: ignored.
        assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN
        signal.raise_signal(signal.SIGINT)

    assert signal.getsignal(signal.SIGINT) is sigint_handler_of_the_test


def test_once_stopped_by_ctrl_c_kb_keeps_ignoring_sigint_until_it_dies(
    sigint_handler_of_the_test,
):
    with pytest.raises(KeyboardInterrupt), stopping_on_sigint("collect"):
        signal.raise_signal(signal.SIGINT)

    # Not set back: a second Ctrl-C would cut the line of the log.
    assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN


def test_a_sigint_ignored_from_the_start_stays_ignored(sigint_handler_of_the_test):
    # As for kb run in the background of a script: Ctrl-C is not meant for it.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    with stopping_on_sigint("collect"):
        assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN
        signal.raise_signal(signal.SIGINT)

    assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN


def test_kb_collect_run_with_sigint_ignored_goes_on_through_a_ctrl_c(
    monkeypatch, tmp_path, sigint_handler_of_the_test, deaths_by_sigint
):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command,
        "SOURCE_KINDS",
        collected_kinds(CtrlCSource("pressed"), WorkingSource("after")),
    )

    exit_code = cli.main(["collect"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert deaths_by_sigint == []
    assert list((tmp_path / "raw" / "automated_watch" / "after").iterdir())
    assert "Ctrl-C" not in (tmp_path / "logs" / "kb.log").read_text("utf-8")


@pytest.mark.parametrize("command", ["serve-data", "serve-ai", "create-db", "openapi"])
def test_the_other_commands_keep_the_sigint_handler_found(
    command, sigint_handler_of_the_test
):
    with stopping_on_sigint(command):
        assert signal.getsignal(signal.SIGINT) is sigint_handler_of_the_test


def test_a_ctrl_c_out_of_kb_serve_data_is_left_to_python_as_before(
    monkeypatch, tmp_path, deaths_by_sigint
):
    # uvicorn stops on Ctrl-C, then sends SIGINT again (uvicorn/server.py): KeyboardInterrupt.
    def stopped_by_ctrl_c(data_dir, environ):
        raise KeyboardInterrupt

    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "run_serve_data", stopped_by_ctrl_c)

    with pytest.raises(KeyboardInterrupt):
        cli.main(["serve-data"])

    assert deaths_by_sigint == []
    for log_path in (tmp_path / "logs").glob("*.log"):
        assert "Ctrl-C" not in log_path.read_text("utf-8")


def test_kb_collect_sent_sigint_in_its_own_process_dies_by_sigint(tmp_path):
    process = subprocess.Popen(  # noqa: S603 — runs this interpreter on a fixed script
        [sys.executable, "-c", COLLECT_WAITING_FOR_A_SIGNAL],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **{
                name: value
                for name, value in os.environ.items()
                if name != "KB_COLLECT_ONLY"
            },
            "KB_DATA_DIR": str(tmp_path),
        },
    )
    try:
        assert process.stdout.readline() == "ready\n"
        process.send_signal(signal.SIGINT)
        _, error_output = process.communicate(timeout=30)
    finally:
        process.kill()
        process.wait()

    # Killed by the signal, as a shell needs to stop its loop: it reads 130.
    assert process.returncode == -signal.SIGINT
    assert "ERROR k_b.cli: kb stopped by Ctrl-C (SIGINT)" in error_output
    assert "Traceback" not in error_output
    assert not (tmp_path / "collection_state.json").exists()
