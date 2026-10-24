import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime, time, timedelta
from functools import partial

import httpx2
import pytest
import uvicorn.config
from etl.test_extract import BrokenSource, WorkingSource
from etl.test_transform import FIXTURES_DIR, copy_fixture
from post.test_ai_api_client import (
    AGENT_DIGEST,
    REQUEST_ID,
    TEST_API_KEY,
    make_response,
    to_body,
)
from post.test_top_sheets import TEST_TOPS, write_ranking

from k_b import cli
from k_b.ai_api.schemas.digest_schema import FailedSubjectSchema
from k_b.commands import (
    collect_command,
    digest_command,
    import_command,
    write_tops_command,
)
from k_b.commands.exit_codes import find_exit_code
from k_b.core import quoting
from k_b.core.config import DigestSubject
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl import collected_sources, load, pipeline
from k_b.etl.source_contract import SourceKind
from k_b.etl.sources import clipping
from k_b.post import vault_files
from k_b.post.ai_api_client import build_ai_api_client


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
def no_ai_api_client_settings(monkeypatch):
    """A terminal that exports the key or the URL of kb digest must not make the tests reach a
    real AI API."""
    monkeypatch.delenv("KB_AI_API_KEY_KB_DIGEST", raising=False)
    monkeypatch.delenv("KB_AI_API_URL", raising=False)


@pytest.fixture(autouse=True)
def no_github_token(monkeypatch):
    """A terminal that exports KB_GITHUB_TOKEN must not hide the line said without it."""
    monkeypatch.delenv("KB_GITHUB_TOKEN", raising=False)


def collected_kinds(*sources):
    """One kind without a reader: the collection tests only need its sources."""
    return (SourceKind("test", sources, None),)


def declared_kinds(*sources):
    """The kind of collected_kinds, and the three kinds etl/collected_sources.py creates."""
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


def test_collect_says_nothing_of_the_github_token_for_the_search_alone(
    monkeypatch, tmp_path, capsys
):
    # The ranking calls the search, which has its own quota, apart from the 60 per hour.
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        collect_command,
        "SOURCE_KINDS",
        (
            SourceKind(
                "github_most_starred", (WorkingSource("github_most_starred"),), None
            ),
        ),
    )

    assert cli.main(["collect"]) == 0
    error_output = capsys.readouterr().err
    assert "INFO k_b.cli: sources to collect: github_most_starred\n" in error_output
    assert "KB_GITHUB_TOKEN" not in error_output


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


def write_state_catalogs(data_dir):
    """Two extracts of Zotero and two catalogs of CISA KEV, not imported yet."""
    paths = []
    for collection in ("2026-10-05T093000Z", "2026-10-06T093000Z"):
        extract_path = (
            data_dir / "raw" / "selected_library" / "zotero" / f"{collection}.json"
        )
        extract_path.parent.mkdir(parents=True, exist_ok=True)
        extract_path.write_bytes(b"[]\n")
        catalog_dir = data_dir / "raw" / "automated_watch" / "cisa_kev"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = catalog_dir / f"{collection}.csv"
        shutil.copyfile(FIXTURES_DIR / "cisa_kev_extract.csv", catalog_path)
        paths += [extract_path, catalog_path]
    return paths


def test_import_keeps_only_the_last_extract_and_catalog_imported(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    older_extract, older_catalog, last_extract, last_catalog = write_state_catalogs(
        tmp_path
    )

    exit_code = cli.main(["import"])

    assert exit_code == 0
    assert "superseded raw files deleted: 2" in capsys.readouterr().out
    assert (older_extract.exists(), older_catalog.exists()) == (False, False)
    assert (last_extract.exists(), last_catalog.exists()) == (True, True)


def test_a_failed_import_deletes_no_raw_file(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    paths = write_state_catalogs(tmp_path)

    def fail_to_import(*arguments):
        raise sqlite3.OperationalError("database is locked")

    def refuse_to_purge(*arguments):
        raise AssertionError("purged after a failed import")

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)
    monkeypatch.setattr(pipeline, "delete_superseded_raw_files", refuse_to_purge)

    assert cli.main(["import"]) == 1
    assert all(path.exists() for path in paths)


def test_a_failed_purge_without_a_reason_names_its_type_only(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    write_state_catalogs(tmp_path)

    def fail_to_delete(store, key):
        raise OSError("raised by code, without an errno")

    monkeypatch.setattr(pipeline.RawStore, "delete", fail_to_delete)

    assert cli.main(["import"]) == 1
    error_output = capsys.readouterr().err
    assert "import committed, raw purge failed: OSError; run kb import again" in (
        error_output
    )
    assert "None" not in error_output


def test_a_failed_purge_keeps_the_import_exits_1_and_the_next_import_purges(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    older_extract, older_catalog, _, _ = write_state_catalogs(tmp_path)

    def fail_to_delete(store, key):
        raise PermissionError(13, "Permission denied", str(tmp_path / key))

    with monkeypatch.context() as patch:
        patch.setattr(pipeline.RawStore, "delete", fail_to_delete)
        patch.setattr(import_command, "datetime", FrozenDatetime)
        assert cli.main(["import"]) == 1

    error_output = capsys.readouterr().err
    assert (
        "import committed, raw purge failed: PermissionError (Permission denied)"
        in (error_output)
    )
    assert "2026-10-05T093000Z" not in error_output
    assert older_extract.exists()
    connection = sqlite3.connect(tmp_path / "k-b.sqlite")
    assert connection.execute("SELECT count(*) FROM raw_data").fetchone() == (4,)
    connection.close()

    assert cli.main(["import"]) == 0
    assert (older_extract.exists(), older_catalog.exists()) == (False, False)


def test_a_failed_purge_leaves_the_summary_of_the_import_it_committed(
    monkeypatch, tmp_path, capsys
):
    """The summary is printed before the purge, so that an import that committed says what it
    wrote even when the purge fails."""
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    write_state_catalogs(tmp_path)
    capsys.readouterr()

    def fail_to_delete(store, key):
        raise PermissionError(13, "Permission denied", str(tmp_path / key))

    monkeypatch.setattr(pipeline.RawStore, "delete", fail_to_delete)

    assert cli.main(["import"]) == 1
    output = capsys.readouterr()
    assert "raw files read: 4" in output.out
    assert "superseded raw files deleted" not in output.out
    assert "import committed, raw purge failed: PermissionError" in output.err


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

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)

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

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)

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

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)

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


@pytest.mark.parametrize(
    ("has_failed", "has_done", "exit_code"),
    [
        (False, True, cli.ExitCode.SUCCEEDED),
        (False, False, cli.ExitCode.SUCCEEDED),
        (True, True, cli.ExitCode.PARTIAL_FAILURE),
        (True, False, cli.ExitCode.FAILED),
    ],
)
def test_a_part_that_failed_gives_4_beside_a_part_done_and_1_alone(
    has_failed, has_done, exit_code
):
    """The same result, the same code, for kb collect, kb write-tops and kb digest."""
    assert find_exit_code(has_failed=has_failed, has_done=has_done) == exit_code


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
    """A SIGTERM handler set before kb runs, which kb must set back; without it, a kb that sets
    none would leave the default one, which kills pytest."""

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
    """Every table, row by row, as SQL text, as in etl/test_load.py, which cannot be imported
    from here."""
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


@pytest.fixture
def test_tops(monkeypatch):
    """The tops of kb write-tops, read with the size of the recorded responses: 3 each."""
    monkeypatch.setattr(write_tops_command, "TOPS", TEST_TOPS)


@pytest.fixture
def data_and_vault_dirs(monkeypatch, tmp_path):
    data_dir, vault_dir = tmp_path / "data", tmp_path / "vault"
    data_dir.mkdir()
    vault_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_VAULT_DIR", str(vault_dir))
    return data_dir, vault_dir


def write_rankings_of_each_top(data_dir, *collection_names):
    return {
        top.name: [write_ranking(data_dir, top, name) for name in collection_names]
        for top in TEST_TOPS
    }


def list_sheets(vault_dir):
    return sorted(
        path.relative_to(vault_dir).as_posix() for path in vault_dir.rglob("*.md")
    )


def test_write_tops_writes_the_sheets_of_each_top_then_deletes_the_older_rankings(
    data_and_vault_dirs, test_tops, capsys
):
    data_dir, vault_dir = data_and_vault_dirs
    rankings = write_rankings_of_each_top(
        data_dir, "2026-10-05T093000Z", "2026-10-12T093000Z"
    )

    exit_code = cli.main(["write-tops"])

    assert exit_code == 0
    assert list_sheets(vault_dir) == [
        "veille/tops/most_forked/2026-10-05.md",
        "veille/tops/most_forked/2026-10-12.md",
        "veille/tops/most_starred/2026-10-05.md",
        "veille/tops/most_starred/2026-10-12.md",
    ]
    for older, last in rankings.values():
        assert (older.exists(), last.exists()) == (False, True)
    output = capsys.readouterr().out
    for top_name in ("most_starred", "most_forked"):
        assert (
            f"{top_name} sheets: written 2,"
            " rankings skipped (sheet of their day exists) 0,"
            " superseded rankings deleted 1, unreadable rankings kept 0\n"
        ) in output


def test_write_tops_again_writes_nothing_new(data_and_vault_dirs, test_tops, capsys):
    data_dir, _ = data_and_vault_dirs
    write_rankings_of_each_top(data_dir, "2026-10-05T093000Z")
    cli.main(["write-tops"])
    capsys.readouterr()

    assert cli.main(["write-tops"]) == 0
    assert (
        "most_starred sheets: written 0,"
        " rankings skipped (sheet of their day exists) 1,"
        " superseded rankings deleted 0, unreadable rankings kept 0\n"
    ) in capsys.readouterr().out


def test_write_tops_without_ranking_says_so_and_succeeds(
    data_and_vault_dirs, test_tops, capsys
):
    _, vault_dir = data_and_vault_dirs

    assert cli.main(["write-tops"]) == 0
    assert capsys.readouterr().out == (
        "most_starred sheets: no ranking\nmost_forked sheets: no ranking\n"
    )
    assert list_sheets(vault_dir) == []


@pytest.mark.parametrize("vault_dir_variable", [None, ""])
def test_write_tops_without_kb_vault_dir_runs_nothing_and_exits_2(
    monkeypatch, data_and_vault_dirs, test_tops, capsys, vault_dir_variable
):
    data_dir, _ = data_and_vault_dirs
    if vault_dir_variable is None:
        monkeypatch.delenv("KB_VAULT_DIR")
    else:
        monkeypatch.setenv("KB_VAULT_DIR", vault_dir_variable)
    rankings = write_rankings_of_each_top(
        data_dir, "2026-10-05T093000Z", "2026-10-12T093000Z"
    )

    assert cli.main(["write-tops"]) == cli.ExitCode.NOT_STARTED
    assert all(path.exists() for paths in rankings.values() for path in paths)
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: KB_VAULT_DIR not set; the sheets of the tops"
        " are written in the vault$",
        (data_dir / "logs" / "kb.log").read_text("utf-8"),
        re.MULTILINE,
    )
    assert capsys.readouterr().out == ""


def test_write_tops_with_a_vault_that_does_not_exist_creates_no_folder_and_exits_2(
    monkeypatch, data_and_vault_dirs, test_tops, tmp_path, capsys
):
    data_dir, _ = data_and_vault_dirs
    absent_vault = tmp_path / "typo"
    monkeypatch.setenv("KB_VAULT_DIR", str(absent_vault))
    write_rankings_of_each_top(data_dir, "2026-10-05T093000Z")

    assert cli.main(["write-tops"]) == cli.ExitCode.NOT_STARTED
    assert not absent_vault.exists()
    error_output = capsys.readouterr().err
    assert "KB_VAULT_DIR is not an existing directory; no folder is created" in (
        error_output
    )
    assert str(absent_vault) not in error_output


def test_a_sheet_not_written_keeps_its_rankings_exits_4_and_the_other_top_is_written(
    monkeypatch, data_and_vault_dirs, test_tops, capsys
):
    data_dir, vault_dir = data_and_vault_dirs
    rankings = write_rankings_of_each_top(
        data_dir, "2026-10-05T093000Z", "2026-10-12T093000Z"
    )
    write_file_atomically = vault_files.write_file_atomically

    def refuse_the_most_starred(path, content):
        if "most_starred" in path.parts:
            raise PermissionError(13, "Permission denied", str(path))
        write_file_atomically(path, content)

    monkeypatch.setattr(vault_files, "write_file_atomically", refuse_the_most_starred)

    assert cli.main(["write-tops"]) == cli.ExitCode.PARTIAL_FAILURE
    assert all(path.exists() for path in rankings["most_starred"])
    assert [path.exists() for path in rankings["most_forked"]] == [False, True]
    assert list_sheets(vault_dir) == [
        "veille/tops/most_forked/2026-10-05.md",
        "veille/tops/most_forked/2026-10-12.md",
    ]
    error_output = capsys.readouterr().err
    assert (
        "top sheets failed: most_starred: PermissionError (Permission denied);"
        " run kb write-tops again"
    ) in error_output
    assert str(vault_dir) not in error_output


def test_an_unreadable_ranking_is_kept_and_write_tops_exits_4_with_the_sheets_written(
    data_and_vault_dirs, test_tops, capsys
):
    """Fail closed: a ranking kept unread is never a success, and the sheets written are kept, so
    the code is the one of a partial failure."""
    data_dir, vault_dir = data_and_vault_dirs
    rankings = write_rankings_of_each_top(data_dir, "2026-10-05T093000Z")
    unreadable = write_ranking(data_dir, TEST_TOPS[0], "2026-10-12T093000Z", b"[]")

    assert cli.main(["write-tops"]) == cli.ExitCode.PARTIAL_FAILURE
    assert unreadable.exists()
    assert rankings["most_starred"][0].exists()
    assert len(list_sheets(vault_dir)) == 2
    assert (
        "most_starred sheets: written 1,"
        " rankings skipped (sheet of their day exists) 0,"
        " superseded rankings deleted 0, unreadable rankings kept 1\n"
    ) in capsys.readouterr().out


def test_a_sigterm_while_a_sheet_is_written_stops_write_tops_and_deletes_no_ranking(
    monkeypatch, data_and_vault_dirs, test_tops, sigterm_handler_of_the_test
):
    data_dir, vault_dir = data_and_vault_dirs
    rankings = write_rankings_of_each_top(
        data_dir, "2026-10-05T093000Z", "2026-10-12T093000Z"
    )
    write_file_atomically = vault_files.write_file_atomically

    def write_then_receive_sigterm(path, content):
        write_file_atomically(path, content)
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(
        vault_files, "write_file_atomically", write_then_receive_sigterm
    )

    exit_code = cli.main(["write-tops"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert all(path.exists() for paths in rankings.values() for path in paths)
    assert list_sheets(vault_dir) == ["veille/tops/most_starred/2026-10-05.md"]
    assert list_hidden_files(vault_dir) == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def test_kb_import_writes_nothing_in_the_vault(data_and_vault_dirs, test_tops):
    data_dir, vault_dir = data_and_vault_dirs
    cli.main(["create-db"])
    rankings = write_rankings_of_each_top(
        data_dir, "2026-10-05T093000Z", "2026-10-12T093000Z"
    )

    assert cli.main(["import"]) == 0
    assert list(vault_dir.iterdir()) == []
    assert all(path.exists() for paths in rankings.values() for path in paths)


def test_kb_help_lists_write_tops(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])

    assert re.search(
        r"^    write-tops +write the sheet of each top ranking",
        capsys.readouterr().out,
        re.MULTILINE,
    )


def test_a_folder_of_a_top_linked_elsewhere_is_refused_exits_4_and_the_other_top_is_written(
    data_and_vault_dirs, test_tops, tmp_path, capsys
):
    data_dir, vault_dir = data_and_vault_dirs
    rankings = write_rankings_of_each_top(
        data_dir, "2026-10-05T093000Z", "2026-10-12T093000Z"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille" / "tops").mkdir(parents=True)
    (vault_dir / "veille" / "tops" / "most_starred").symlink_to(
        elsewhere, target_is_directory=True
    )

    assert cli.main(["write-tops"]) == cli.ExitCode.PARTIAL_FAILURE
    assert all(path.exists() for path in rankings["most_starred"])
    assert list(elsewhere.iterdir()) == []
    assert list_sheets(vault_dir / "veille" / "tops" / "most_forked") == [
        "2026-10-05.md",
        "2026-10-12.md",
    ]
    error_output = capsys.readouterr().err
    assert (
        "top sheets failed: most_starred: vault_link_refused: veille/tops/most_starred is a"
        " symbolic link\n"
    ) in error_output
    assert str(vault_dir) not in error_output


def test_write_tops_exits_1_when_both_tops_are_refused(
    data_and_vault_dirs, test_tops, tmp_path
):
    data_dir, vault_dir = data_and_vault_dirs
    rankings = write_rankings_of_each_top(data_dir, "2026-10-05T093000Z")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille").symlink_to(elsewhere, target_is_directory=True)

    assert cli.main(["write-tops"]) == cli.ExitCode.FAILED
    assert all(path.exists() for paths in rankings.values() for path in paths)
    assert list(elsewhere.iterdir()) == []


def test_write_tops_exits_1_when_its_only_rankings_are_unreadable(
    data_and_vault_dirs, test_tops
):
    data_dir, vault_dir = data_and_vault_dirs
    for top in TEST_TOPS:
        write_ranking(data_dir, top, "2026-10-05T093000Z", b"[]")

    assert cli.main(["write-tops"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []


def test_a_top_without_ranking_succeeds_beside_a_top_refused_so_write_tops_exits_4(
    data_and_vault_dirs, test_tops, tmp_path
):
    """A top without ranking ran to its end: as a source with nothing new for kb collect."""
    data_dir, vault_dir = data_and_vault_dirs
    write_ranking(data_dir, TEST_TOPS[0], "2026-10-05T093000Z")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille" / "tops").mkdir(parents=True)
    (vault_dir / "veille" / "tops" / TEST_TOPS[0].name).symlink_to(
        elsewhere, target_is_directory=True
    )

    assert cli.main(["write-tops"]) == cli.ExitCode.PARTIAL_FAILURE


# The subjects of the tests, never the real ones, as in tests/ai_api/test_digest_router.py.
TEST_DIGEST_SUBJECTS = (
    DigestSubject("security_alerts", "failles et alertes de sécurité"),
    DigestSubject("agent_tools", "outils et cadres d'agents"),
    DigestSubject("research", "articles de recherche"),
)
# The UTC day of the run, the one of the end of the window of make_response.
DIGEST_DAY = date(2026, 10, 21)
RESEARCH_DIGEST = AGENT_DIGEST.model_copy(update={"subject": "research"})
RESEARCH_FAILED = FailedSubjectSchema(
    subject="research", stage="write", error="llm_timeout"
)


@pytest.fixture
def digest_environment(monkeypatch, data_and_vault_dirs):
    """kb digest with its key, the subjects of the tests and the day of the run."""
    monkeypatch.setenv("KB_AI_API_KEY_KB_DIGEST", TEST_API_KEY)
    monkeypatch.setattr(digest_command, "DIGEST_SUBJECTS", TEST_DIGEST_SUBJECTS)
    monkeypatch.setattr(digest_command, "read_today", lambda: DIGEST_DAY)
    return data_and_vault_dirs


def answer_digests(monkeypatch, handle):
    """The AI API of kb digest: handle answers each request, kept in the list returned."""
    requests = []

    def keep_and_handle(request):
        requests.append(request)
        return handle(request)

    monkeypatch.setattr(
        digest_command,
        "build_ai_api_client",
        partial(build_ai_api_client, transport=httpx2.MockTransport(keep_and_handle)),
    )
    return requests


def answer_with(response=None, status=200, content=None, headers=None):
    def handle(request):
        body = to_body(response or make_response()) if content is None else content
        return httpx2.Response(status, content=body, headers=headers)

    return handle


def read_kb_log(data_dir):
    return (data_dir / "logs" / "kb.log").read_text("utf-8")


def test_digest_writes_the_sheet_of_each_subject_and_says_so(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    requests = answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )

    exit_code = cli.main(["digest"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert [(r.method, r.url.path) for r in requests] == [("POST", "/digests")]
    assert list_sheets(vault_dir) == [
        "veille/agent_tools/2026-10-21.md",
        "veille/research/2026-10-21.md",
    ]
    assert capsys.readouterr().out == (
        "agent_tools: sheet written, veille/agent_tools/2026-10-21.md\n"
        "research: sheet written, veille/research/2026-10-21.md\n"
        f"digests: written 2, failed 0; model gpt-6-luna, request_id {REQUEST_ID}\n"
    )


def test_digest_without_digest_in_the_window_says_so_and_succeeds(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(monkeypatch, answer_with(make_response([])))

    assert cli.main(["digest"]) == cli.ExitCode.SUCCEEDED
    assert capsys.readouterr().out == (
        f"digests: none in the window; model gpt-6-luna, request_id {REQUEST_ID}\n"
    )
    assert list_sheets(vault_dir) == []


def test_digest_with_a_sheet_of_the_day_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys
):
    data_dir, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    sheet = vault_dir / "veille" / "research" / "2026-10-21.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"read by Sabine\n")

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert sheet.read_bytes() == b"read by Sabine\n"
    assert list_sheets(vault_dir) == ["veille/research/2026-10-21.md"]
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: no digest asked: sheet_exists:"
        r" veille/research/2026-10-21\.md is there; kb digest never rewrites a sheet$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert str(vault_dir) not in output.err


def test_digest_with_a_folder_linked_elsewhere_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, tmp_path
):
    _, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille").symlink_to(elsewhere, target_is_directory=True)

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert list(elsewhere.iterdir()) == []


def test_digest_with_a_file_in_place_of_a_folder_asks_nothing_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    (vault_dir / "veille").write_bytes(b"a file\n")

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert requests == []
    error_output = capsys.readouterr().err
    assert "no digest asked: NotADirectoryError (Not a directory)" in error_output
    assert str(vault_dir) not in error_output


@pytest.mark.parametrize("vault_dir_variable", [None, ""])
def test_digest_without_kb_vault_dir_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys, vault_dir_variable
):
    data_dir, _ = digest_environment
    if vault_dir_variable is None:
        monkeypatch.delenv("KB_VAULT_DIR")
    else:
        monkeypatch.setenv("KB_VAULT_DIR", vault_dir_variable)
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: KB_VAULT_DIR not set; the digests are written"
        " in the vault$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )


def test_digest_with_a_vault_that_does_not_exist_creates_no_folder_and_exits_2(
    monkeypatch, digest_environment, tmp_path, capsys
):
    absent_vault = tmp_path / "typo"
    monkeypatch.setenv("KB_VAULT_DIR", str(absent_vault))
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert not absent_vault.exists()
    error_output = capsys.readouterr().err
    assert "KB_VAULT_DIR is not an existing directory; no folder is created" in (
        error_output
    )
    assert str(absent_vault) not in error_output


def test_digest_without_its_key_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys
):
    monkeypatch.delenv("KB_AI_API_KEY_KB_DIGEST")
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert "ERROR k_b.cli: KB_AI_API_KEY_KB_DIGEST: not set" in capsys.readouterr().err


def test_digest_without_the_ai_api_writes_nothing_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    data_dir, vault_dir = digest_environment

    def refuse_the_connection(request):
        raise httpx2.ConnectError("refused", request=request)

    answer_digests(monkeypatch, refuse_the_connection)

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: digests not received: ai_api_unavailable$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )
    assert capsys.readouterr().out == ""


def test_digest_with_a_refused_key_writes_nothing_names_its_variable_never_the_key(
    monkeypatch, digest_environment, capsys
):
    """The request went out: 1, as a source that answers 401 to kb collect."""
    data_dir, vault_dir = digest_environment
    answer_digests(
        monkeypatch,
        answer_with(
            status=401,
            content=b'{"error": "invalid_api_key"}',
            headers={"X-Request-ID": REQUEST_ID, "WWW-Authenticate": "Bearer"},
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    output = capsys.readouterr()
    assert (
        "digests not received: ai_api_unauthorized, HTTP 401, error invalid_api_key,"
        f" X-Request-ID {REQUEST_ID}; the AI API refused the key of KB_AI_API_KEY_KB_DIGEST"
    ) in output.err
    log = read_kb_log(data_dir)
    for text in (output.out, output.err, log):
        assert TEST_API_KEY not in text


def test_digest_on_a_failure_of_the_ai_api_exits_1_at_once_with_its_retry_after(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    requests = answer_digests(
        monkeypatch,
        answer_with(
            status=503,
            content=b'{"error": "llm_rate_limited"}',
            headers={"X-Request-ID": REQUEST_ID, "Retry-After": "20"},
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert len(requests) == 1
    assert list(vault_dir.iterdir()) == []
    assert (
        "digests not received: ai_api_failed, HTTP 503, error llm_rate_limited,"
        f" X-Request-ID {REQUEST_ID}, Retry-After 20\n"
    ) in capsys.readouterr().err


def test_digest_on_a_response_out_of_the_schema_writes_nothing_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    response = make_response([AGENT_DIGEST.model_copy(update={"subject": "tops"})])
    answer_digests(monkeypatch, answer_with(response))

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    assert (
        "digests not received: ai_api_invalid_response, HTTP 200,"
        f" digests.0.subject (subject_not_listed), request_id {REQUEST_ID}\n"
    ) in capsys.readouterr().err


def test_digest_with_failed_subjects_writes_the_others_names_them_and_exits_4(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST], [RESEARCH_FAILED]))
    )

    assert cli.main(["digest"]) == cli.ExitCode.PARTIAL_FAILURE
    assert list_sheets(vault_dir) == ["veille/agent_tools/2026-10-21.md"]
    output = capsys.readouterr()
    assert "ERROR k_b.cli: research: digest failed: llm_timeout at the stage write" in (
        output.err
    )
    assert output.out.endswith(
        f"digests: written 1, failed 1; model gpt-6-luna, request_id {REQUEST_ID}\n"
    )


def test_digest_with_failed_subjects_only_exits_1(monkeypatch, digest_environment):
    _, vault_dir = digest_environment
    answer_digests(monkeypatch, answer_with(make_response([], [RESEARCH_FAILED])))

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []


def test_a_sheet_not_written_exits_4_and_the_other_sheet_is_written(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )
    write_file_atomically = vault_files.write_file_atomically

    def refuse_the_agent_tools(path, content):
        if "agent_tools" in path.parts:
            raise PermissionError(13, "Permission denied", str(path))
        write_file_atomically(path, content)

    monkeypatch.setattr(vault_files, "write_file_atomically", refuse_the_agent_tools)

    assert cli.main(["digest"]) == cli.ExitCode.PARTIAL_FAILURE
    assert list_sheets(vault_dir) == ["veille/research/2026-10-21.md"]
    error_output = capsys.readouterr().err
    assert (
        "agent_tools: sheet not written: PermissionError (Permission denied)"
    ) in error_output
    assert str(vault_dir) not in error_output


def test_a_sigterm_while_a_sheet_is_written_stops_digest_and_keeps_the_sheet(
    monkeypatch, digest_environment, sigterm_handler_of_the_test
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )
    write_file_atomically = vault_files.write_file_atomically

    def write_then_receive_sigterm(path, content):
        write_file_atomically(path, content)
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(
        vault_files, "write_file_atomically", write_then_receive_sigterm
    )

    exit_code = cli.main(["digest"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert list_sheets(vault_dir) == ["veille/agent_tools/2026-10-21.md"]
    assert list_hidden_files(vault_dir) == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def test_kb_help_lists_digest(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])

    assert re.search(
        r"^    digest +ask the AI API for the digests of the watch",
        capsys.readouterr().out,
        re.MULTILINE,
    )
