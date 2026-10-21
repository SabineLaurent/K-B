"""The end-to-end test of each source: kb create-db, KB_COLLECT_ONLY=<source> kb collect, then
kb import, on the real source, in a new data directory; each command exits 0 and the items of
the source are in the base, with no rejection.

Left out of uv run pytest (tests/conftest.py). Run on the Mac by uv run pytest -m e2e, with the
settings of the sources in the environment; to be run the same way in a container (#200) and as a
job. Without KB_ZOTERO_DIR, KB_VAULT_DIR or GOOGLE_APPLICATION_CREDENTIALS, the test of its source
is skipped. KB_GITHUB_TOKEN is optional: without it, the GitHub sources run on 60 requests per
hour instead of 5,000. gh_archive runs a real BigQuery query (docs/bigquery.md).
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from k_b.commands.exit_codes import ExitCode
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

# The kb of this interpreter, by its full path: the one of the environment under test.
KB_PATH = Path(sys.executable).with_name("kb")
# A source that does not answer stops its test, not the whole run.
COMMAND_TIMEOUT_SECONDS = 900
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


def run_kb(command, environ, console_dir):
    """Run kb <command> and keep what it printed in console_dir; return its exit code alone, so
    that a failed assert never shows the environment, which holds the GitHub token. A command
    past its timeout keeps what it printed until then."""
    try:
        result = subprocess.run(  # noqa: S603 — runs the kb of this interpreter, fixed arguments
            [str(KB_PATH), command],
            capture_output=True,
            text=True,
            env=environ,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        write_console(console_dir, command, error.stdout, error.stderr)
        raise
    write_console(console_dir, command, result.stdout, result.stderr)
    return result.returncode


def write_console(console_dir, command, stdout, stderr):
    """Its output as text, or as bytes: subprocess gives a timeout the bytes read, or None."""
    for extension, output in (("out", stdout), ("err", stderr)):
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        (console_dir / f"{command}.{extension}").write_text(output or "")


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
        if LOG_LINE_ABOVE_INFO.match(line)
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
def test_kb_collects_and_imports_the_real_source(source_name, tmp_path):
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
    # Never the KB_COLLECT_ONLY of the terminal: kb collect gets the source of this test alone,
    # so that no other source runs, gh_archive and its BigQuery query above all.
    environ = {
        name: value
        for name, value in os.environ.items()
        if name != COLLECT_ONLY_VARIABLE
    }
    environ["KB_DATA_DIR"] = str(data_dir)

    # Each exit code is checked as soon as its command ends: nothing is collected, BigQuery
    # least of all, after a command has failed.
    create_db_exit_code = run_kb("create-db", environ, console_dir)
    assert create_db_exit_code == ExitCode.SUCCEEDED
    collect_exit_code = run_kb(
        "collect", {**environ, COLLECT_ONLY_VARIABLE: source_name}, console_dir
    )
    assert collect_exit_code == ExitCode.SUCCEEDED
    import_exit_code = run_kb("import", environ, console_dir)
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
