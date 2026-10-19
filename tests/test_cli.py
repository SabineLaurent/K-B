import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, time, timedelta

import pytest
import uvicorn.config
from etl.test_extract import BrokenSource, WorkingSource
from etl.test_transform import FIXTURES_DIR, copy_fixture

from k_b import cli
from k_b.commands import collect_command, import_command
from k_b.core import quoting
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl import collected_sources, load
from k_b.etl.source_contract import SourceKind
from k_b.etl.sources import clipping


@pytest.fixture(autouse=True)
def no_zotero_directory(monkeypatch):
    """A terminal that exports KB_ZOTERO_DIR must not make the tests read a real library."""
    monkeypatch.delenv("KB_ZOTERO_DIR", raising=False)


@pytest.fixture(autouse=True)
def no_vault_directory(monkeypatch):
    """A terminal that exports KB_VAULT_DIR must not make the tests read a real vault."""
    monkeypatch.delenv("KB_VAULT_DIR", raising=False)


@pytest.fixture(autouse=True)
def no_bigquery_key(monkeypatch):
    """A terminal that exports the BigQuery key must not make the tests query BigQuery."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)


@pytest.fixture(autouse=True)
def no_collect_only(monkeypatch):
    """A terminal that exports KB_COLLECT_ONLY must not filter the sources of the tests."""
    monkeypatch.delenv("KB_COLLECT_ONLY", raising=False)


@pytest.fixture(autouse=True)
def no_github_token(monkeypatch):
    """A terminal that exports KB_GITHUB_TOKEN must not hide the line said without it."""
    monkeypatch.delenv("KB_GITHUB_TOKEN", raising=False)


def collected_kinds(*sources):
    """One kind without a reader: the collection tests only need its sources."""
    return (SourceKind("test", sources, None),)


def declared_kinds(*sources):
    """The kind of collected_kinds, and the three kinds whose source etl/collected_sources.py
    creates: names that KB_COLLECT_ONLY can choose."""
    return collected_kinds(*sources) + tuple(
        SourceKind(name, (), None) for name in ("zotero", "clipping", "gh_archive")
    )


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
        collect_command,
        "SOURCE_KINDS",
        collected_kinds(BrokenSource(), WorkingSource()),
    )

    exit_code = cli.main(["collect"])

    assert exit_code == cli.ExitCode.PARTIAL_FAILURE
    assert list((tmp_path / "raw" / "automated_watch" / "working").iterdir())


def test_collect_writes_its_state_at_the_root_of_the_data_directory_not_in_raw(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

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
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

    try:
        exit_code = cli.main(["collect"])
    finally:
        tmp_path.chmod(0o700)

    assert exit_code == 1
    assert (
        capsys.readouterr().out
        == "working: ok\nzotero: skipped (KB_ZOTERO_DIR not set)\n"
        "clipping: skipped (KB_VAULT_DIR not set)\n"
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
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == "working: ok\nzotero: skipped (KB_ZOTERO_DIR not set)\n"
        "clipping: skipped (KB_VAULT_DIR not set)\n"
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
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", collected_kinds())

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "zotero: ok\nclipping: skipped (KB_VAULT_DIR not set)\n"
        "gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n"
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
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", collected_kinds())

    exit_code = cli.main(["collect"])

    assert exit_code == 1
    assert capsys.readouterr().out == (
        "zotero: failed (FileNotFoundError)\nclipping: skipped (KB_VAULT_DIR not set)\n"
        "gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)\n"
    )
    assert json.loads((data_dir / "collection_state.json").read_text()) == {}
    assert not (data_dir / "raw").exists()


@pytest.mark.parametrize("vault_dir_variable", [None, ""])
def test_collect_skips_the_clips_and_says_so_without_the_vault(
    monkeypatch, tmp_path, capsys, vault_dir_variable
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    if vault_dir_variable is not None:
        monkeypatch.setenv("KB_VAULT_DIR", vault_dir_variable)
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert "clipping: skipped (KB_VAULT_DIR not set)\n" in capsys.readouterr().out
    assert not (tmp_path / "raw" / "selected_library").exists()


def test_collect_copies_the_clips_into_the_selected_library_with_the_vault(
    monkeypatch, tmp_path, capsys
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    clippings_dir = tmp_path / "vault" / "Clippings"
    clippings_dir.mkdir(parents=True)
    clip = (FIXTURES_DIR / "clipping" / "article_with_author.md").read_bytes()
    (clippings_dir / "A clip.md").write_bytes(clip)
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", collected_kinds())
    # A collection later than the margin after the clip written above (CLIP_CHANGE_MARGIN).
    monkeypatch.setattr(
        clipping, "current_time", lambda: datetime.now(UTC) + timedelta(minutes=5)
    )

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert "clipping: ok\n" in capsys.readouterr().out
    [collection_dir] = (data_dir / "raw" / "selected_library" / "clipping").iterdir()
    assert [page.read_bytes() for page in collection_dir.iterdir()] == [clip]
    assert (clippings_dir / "A clip.md").read_bytes() == clip
    assert "clipping" in json.loads((data_dir / "collection_state.json").read_text())


@pytest.mark.parametrize("bigquery_key_variable", [None, ""])
def test_collect_skips_gh_archive_and_says_so_without_the_bigquery_key(
    monkeypatch, tmp_path, capsys, bigquery_key_variable
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    if bigquery_key_variable is not None:
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", bigquery_key_variable)
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", collected_kinds())

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
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", collected_kinds())
    monkeypatch.setattr(collected_sources, "GhArchiveSource", FakeGhArchiveSource)

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert created == [collected_sources.create_bigquery_client]
    output = capsys.readouterr().out
    assert "gh_archive: ok\n" in output
    assert "gh_archive: skipped" not in output
    assert list((tmp_path / "raw" / "automated_watch" / "gh_archive").iterdir())


def test_collect_only_runs_the_sources_chosen_and_keeps_the_date_of_the_others(
    monkeypatch, tmp_path, capsys, zotero_dir
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "collection_state.json").write_text(
        '{"working": "2026-10-17T06:00:00+00:00"}', encoding="utf-8"
    )
    clippings_dir = tmp_path / "vault" / "Clippings"
    clippings_dir.mkdir(parents=True)
    clip = (FIXTURES_DIR / "clipping" / "article_with_author.md").read_bytes()
    (clippings_dir / "A clip.md").write_bytes(clip)
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_ZOTERO_DIR", str(zotero_dir))
    monkeypatch.setenv("KB_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("KB_COLLECT_ONLY", "zotero,clipping")
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", declared_kinds(WorkingSource())
    )
    # A collection later than the margin after the clip written above (CLIP_CHANGE_MARGIN).
    monkeypatch.setattr(
        clipping, "current_time", lambda: datetime.now(UTC) + timedelta(minutes=5)
    )

    exit_code = cli.main(["collect"])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "zotero: ok\nclipping: ok\ntest: skipped (not in KB_COLLECT_ONLY)\n"
        "gh_archive: skipped (not in KB_COLLECT_ONLY)\n"
    )
    assert sorted(path.name for path in (data_dir / "raw").iterdir()) == [
        "selected_library"
    ]
    state = json.loads((data_dir / "collection_state.json").read_text())
    assert state["working"] == "2026-10-17T06:00:00+00:00"
    assert {"zotero", "clipping"} <= state.keys()


def test_collect_without_collect_only_runs_every_source(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command,
        "SOURCE_KINDS",
        declared_kinds(WorkingSource(), WorkingSource("other")),
    )

    assert cli.main(["collect"]) == 0
    assert capsys.readouterr().out.startswith("working: ok\nother: ok\n")
    assert sorted(
        path.name for path in (tmp_path / "raw" / "automated_watch").iterdir()
    ) == ["other", "working"]


def test_collect_only_prints_one_line_for_a_source_not_chosen(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_COLLECT_ONLY", "test")
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", declared_kinds(WorkingSource())
    )

    assert cli.main(["collect"]) == 0
    # Not "zotero: skipped (KB_ZOTERO_DIR not set)" as well: Zotero was not chosen.
    assert capsys.readouterr().out == (
        "working: ok\nzotero: skipped (not in KB_COLLECT_ONLY)\n"
        "clipping: skipped (not in KB_COLLECT_ONLY)\n"
        "gh_archive: skipped (not in KB_COLLECT_ONLY)\n"
    )


def test_collect_only_takes_the_names_with_spaces_around_in_any_case_and_twice(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_COLLECT_ONLY", " Test , TEST,test")
    source = WorkingSource()
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", declared_kinds(source))

    assert cli.main(["collect"]) == 0
    assert source.received_last_collected_at == [None]


def assert_nothing_collected(data_dir, output):
    """Refused before the collection: no raw file, no state, no summary."""
    assert not (data_dir / "raw").exists()
    assert not (data_dir / "collection_state.json").exists()
    assert output == ""


def test_collect_only_refuses_a_name_that_is_not_a_source_folder_and_quotes_it(
    monkeypatch, tmp_path, capsys
):
    unknown_name = "tldr_ai\nERROR k_b.cli: forged line " + "x" * 200
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_COLLECT_ONLY", f"test,{unknown_name}")
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", declared_kinds(WorkingSource())
    )

    exit_code = cli.main(["collect"])

    assert exit_code == cli.ExitCode.NOT_STARTED
    output = capsys.readouterr()
    assert_nothing_collected(tmp_path, output.out)
    error_output = output.err
    quoted_name = quoting.quote_value(unknown_name)
    assert len(quoted_name) == 100
    assert (
        f"KB_COLLECT_ONLY: entry 2 of 2 {quoted_name} not a source folder;"
        " folders: test, zotero, clipping, gh_archive\n"
    ) in error_output
    assert "\nERROR k_b.cli: forged line" not in error_output


def test_collect_only_quotes_a_name_refused_as_it_was_written(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_COLLECT_ONLY", "Test,TLDR_AI")
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", declared_kinds(WorkingSource())
    )

    assert cli.main(["collect"]) == cli.ExitCode.NOT_STARTED
    assert "entry 2 of 2 'TLDR_AI' not a source folder" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("collect_only", "refusal"),
    [
        ("", "KB_COLLECT_ONLY: empty"),
        ("  ", "KB_COLLECT_ONLY: empty"),
        ("test,", "KB_COLLECT_ONLY: entry 2 of 2 empty"),
        ("test,,zotero", "KB_COLLECT_ONLY: entry 2 of 3 empty"),
    ],
)
def test_collect_only_refuses_an_empty_value_or_entry(
    monkeypatch, tmp_path, capsys, collect_only, refusal
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_COLLECT_ONLY", collect_only)
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", declared_kinds(WorkingSource())
    )

    assert cli.main(["collect"]) == cli.ExitCode.NOT_STARTED
    output = capsys.readouterr()
    assert refusal in output.err
    assert_nothing_collected(tmp_path, output.out)


@pytest.mark.parametrize(
    ("name", "variable"),
    [
        ("zotero", "KB_ZOTERO_DIR"),
        ("Zotero", "KB_ZOTERO_DIR"),
        ("clipping", "KB_VAULT_DIR"),
        ("gh_archive", "GOOGLE_APPLICATION_CREDENTIALS"),
    ],
)
def test_collect_only_refuses_a_source_chosen_without_its_variable(
    monkeypatch, tmp_path, capsys, name, variable
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_COLLECT_ONLY", f"test,{name}")
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", declared_kinds(WorkingSource())
    )

    assert cli.main(["collect"]) == cli.ExitCode.NOT_STARTED
    output = capsys.readouterr()
    assert f"KB_COLLECT_ONLY: entry 2 of 2 '{name}' chosen, {variable} not set" in (
        output.err
    )
    assert_nothing_collected(tmp_path, output.out)


def test_collect_fails_closed_with_a_clear_message_on_a_corrupted_state(
    monkeypatch, tmp_path, capsys
):
    state_path = tmp_path / "collection_state.json"
    state_path.write_text('{"working": ', encoding="utf-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

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
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", collected_kinds())

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
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

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
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(BrokenSource())
    )

    assert cli.main(["collect"]) == 1

    error_line = re.compile(
        rf"{LOG_LINE_DATE} ERROR k_b\.etl\.extract: collection failed for source 'broken':"
        " ConnectionError 'source is down'"
    )
    [file_line] = [
        line
        for line in (tmp_path / "logs" / "kb.log").read_text("utf-8").splitlines()
        if error_line.fullmatch(line)
    ]
    assert file_line in capsys.readouterr().err.splitlines()


QUOTA_LINE = "KB_GITHUB_TOKEN not set: the GitHub API allows 60 requests per hour instead of 5,000"


def github_kinds():
    """Two kinds of the sources that call the GitHub API, a source each."""
    return tuple(
        SourceKind(name, (WorkingSource(f"{name}_owner_repository"),), None)
        for name in ("github_releases", "github_advisories")
    )


def test_collect_announces_once_the_sources_it_runs_before_the_first_one(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command,
        "SOURCE_KINDS",
        declared_kinds(BrokenSource(), WorkingSource()),
    )

    assert cli.main(["collect"]) == cli.ExitCode.PARTIAL_FAILURE
    output = capsys.readouterr()
    error_lines = output.err.splitlines()
    # Not zotero, clipping nor gh_archive: declared, their variable not set.
    [announcement_position] = [
        position
        for position, line in enumerate(error_lines)
        if re.fullmatch(
            rf"{LOG_LINE_DATE} INFO k_b\.cli: sources to collect: broken, working", line
        )
    ]
    [failure_position] = [
        position
        for position, line in enumerate(error_lines)
        if "collection failed for source 'broken'" in line
    ]
    assert announcement_position < failure_position
    assert output.err.count("sources to collect:") == 1
    assert "sources to collect:" not in output.out


@pytest.mark.parametrize("token", [None, ""])
def test_collect_says_once_without_the_github_token_that_github_allows_60_requests(
    monkeypatch, tmp_path, capsys, token
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    if token is not None:
        monkeypatch.setenv("KB_GITHUB_TOKEN", token)
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", github_kinds())

    assert cli.main(["collect"]) == 0
    [quota_line] = [
        line
        for line in capsys.readouterr().err.splitlines()
        if "60 requests per hour" in line
    ]
    assert re.fullmatch(
        rf"{LOG_LINE_DATE} WARNING k_b\.cli: {re.escape(QUOTA_LINE)}", quota_line
    )


def test_collect_says_nothing_of_the_github_token_when_it_is_set(
    monkeypatch, tmp_path, capsys
):
    token_value = "github_pat_" + "x" * 30
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_GITHUB_TOKEN", token_value)
    monkeypatch.setattr(collect_command, "SOURCE_KINDS", github_kinds())

    assert cli.main(["collect"]) == 0
    output = capsys.readouterr()
    log_file_text = (tmp_path / "logs" / "kb.log").read_text("utf-8")
    assert "sources to collect:" in log_file_text
    for text in (output.out, output.err, log_file_text):
        assert "KB_GITHUB_TOKEN" not in text
        assert token_value not in text


def test_collect_only_without_a_github_source_says_nothing_of_the_github_token(
    monkeypatch, tmp_path, capsys, zotero_dir
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (tmp_path / "vault" / "Clippings").mkdir(parents=True)
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_ZOTERO_DIR", str(zotero_dir))
    monkeypatch.setenv("KB_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("KB_COLLECT_ONLY", "zotero,clipping")
    # The GitHub kinds are declared: only KB_COLLECT_ONLY leaves them out.
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", github_kinds() + declared_kinds()
    )

    assert cli.main(["collect"]) == 0
    error_output = capsys.readouterr().err
    assert "INFO k_b.cli: sources to collect: zotero, clipping\n" in error_output
    assert "KB_GITHUB_TOKEN" not in error_output
    assert "60 requests per hour" not in error_output


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root writes a file whatever its permissions"
)
def test_collect_refuses_to_run_when_the_log_file_cannot_be_opened(
    monkeypatch, tmp_path, capsys
):
    tmp_path.chmod(0o500)
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )

    try:
        exit_code = cli.main(["collect"])
    finally:
        tmp_path.chmod(0o700)

    assert exit_code == 2
    assert "error: log file not opened" in capsys.readouterr().err
    assert not (tmp_path / "raw").exists()


def test_an_error_handled_by_kb_is_a_dated_log_line_of_the_log_file(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))

    assert cli.main(["import"]) == 2

    [file_line] = (tmp_path / "logs" / "kb.log").read_text("utf-8").splitlines()
    assert re.fullmatch(
        rf"{LOG_LINE_DATE} ERROR k_b\.cli: .*; create it with kb create-db", file_line
    )
    assert file_line in capsys.readouterr().err.splitlines()


def test_an_exception_kb_does_not_handle_is_logged_once_and_exits_1(
    monkeypatch, tmp_path, capsys
):
    def failing_collect(data_dir):
        raise RuntimeError("not handled")

    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "run_collect", failing_collect)

    assert cli.main(["collect"]) == 1

    # Once on stderr: the traceback is not printed again by Python.
    assert capsys.readouterr().err.count("RuntimeError: not handled") == 1

    log_text = (tmp_path / "logs" / "kb.log").read_text("utf-8")
    assert re.match(
        rf"{LOG_LINE_DATE} ERROR k_b\.cli: kb stopped by an exception it does not handle\n",
        log_text,
    )
    assert "RuntimeError: not handled" in log_text


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
    assert "ERROR k_b.cli: " in capsys.readouterr().err


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
    monkeypatch.setattr(import_command, "datetime", FrozenDatetime)
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

    monkeypatch.setattr(import_command, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "ERROR k_b.cli: IntegrityError: CHECK constraint failed: publication"
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

    monkeypatch.setattr(import_command, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "ERROR k_b.cli: UnknownSourceError: source_code not in the source table: cisa_kev"
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

    monkeypatch.setattr(import_command, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "ERROR k_b.cli: KindWithoutTableError: kind without a table in the base: newsletter_article"
        in capsys.readouterr().err
    )


def test_each_exit_code_keeps_its_value():
    assert {member.name: member.value for member in cli.ExitCode} == {
        "SUCCEEDED": 0,
        "FAILED": 1,
        "NOT_STARTED": 2,
        "SERVER_NOT_STARTED": 3,
        "PARTIAL_FAILURE": 4,
        "STOPPED_BY_SIGTERM": 143,
    }


def test_the_server_not_started_code_is_the_one_uvicorn_exits_with():
    assert cli.ExitCode.SERVER_NOT_STARTED == uvicorn.config.STARTUP_FAILURE


def test_kb_help_lists_each_exit_code_with_its_meaning_on_its_own_line(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--help"])

    assert stop.value.code == 0
    lines = capsys.readouterr().out.splitlines()
    for member in cli.ExitCode:
        assert [str(member.value), member.meaning] in [
            line.split(maxsplit=1) for line in lines
        ]


class SigtermNotHandledByKbError(Exception):
    """Raised by the handler of the test: kb did not set its own."""


@pytest.fixture
def sigterm_handler_of_the_test():
    """A SIGTERM handler set before kb runs. Without it, a kb that sets no handler would leave
    the default one, which kills pytest; kb must set it back when it ends."""

    def raise_in_the_test(signal_number, frame):
        raise SigtermNotHandledByKbError

    previous_handler = signal.signal(signal.SIGTERM, raise_in_the_test)
    yield raise_in_the_test
    signal.signal(signal.SIGTERM, previous_handler)


class SigtermSource(WorkingSource):
    """A source during which the container is stopped."""

    def fetch(self, last_collected_at):
        signal.raise_signal(signal.SIGTERM)
        return super().fetch(last_collected_at)


def list_hidden_files(directory):
    return [path for path in directory.rglob(".*") if path.is_file()]


def dump_database(data_dir):
    """Every table, row by row, as SQL text, as in etl/test_load.py: its module cannot be
    imported from here (it imports its neighbours by their bare name)."""
    connection = sqlite3.connect(data_dir / "k-b.sqlite")
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def test_a_sigterm_after_the_import_log_is_written_leaves_neither_the_import_nor_its_log(
    monkeypatch, tmp_path, sigterm_handler_of_the_test
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    tables_before = dump_database(tmp_path)
    write_import_log = load.write_import_log

    def write_then_receive_sigterm(log_path, *arguments):
        write_import_log(log_path, *arguments)
        assert log_path.is_file()
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(load, "write_import_log", write_then_receive_sigterm)

    exit_code = cli.main(["import"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert dump_database(tmp_path) == tables_before
    assert list(tmp_path.glob("import-log-*.jsonl")) == []
    assert list_hidden_files(tmp_path) == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: kb stopped by SIGTERM$",
        (tmp_path / "logs" / "kb.log").read_text("utf-8"),
        re.MULTILINE,
    )


class SigtermAfterCommitConnection(sqlite3.Connection):
    """A SIGTERM received during the commit: its handler runs once the commit has returned."""

    def commit(self):
        super().commit()
        signal.raise_signal(signal.SIGTERM)


def test_a_sigterm_once_the_base_has_committed_keeps_the_import_and_its_log(
    monkeypatch, tmp_path, capsys, sigterm_handler_of_the_test, connect_with_factory
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    # An unreadable page: a rejection, so that the log kept has a line.
    unreadable_path = copy_fixture(
        tmp_path / "raw", "cisa_kev_extract.csv", "github_advisories_pip", "json"
    )
    unreadable_path.write_text("not json", encoding="utf-8")
    capsys.readouterr()
    monkeypatch.setattr(
        load, "connect_database", connect_with_factory(SigtermAfterCommitConnection)
    )

    exit_code = cli.main(["import"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    connection = sqlite3.connect(tmp_path / "k-b.sqlite")
    assert connection.execute("SELECT count(*) FROM raw_data").fetchone() == (1,)
    connection.close()
    [log_path] = tmp_path.glob("import-log-*.jsonl")
    log_lines = [json.loads(line) for line in log_path.read_text("utf-8").splitlines()]
    assert [line["kind"] for line in log_lines] == ["rejection"]
    imported_at = datetime.fromisoformat(log_lines[0]["imported_at"])
    assert log_path.name == f"import-log-{imported_at:%Y-%m-%dT%H%M%SZ}.jsonl"
    output = capsys.readouterr()
    assert "raw files read" not in output.out
    assert f"INFO k_b.etl.load: import committed, log kept: '{log_path.name}'" in (
        output.err
    )


def test_a_sigterm_during_a_source_stops_kb_collect_and_keeps_the_collection_state(
    monkeypatch, tmp_path, sigterm_handler_of_the_test
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
        collected_kinds(SigtermSource("stopped"), WorkingSource("after")),
    )

    exit_code = cli.main(["collect"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert (tmp_path / "collection_state.json").read_bytes() == state_before
    assert not (tmp_path / "raw" / "automated_watch" / "after").exists()
    assert list_hidden_files(tmp_path) == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


# kb collect run as the kb script runs it, sys.exit(main()), with a source that says it has
# started, then waits for the signal.
COLLECT_WAITING_FOR_SIGTERM = """
import sys
import time

from k_b import cli
from k_b.commands import collect_command
from k_b.etl.source_contract import SourceKind


class WaitingSource:
    name = "waiting"
    extension = "json"
    acquisition_dir_name = "automated_watch"

    def fetch(self, last_collected_at):
        print("ready", flush=True)
        time.sleep(60)
        return b"{}"


collect_command.SOURCE_KINDS = (SourceKind("test", (WaitingSource(),), None),)
sys.exit(cli.main(["collect"]))
"""


def test_kb_collect_sent_sigterm_in_its_own_process_exits_with_143(tmp_path):
    process = subprocess.Popen(  # noqa: S603 — runs this interpreter on a fixed script
        [sys.executable, "-c", COLLECT_WAITING_FOR_SIGTERM],
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
        process.send_signal(signal.SIGTERM)
        _, error_output = process.communicate(timeout=30)
    finally:
        process.kill()
        process.wait()

    assert process.returncode == cli.ExitCode.STOPPED_BY_SIGTERM
    assert "ERROR k_b.cli: kb stopped by SIGTERM" in error_output
    assert not (tmp_path / "collection_state.json").exists()
