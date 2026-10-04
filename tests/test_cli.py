import os
import subprocess
import sys

import pytest

from test_collect import BrokenSource, WorkingSource

from k_b import cli


def test_collect_refuses_to_run_without_a_data_directory(monkeypatch, capsys):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)

    exit_code = cli.main(["collect"])

    assert exit_code == 2
    assert "KB_DATA_DIR" in capsys.readouterr().err


def test_collect_refuses_a_data_directory_that_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path / "missing"))

    assert cli.main(["collect"]) == 2


def test_collect_reports_a_failure_but_still_stores_the_other_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCES", [BrokenSource(), WorkingSource()])

    exit_code = cli.main(["collect"])

    assert exit_code == 1
    assert list((tmp_path / "raw" / "automation" / "working").iterdir())


def test_collect_fails_closed_with_a_clear_message_on_a_corrupted_state(
    monkeypatch, tmp_path, capsys
):
    state_path = tmp_path / "raw" / "collection_state.json"
    state_path.parent.mkdir()
    state_path.write_text('{"working": ', encoding="utf-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCES", [WorkingSource()])

    exit_code = cli.main(["collect"])

    assert exit_code == 2
    error_output = capsys.readouterr().err
    assert "collection_state.json" in error_output
    assert "Traceback" not in error_output
    assert not (tmp_path / "raw" / "automation").exists()
    assert state_path.read_text(encoding="utf-8") == '{"working": '


def test_collect_prints_nothing_but_the_error_on_a_corrupted_state(monkeypatch, tmp_path, capsys):
    state_path = tmp_path / "raw" / "collection_state.json"
    state_path.parent.mkdir()
    state_path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCES", [])

    assert cli.main(["collect"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file whatever its permissions")
def test_collect_fails_closed_with_a_clear_message_on_an_unreadable_state(
    monkeypatch, tmp_path, capsys
):
    state_path = tmp_path / "raw" / "collection_state.json"
    state_path.parent.mkdir()
    state_path.write_text("{}", encoding="utf-8")
    state_path.chmod(0o000)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCES", [WorkingSource()])

    try:
        exit_code = cli.main(["collect"])
    finally:
        state_path.chmod(0o600)

    assert exit_code == 2
    error_output = capsys.readouterr().err
    assert "collection_state.json" in error_output
    assert "permission" in error_output.lower()
    assert not (tmp_path / "raw" / "automation").exists()


def test_an_info_line_of_k_b_is_shown_once_logging_is_configured():
    # A new interpreter: pytest's own log handlers would hide what kb collect shows.
    script = (
        "import logging; from k_b.cli import configure_logging; configure_logging(); "
        "logging.getLogger('k_b.tldr_source').info('tldr_ai 2026-10-03: no edition page')"
    )

    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)

    assert "INFO k_b.tldr_source: tldr_ai 2026-10-03: no edition page" in result.stderr
