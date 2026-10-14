import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, time, timedelta

import pytest
from etl.test_extract import BrokenSource, WorkingSource
from etl.test_transform import FIXTURES_DIR

from k_b import cli
from k_b.database.writers.shared_rows import UnknownSourceError
from k_b.etl.load import KindWithoutTableError
from k_b.etl.source_contract import SourceKind


@pytest.fixture(autouse=True)
def no_zotero_directory(monkeypatch):
    """A terminal that exports KB_ZOTERO_DIR must not make the tests read a real library."""
    monkeypatch.delenv("KB_ZOTERO_DIR", raising=False)


@pytest.fixture(autouse=True)
def no_bigquery_key(monkeypatch):
    """A terminal that exports the BigQuery key must not make the tests query BigQuery."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)


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
    # The log folder stays writable: only the state cannot be written.
    (tmp_path / "logs").mkdir()
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
        == "working: ok\nzotero: skipped (KB_ZOTERO_DIR not set)\n"
        "gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n"
        "collection_state: failed (PermissionError)\n"
    )


@pytest.mark.parametrize("zotero_dir_variable", [None, ""])
def test_collect_skips_zotero_and_says_so_without_its_directory(
    monkeypatch, tmp_path, capsys, zotero_dir_variable
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    if zotero_dir_variable is not None:
        monkeypatch.setenv("KB_ZOTERO_DIR", zotero_dir_variable)
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(WorkingSource()))

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == "working: ok\nzotero: skipped (KB_ZOTERO_DIR not set)\n"
        "gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n"
    )
    assert not (data_dir / "raw" / "selected_library").exists()


def test_collect_extracts_zotero_into_the_selected_library_with_its_directory(
    monkeypatch, tmp_path, capsys, zotero_dir
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_ZOTERO_DIR", str(zotero_dir))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds())

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "zotero: ok\ngh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n"
    )
    [extract_path] = (data_dir / "raw" / "selected_library" / "zotero").iterdir()
    assert extract_path.suffix == ".json"
    assert [document["key"] for document in json.loads(extract_path.read_bytes())] == [
        "AAAAAAA1",
        "BBBBBBB2",
    ]
    assert "zotero" in json.loads((data_dir / "collection_state.json").read_text())


def test_collect_reports_a_zotero_failure_and_keeps_its_last_collection_date(
    monkeypatch, tmp_path, capsys
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    directory_without_a_library = tmp_path / "Zotero"
    directory_without_a_library.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_ZOTERO_DIR", str(directory_without_a_library))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds())

    exit_code = cli.main(["collect"])

    assert exit_code == 1
    assert capsys.readouterr().out == (
        "zotero: failed (FileNotFoundError)\ngh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n"
    )
    assert json.loads((data_dir / "collection_state.json").read_text()) == {}
    assert not (data_dir / "raw").exists()


@pytest.mark.parametrize("bigquery_key_variable", [None, ""])
def test_collect_skips_gh_archive_and_says_so_without_the_bigquery_key(
    monkeypatch, tmp_path, capsys, bigquery_key_variable
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    if bigquery_key_variable is not None:
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", bigquery_key_variable)
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds())

    assert cli.main(["collect"]) == 0
    assert "gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n" in (
        capsys.readouterr().out
    )


def test_collect_runs_gh_archive_with_the_bigquery_key(monkeypatch, tmp_path, capsys):
    created = []

    class FakeGhArchiveSource(WorkingSource):
        def __init__(self, create_client):
            super().__init__("gh_archive")
            created.append(create_client)

    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/a/key.json")
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds())
    monkeypatch.setattr(cli, "GhArchiveSource", FakeGhArchiveSource)

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert created == [cli.create_bigquery_client]
    output = capsys.readouterr().out
    assert "gh_archive: ok\n" in output
    assert "gh_archive: skipped" not in output
    assert list((tmp_path / "raw" / "automated_watch" / "gh_archive").iterdir())


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


# The date of a log line, in the format of the dates of the base: ISO 8601, UTC, its zone Z.
LOG_LINE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


def test_a_log_line_is_dated_in_utc_with_its_zone(tmp_path):
    # A new interpreter: pytest's own log handlers would hide what kb shows. Its local time is
    # UTC+5:30: a line dated in local time cannot pass for UTC.
    script = (
        "import logging, sys; from pathlib import Path; from k_b.cli import logging_to\n"
        "with logging_to(Path(sys.argv[1])):\n"
        "    logging.getLogger('k_b.etl.sources.tldr').info('tldr_ai 2026-10-03: no edition page')"
    )
    before = datetime.now(UTC).replace(microsecond=0)

    result = subprocess.run(  # noqa: S603 — runs this interpreter on a fixed script
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "Asia/Kolkata"},
    )

    after = datetime.now(UTC)
    match = re.fullmatch(
        rf"({LOG_LINE_DATE}) INFO k_b\.etl\.sources\.tldr: tldr_ai 2026-10-03: no edition page\n",
        result.stderr,
    )
    assert match is not None, result.stderr
    assert before <= datetime.fromisoformat(match.group(1)) <= after


def test_an_error_log_line_is_written_to_the_log_file_in_the_same_format(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(BrokenSource()))

    assert cli.main(["collect"]) == 1

    error_line = re.compile(
        rf"{LOG_LINE_DATE} ERROR k_b\.etl\.extract: collection failed for source 'broken'"
    )
    [file_line] = [
        line
        for line in (tmp_path / "logs" / "kb.log").read_text("utf-8").splitlines()
        if error_line.fullmatch(line)
    ]
    assert file_line in capsys.readouterr().err.splitlines()


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root writes a file whatever its permissions"
)
def test_collect_refuses_to_run_when_the_log_file_cannot_be_opened(
    monkeypatch, tmp_path, capsys
):
    tmp_path.chmod(0o500)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "SOURCE_KINDS", collected_kinds(WorkingSource()))

    try:
        exit_code = cli.main(["collect"])
    finally:
        tmp_path.chmod(0o700)

    assert exit_code == 2
    assert "error: log file not opened" in capsys.readouterr().err
    assert not (tmp_path / "raw").exists()


def test_a_log_file_of_an_earlier_utc_day_is_rotated_at_the_first_line(tmp_path):
    log_path = tmp_path / "logs" / "kb.log"
    log_path.parent.mkdir()
    log_path.write_text("a line of yesterday\n", encoding="utf-8")
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    yesterday_noon = datetime.combine(yesterday, time(12), tzinfo=UTC).timestamp()
    os.utime(log_path, (yesterday_noon, yesterday_noon))

    with cli.logging_to(tmp_path):
        logging.getLogger("k_b.test").info("a line of today")

    rotated_path = tmp_path / "logs" / f"kb.log.{yesterday.isoformat()}"
    assert rotated_path.read_text("utf-8") == "a line of yesterday\n"
    assert log_path.read_text("utf-8").endswith(" INFO k_b.test: a line of today\n")
    assert "yesterday" not in log_path.read_text("utf-8")


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
    # The log folder stays writable: only the database cannot be written.
    (read_only_dir / "logs").mkdir(parents=True)
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
    output = capsys.readouterr().out
    assert "raw files read: 0" in output
    assert "items written (new or updated): 0" in output
    assert (
        "items and trend windows left out (duplicates or versions not newer): 0"
        in output
    )
    assert "trend rows written: 0" in output
    assert "rows withdrawn (vulnerabilities, Zotero entries, highlights): 0" in output
    (log_path,) = tmp_path.glob("import-log-*.jsonl")
    assert re.fullmatch(r"import-log-\d{4}-\d{2}-\d{2}T\d{6}Z\.jsonl", log_path.name)
    assert f"log: {log_path}" in output


def test_import_writes_the_raw_rankings_of_gh_archive_into_the_trend_table(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    source_dir = tmp_path / "raw" / "automated_watch" / "gh_archive"
    source_dir.mkdir(parents=True)
    shutil.copyfile(
        FIXTURES_DIR / "gh_archive_extract.json", source_dir / "2026-10-11T153130Z.json"
    )

    exit_code = cli.main(["import"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "raw files read: 1" in output
    assert "trend rows written: 5" in output
    connection = sqlite3.connect(tmp_path / "k-b.sqlite")
    assert connection.execute("SELECT count(*) FROM trend").fetchone() == (5,)
    connection.close()


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 12, 15, 49, 3, 250000, tzinfo=UTC)


def test_import_refuses_to_rewrite_the_log_of_its_second_and_exits_2(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    monkeypatch.setattr(cli, "datetime", FrozenDatetime)
    log_path = tmp_path / "import-log-2026-10-12T154903Z.jsonl"
    log_path.write_text("earlier import\n")

    exit_code = cli.main(["import"])

    assert exit_code == 2
    assert str(log_path) in capsys.readouterr().err
    assert log_path.read_text() == "earlier import\n"


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
        reading,
        trend_reading,
        database_path,
        log_path,
        imported_at,
        tracked_repositories,
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
        reading,
        trend_reading,
        database_path,
        log_path,
        imported_at,
        tracked_repositories,
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
        reading,
        trend_reading,
        database_path,
        log_path,
        imported_at,
        tracked_repositories,
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
