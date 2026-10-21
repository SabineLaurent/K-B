"""The end-to-end test of each source: kb create-db, KB_COLLECT_ONLY=<source> kb collect, then
kb import, on the real source, in a new data directory; each command exits 0 and the items of
the source are in the base.

Left out of uv run pytest (tests/conftest.py). Run on the Mac, in a container and as a job by
uv run pytest -m e2e, with the settings of the sources in the environment (KB_GITHUB_TOKEN,
KB_ZOTERO_DIR, KB_VAULT_DIR, GOOGLE_APPLICATION_CREDENTIALS). gh_archive runs a real BigQuery
query (docs/bigquery.md).
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from k_b.commands.exit_codes import ExitCode
from k_b.database.connection import DATABASE_FILE_NAME
from k_b.etl.collected_sources import COLLECT_ONLY_VARIABLE, VARIABLE_BY_SOURCE_NAME
from k_b.etl.raw_store import AUTOMATED_WATCH_DIR_NAME, make_source_folder_key
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


def run_kb(command, environ, console_dir):
    """Run kb <command> and keep what it printed in console_dir; return its exit code alone, so
    that a failed assert never shows the environment, which holds the GitHub token."""
    result = subprocess.run(  # noqa: S603 — runs the kb of this interpreter, fixed arguments
        [str(KB_PATH), command],
        capture_output=True,
        text=True,
        env=environ,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    (console_dir / f"{command}.out").write_text(result.stdout)
    (console_dir / f"{command}.err").write_text(result.stderr)
    return result.returncode


def count_rows(database_path, query, *parameters):
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        return connection.execute(query, parameters).fetchone()[0]
    finally:
        connection.close()


def count_raw_files(folder):
    return sum(
        1
        for path in folder.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )


@pytest.mark.e2e
@pytest.mark.parametrize("source_name", [kind.folder_prefix for kind in SOURCE_KINDS])
def test_kb_collects_and_imports_the_real_source(source_name, tmp_path):
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

    create_db_exit_code = run_kb("create-db", environ, console_dir)
    collect_exit_code = run_kb(
        "collect", {**environ, COLLECT_ONLY_VARIABLE: source_name}, console_dir
    )
    import_exit_code = run_kb("import", environ, console_dir)

    assert create_db_exit_code == ExitCode.SUCCEEDED
    assert collect_exit_code == ExitCode.SUCCEEDED
    assert import_exit_code == ExitCode.SUCCEEDED
    database_path = data_dir / DATABASE_FILE_NAME
    item_count = count_rows(database_path, "SELECT COUNT(*) FROM item")
    if source_name in TOP_FOLDER_KEY_BY_SOURCE_NAME:
        folder = data_dir / TOP_FOLDER_KEY_BY_SOURCE_NAME[source_name]
        assert count_raw_files(folder) >= 1
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
