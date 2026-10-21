"""The end-to-end test of each source: kb create-db, KB_COLLECT_ONLY=<source> kb collect, then
kb import, on the real source, in a new data directory; each command exits 0 and the items of
the source are in the base, with no rejection.

Left out of uv run pytest (tests/conftest.py). Run on the Mac by uv run pytest -m e2e, with the
settings of the sources in the environment; to be run the same way in a container (#200) and as a
job. Without KB_ZOTERO_DIR, KB_VAULT_DIR or GOOGLE_APPLICATION_CREDENTIALS, the test of its source
is skipped. KB_GITHUB_TOKEN is optional: without it, the GitHub sources run on 60 requests per
hour instead of 5,000. gh_archive runs a real BigQuery query (docs/bigquery.md).

Once a test ends, however it ends, its data directory is deleted but its logs/: what a test keeps
is its console and the log of kb (docs/registre-traitements.md, step 10 of the sorting).
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from k_b.commands.environment import DATA_DIR_VARIABLE
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOG_FILE_PATH, LOGGER_NAME
from k_b.database.connection import DATABASE_FILE_NAME
from k_b.etl.collected_sources import COLLECT_ONLY_VARIABLE, VARIABLE_BY_SOURCE_NAME
from k_b.etl.raw_store import (
    AUTOMATED_WATCH_DIR_NAME,
    RawStore,
    make_source_folder_key,
)
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources import (
    arxiv,
    cisa_kev,
    clipping,
    gh_archive,
    github_advisories,
    github_most_forked,
    github_most_starred,
    github_releases,
    tldr,
    zotero,
)
from k_b.etl.sources.github_api import TOKEN_VARIABLE

# The kb of this interpreter, by its full path: the one of the environment under test.
KB_PATH = Path(sys.executable).with_name("kb")
# A source that does not answer stops its test, not the whole run.
COMMAND_TIMEOUT_SECONDS = 900
# The wait for kb to stop on SIGTERM, cleaning up (the copy of the Zotero base), before SIGKILL.
STOP_TIMEOUT_SECONDS = 30
# The kind of the items each source brings; a source missing here fails its test.
ITEM_KIND_BY_SOURCE_NAME = {
    cisa_kev.FOLDER_PREFIX: "vulnerability",
    github_releases.FOLDER_PREFIX: "release",
    github_advisories.FOLDER_PREFIX: "advisory",
    arxiv.FOLDER_PREFIX: "paper",
    tldr.FOLDER_PREFIX: "newsletter_article",
    zotero.FOLDER_PREFIX: "zotero_entry",
    clipping.FOLDER_PREFIX: "clip",
}
# The top rankings do not enter the base (decision "Tops", 2026-10-07): their raw folder.
TOP_FOLDER_KEY_BY_SOURCE_NAME = {
    name: make_source_folder_key(AUTOMATED_WATCH_DIR_NAME, name)
    for name in (github_most_starred.FOLDER_PREFIX, github_most_forked.FOLDER_PREFIX)
}
# A line of the log of kb above INFO: its date, then its level (commands/run_log.py).
LOG_LINE_ABOVE_INFO = re.compile(r"\S+ (WARNING|ERROR|CRITICAL) ")
# The only line above INFO that is not a case met: the quota of the GitHub API without
# KB_GITHUB_TOKEN (commands/collect_command.py), with which the GitHub tests run (plan of #25).
TOKEN_NOT_SET_WARNING = f"WARNING {LOGGER_NAME}: {TOKEN_VARIABLE} not set:"
# The folder of the log of kb in the data directory, the only one a test keeps.
LOG_DIR_NAME = LOG_FILE_PATH.parts[0]


def run_kb(command, console_dir):
    """Run kb <command> in the environment of this process and keep what it printed in
    console_dir; return its exit code. No variable here nor in subprocess holds the environment,
    and with it the GitHub token: a traceback that shows the locals cannot show it.

    A command past its timeout is sent SIGTERM, so that kb cleans up as on docker stop, then
    SIGKILL if it does not stop; what it printed until then is kept."""
    with subprocess.Popen(  # noqa: S603 — runs the kb of this interpreter, fixed arguments
        [str(KB_PATH), command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=COMMAND_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            stdout, stderr = stop(process)
            write_console(console_dir, command, stdout, stderr)
            raise
    write_console(console_dir, command, stdout, stderr)
    return process.returncode


def stop(process):
    """SIGTERM, then SIGKILL past STOP_TIMEOUT_SECONDS; what the process printed."""
    process.terminate()
    try:
        return process.communicate(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate()


def write_console(console_dir, command, stdout, stderr):
    for extension, output in (("out", stdout), ("err", stderr)):
        (console_dir / f"{command}.{extension}").write_text(output or "")


def delete_all_but_logs(data_dir):
    """Delete the raw files, the base (and its -wal and -shm) and the import logs, which hold
    the authors of Zotero and of arXiv, the clips and their URLs: logs/ alone is kept."""
    for entry in data_dir.iterdir():
        if entry.name == LOG_DIR_NAME:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def count_rows(database_path, query, *parameters):
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
    try:
        return connection.execute(query, parameters).fetchone()[0]
    finally:
        connection.close()


def count_log_lines_above_info(console_dir):
    """The WARNING, ERROR and CRITICAL lines of the commands run: a case a source logs and gives
    up without failing (tldr given up, a page not read) is a case met."""
    return sum(
        1
        for console_path in console_dir.glob("*.err")
        for line in console_path.read_text().splitlines()
        if LOG_LINE_ABOVE_INFO.match(line) and TOKEN_NOT_SET_WARNING not in line
    )


def count_rejections(data_dir):
    """The rejections of the import logs of data_dir: kb import exits 0 with them."""
    return sum(
        1
        for log_path in data_dir.glob("import-log-*.jsonl")
        for line in log_path.read_text().splitlines()
        if json.loads(line)["kind"] == "rejection"
    )


@pytest.mark.e2e
@pytest.mark.parametrize("source_name", [kind.folder_prefix for kind in SOURCE_KINDS])
def test_kb_collects_and_imports_the_real_source(source_name, tmp_path, monkeypatch):
    # Read before any command: a source without what it brings fails before the real calls.
    is_expected = (
        source_name in ITEM_KIND_BY_SOURCE_NAME
        or source_name in TOP_FOLDER_KEY_BY_SOURCE_NAME
        or source_name == gh_archive.FOLDER_PREFIX
    )
    assert is_expected, (
        f"{source_name}: what it brings is not in the expectations of this test"
    )
    variable = VARIABLE_BY_SOURCE_NAME.get(source_name)
    if variable is not None and not os.environ.get(variable):
        pytest.skip(f"{variable} not set")
    data_dir = tmp_path / "data"
    console_dir = tmp_path / "console"
    data_dir.mkdir()
    console_dir.mkdir()
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(data_dir))
    # Never the KB_COLLECT_ONLY of the terminal: kb collect gets the source of this test alone,
    # so that no other source runs, gh_archive and its BigQuery query above all.
    monkeypatch.delenv(COLLECT_ONLY_VARIABLE, raising=False)
    try:
        collect_and_import(source_name, data_dir, console_dir, monkeypatch)
    finally:
        # A failed assert, a timeout or a Ctrl-C deletes as well.
        delete_all_but_logs(data_dir)


def collect_and_import(source_name, data_dir, console_dir, monkeypatch):
    # Each exit code is checked as soon as its command ends: nothing is collected, BigQuery
    # least of all, after a command has failed.
    create_db_exit_code = run_kb("create-db", console_dir)
    assert create_db_exit_code == ExitCode.SUCCEEDED
    with monkeypatch.context() as collect_patch:
        collect_patch.setenv(COLLECT_ONLY_VARIABLE, source_name)
        collect_exit_code = run_kb("collect", console_dir)
    assert collect_exit_code == ExitCode.SUCCEEDED
    import_exit_code = run_kb("import", console_dir)
    assert import_exit_code == ExitCode.SUCCEEDED

    assert count_rejections(data_dir) == 0
    assert count_log_lines_above_info(console_dir) == 0
    database_path = data_dir / DATABASE_FILE_NAME
    item_count = count_rows(database_path, "SELECT COUNT(*) FROM item")
    if source_name in TOP_FOLDER_KEY_BY_SOURCE_NAME:
        # The rankings as kb write-tops lists them.
        folder_key = TOP_FOLDER_KEY_BY_SOURCE_NAME[source_name]
        assert len(RawStore(data_dir).list_file_keys(folder_key)) >= 1
        assert item_count == 0
    elif source_name == gh_archive.FOLDER_PREFIX:
        assert count_rows(database_path, "SELECT COUNT(*) FROM trend") >= 1
        assert item_count == 0
    else:
        kind = ITEM_KIND_BY_SOURCE_NAME[source_name]
        kind_count = count_rows(
            database_path, "SELECT COUNT(*) FROM item WHERE kind = ?", kind
        )
        assert kind_count >= 1
        assert kind_count == item_count
