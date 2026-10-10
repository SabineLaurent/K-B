import os
import sqlite3
import subprocess
import sys

import pytest
from test_collect import BrokenSource, WorkingSource

from k_b import cli
from k_b.import_items import KindWithoutTableError, UnknownSourceError
from k_b.source_contract import SourceKind


def collected_kinds(*sources):
    """One kind without a reader: the collection tests only need its sources."""
    return (SourceKind("test", sources, None),)


def test_collect_refuses_to_run_without_a_data_directory(monkeypatch, capsys):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)

    exit_code = cli.main(["collect"])

    assert exit_code == 2
    assert "KB_DATA_DIR" in capsys.readouterr().err


def test_collect_refuses_a_data_directory_that_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path / "missing"))

    assert cli.main(["collect"]) == 2


def test_collect_reports_a_failure_but_still_stores_the_other_sources(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        cli, "SOURCE_KINDS", collected_kinds(BrokenSource(), WorkingSource())
    )

    exit_code = cli.main(["collect"])

    assert exit_code == 1
    assert list((tmp_path / "raw" / "automated_watch" / "working").iterdir())


def test_collect_writes_its_state_at_the_root_of_the_data_directory_not_in_raw(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(WorkingSource()))

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert (tmp_path / "collection_state.json").is_file()
    assert not (tmp_path / "raw" / "collection_state.json").exists()


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root writes a file whatever its permissions"
)
def test_collect_still_prints_the_summary_and_exits_1_when_the_state_cannot_be_written(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / "raw" / "automated_watch").mkdir(parents=True)
    tmp_path.chmod(0o500)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(WorkingSource()))

    try:
        exit_code = cli.main(["collect"])
    finally:
        tmp_path.chmod(0o700)

    assert exit_code == 1
    assert (
        capsys.readouterr().out
        == "working: ok\ncollection_state: failed (PermissionError)\n"
    )


def test_collect_fails_closed_with_a_clear_message_on_a_corrupted_state(
    monkeypatch, tmp_path, capsys
):
    state_path = tmp_path / "collection_state.json"
    state_path.write_text('{"working": ', encoding="utf-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(WorkingSource()))

    exit_code = cli.main(["collect"])

    assert exit_code == 2
    error_output = capsys.readouterr().err
    assert "collection_state.json" in error_output
    assert "Traceback" not in error_output
    assert not (tmp_path / "raw" / "automated_watch").exists()
    assert state_path.read_text(encoding="utf-8") == '{"working": '


def test_collect_prints_nothing_but_the_error_on_a_corrupted_state(
    monkeypatch, tmp_path, capsys
):
    state_path = tmp_path / "collection_state.json"
    state_path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds())

    assert cli.main(["collect"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root reads a file whatever its permissions"
)
def test_collect_fails_closed_with_a_clear_message_on_an_unreadable_state(
    monkeypatch, tmp_path, capsys
):
    state_path = tmp_path / "collection_state.json"
    state_path.write_text("{}", encoding="utf-8")
    state_path.chmod(0o000)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(WorkingSource()))

    try:
        exit_code = cli.main(["collect"])
    finally:
        state_path.chmod(0o600)

    assert exit_code == 2
    error_output = capsys.readouterr().err
    assert "collection_state.json" in error_output
    assert "permission" in error_output.lower()
    assert not (tmp_path / "raw" / "automated_watch").exists()


def test_an_info_line_of_k_b_is_shown_once_logging_is_configured():
    # A new interpreter: pytest's own log handlers would hide what kb collect shows.
    script = (
        "import logging; from k_b.cli import configure_logging; configure_logging(); "
        "logging.getLogger('k_b.sources.tldr').info('tldr_ai 2026-10-03: no edition page')"
    )

    result = subprocess.run(  # noqa: S603 — runs this interpreter on a fixed script
        [sys.executable, "-c", script], capture_output=True, text=True
    )

    assert "INFO k_b.sources.tldr: tldr_ai 2026-10-03: no edition page" in result.stderr


def test_create_db_creates_the_database_in_the_data_directory(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))

    exit_code = cli.main(["create-db"])

    assert exit_code == 0
    assert (tmp_path / "k-b.sqlite").is_file()
    assert "k-b.sqlite" in capsys.readouterr().out


def test_create_db_run_again_refuses_and_keeps_the_database(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    database_content = (tmp_path / "k-b.sqlite").read_bytes()

    exit_code = cli.main(["create-db"])

    assert exit_code == 2
    assert "already exists" in capsys.readouterr().err
    assert (tmp_path / "k-b.sqlite").read_bytes() == database_content


def test_create_db_refuses_to_run_without_a_data_directory(monkeypatch, capsys):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)

    assert cli.main(["create-db"]) == 2
    assert "KB_DATA_DIR" in capsys.readouterr().err


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root writes a file whatever its permissions"
)
def test_create_db_reports_a_database_that_cannot_be_written_and_exits_1(
    monkeypatch, tmp_path, capsys
):
    read_only_dir = tmp_path / "read-only"
    read_only_dir.mkdir()
    read_only_dir.chmod(0o500)
    monkeypatch.setenv("KB_DATA_DIR", str(read_only_dir))

    try:
        exit_code = cli.main(["create-db"])
    finally:
        read_only_dir.chmod(0o700)

    assert exit_code == 1
    assert "error:" in capsys.readouterr().err


def test_import_writes_the_raw_items_into_the_database(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    exit_code = cli.main(["import"])

    assert exit_code == 0
    assert "items imported: 0" in capsys.readouterr().out
    assert (tmp_path / "import-log.jsonl").is_file()


def test_import_refuses_a_missing_database_and_does_not_create_it(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))

    exit_code = cli.main(["import"])

    assert exit_code == 2
    assert "kb create-db" in capsys.readouterr().err
    assert not (tmp_path / "k-b.sqlite").exists()


def test_import_reports_a_failed_import_and_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    def fail_to_import(
        raw_dir, database_path, log_path, source_kinds, tracked_repositories
    ):
        raise sqlite3.IntegrityError("CHECK constraint failed: publication")

    monkeypatch.setattr(cli, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "error: IntegrityError: CHECK constraint failed: publication"
        in capsys.readouterr().err
    )


def test_import_reports_a_source_missing_from_the_database_and_exits_1(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    def fail_to_import(
        raw_dir, database_path, log_path, source_kinds, tracked_repositories
    ):
        raise UnknownSourceError("source_code not in the source table: cisa_kev")

    monkeypatch.setattr(cli, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "error: UnknownSourceError: source_code not in the source table: cisa_kev"
        in capsys.readouterr().err
    )


def test_import_reports_a_kind_without_table_and_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    def fail_to_import(
        raw_dir, database_path, log_path, source_kinds, tracked_repositories
    ):
        raise KindWithoutTableError(
            "kind without a table in the base: newsletter_article"
        )

    monkeypatch.setattr(cli, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "error: KindWithoutTableError: kind without a table in the base: newsletter_article"
        in capsys.readouterr().err
    )
