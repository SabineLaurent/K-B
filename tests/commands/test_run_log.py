"""The log of kb: its lines dated in UTC, its file, its rotation and the errors it records."""

import contextlib
import logging
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, time, timedelta

import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import HttpResponseError
from commands.cli_helpers import (
    LOG_LINE_DATE,
    collected_kinds,
)
from etl.test_extract import BrokenSource, WorkingSource
from jobs.storage_fakes import (
    SPOTTED_BLOB_NAME,
    TEST_ACCOUNT_URL,
    FakeTransport,
    answer_forbidden_naming_the_blob,
    names_the_spotted_blob,
)

from k_b import cli
from k_b.commands import (
    collect_command,
)
from k_b.jobs.exchange_storage import open_container_client


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

    # The line of the start of kb import, then the error.
    [_, file_line] = (tmp_path / "logs" / "kb.log").read_text("utf-8").splitlines()
    assert re.fullmatch(
        rf"{LOG_LINE_DATE} ERROR k_b\.cli: .*; create it with kb create-db", file_line
    )
    assert file_line in capsys.readouterr().err.splitlines()


def test_an_exception_kb_does_not_handle_is_logged_once_and_exits_1(
    monkeypatch, tmp_path, capsys
):
    def failing_collect(data_dir, environ):
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


def test_a_rotation_deletes_no_log_file_only_the_purge_does(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    rotated_paths = [
        logs_dir / f"kb.log.{(yesterday - timedelta(days=days)).isoformat()}"
        for days in range(1, 40)
    ]
    for path in rotated_paths:
        path.write_text("a line of before\n", encoding="utf-8")
    log_path = logs_dir / "kb.log"
    log_path.write_text("a line of yesterday\n", encoding="utf-8")
    yesterday_noon = datetime.combine(yesterday, time(12), tzinfo=UTC).timestamp()
    os.utime(log_path, (yesterday_noon, yesterday_noon))

    with cli.logging_to(tmp_path):
        logging.getLogger("k_b.test").info("a line of today")

    assert all(path.exists() for path in rotated_paths)


class StorageCredential:
    """A token for the storage, without the identity endpoint."""

    def get_token(self, *scopes, **kwargs):
        return AccessToken("token-of-the-test", 4102444800)


def test_the_azure_sdk_writes_no_url_of_a_blob_in_the_log(tmp_path, capsys):
    """A transfer names its blob in its URL, which the SDK logs at INFO: the name of a clip is its
    title (#412)."""
    storage = FakeTransport(answer_forbidden_naming_the_blob)

    with (
        cli.logging_to(tmp_path),
        open_container_client(
            TEST_ACCOUNT_URL, "smoke-test", StorageCredential(), transport=storage
        ) as container,
        contextlib.suppress(HttpResponseError),
    ):
        container.download_blob(SPOTTED_BLOB_NAME).readall()

    [transfer] = storage.adapter.requests
    assert names_the_spotted_blob(transfer.url)
    assert not names_the_spotted_blob((tmp_path / "logs" / "kb.log").read_text("utf-8"))
    assert not names_the_spotted_blob(capsys.readouterr().err)


@pytest.mark.parametrize(
    ("logger_name", "level"),
    [
        # Its requests at INFO, with their URL.
        ("httpx2", logging.WARNING),
        # Its WARNING lines quote the text of an answer, unescaped (review of #412).
        ("azure", logging.ERROR),
        # Its WARNING lines may quote a whole URL, the one of a blob (urllib3/connection.py).
        ("urllib3", logging.ERROR),
    ],
)
def test_a_library_that_logs_what_an_answer_says_is_held_and_set_back(
    tmp_path, logger_name, level
):
    library_logger = logging.getLogger(logger_name)
    level_before = library_logger.level

    with cli.logging_to(tmp_path):
        assert library_logger.level == level

    assert library_logger.level == level_before
