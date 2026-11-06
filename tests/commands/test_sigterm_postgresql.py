"""SIGTERM during a query of kb import on PostgreSQL: the import is undone whole, and kb exits with
its code of a stop by SIGTERM (.claude/rules/poc.md, rule 6)."""

import os
import signal
import threading

import psycopg
import pytest
from etl.test_transform import copy_fixture

from k_b import cli
from k_b.commands.sigterm import StoppedBySigtermError
from k_b.database import writing
from k_b.database.location import DATABASE_URL_VARIABLE
from k_b.database.postgresql import PostgresConnection

pytestmark = pytest.mark.postgresql


def count_raw_data(location):
    connection = psycopg.connect(location.value)
    try:
        return connection.execute("SELECT count(*) FROM raw_data").fetchone()[0]
    finally:
        connection.close()


def test_a_sigterm_during_a_query_on_postgresql_undoes_the_import_and_exits_with_its_code(
    monkeypatch, tmp_path, postgresql_base, sigterm_handler_of_the_test
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, postgresql_base.value)
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    write_vulnerability = writing.WRITER_BY_KIND["vulnerability"]

    # The container is stopped while the base answers a query: the signal comes from another
    # thread, as from docker stop, and finds kb waiting for PostgreSQL.
    def write_during_a_sigterm(connection, item, raw_data_id):
        threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
        connection.execute("SELECT pg_sleep(5)")
        return write_vulnerability(connection, item, raw_data_id)

    monkeypatch.setitem(writing.WRITER_BY_KIND, "vulnerability", write_during_a_sigterm)

    exit_code = cli.main(["import"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert count_raw_data(postgresql_base) == 0
    assert list(tmp_path.glob("journals/import-journal-*.jsonl")) == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def commit_canceled_by_psycopg(self):
    """A SIGTERM received while psycopg waits for the answer to COMMIT: psycopg cancels the query,
    the server undoes the transaction, and the signal is raised once the connection is idle."""
    self.rollback()
    raise StoppedBySigtermError


def test_a_sigterm_during_the_commit_on_postgresql_keeps_the_journal_and_says_the_outcome_is_unknown(
    monkeypatch, tmp_path, capsys, postgresql_base, sigterm_handler_of_the_test
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, postgresql_base.value)
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    capsys.readouterr()
    monkeypatch.setattr(PostgresConnection, "commit", commit_canceled_by_psycopg)

    exit_code = cli.main(["import"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    # Whether the server committed is not known to kb: the journal is kept, as a journal lost
    # would leave an import without trace, and the log says only what kb saw.
    [journal_path] = tmp_path.glob("journals/import-journal-*.jsonl")
    error_output = capsys.readouterr().err
    assert (
        "INFO k_b.etl.load: import commit interrupted, outcome unknown, journal kept:"
        f" '{journal_path.name}'" in error_output
    )
    assert "import committed" not in error_output
