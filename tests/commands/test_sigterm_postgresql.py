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


# A COMMIT that waits: a trigger deferred to the commit sleeps once per raw file registered.
WAIT_AT_COMMIT = """
CREATE FUNCTION wait_at_commit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_sleep(2);
    RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER wait_at_commit AFTER INSERT ON raw_data
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION wait_at_commit();
"""


def prepare_import_of_one_catalog(monkeypatch, tmp_path, capsys, location):
    """A PostgreSQL base and one CISA KEV catalog to import, the output read so far emptied."""
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, location.value)
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    capsys.readouterr()


def assert_the_journal_is_kept_with_the_outcome_unknown(tmp_path, error_output):
    # Whether the server committed is not known to kb: the journal is kept, as a journal lost
    # would leave an import without trace, and the log says only what kb saw.
    [journal_path] = tmp_path.glob("journals/import-journal-*.jsonl")
    assert (
        "INFO k_b.etl.load: import commit interrupted, outcome unknown, journal kept:"
        f" '{journal_path.name}'" in error_output
    )
    assert "import committed" not in error_output


def test_a_sigterm_during_the_commit_on_postgresql_keeps_the_journal_and_says_the_outcome_is_unknown(
    monkeypatch, tmp_path, capsys, postgresql_base, sigterm_handler_of_the_test
):
    prepare_import_of_one_catalog(monkeypatch, tmp_path, capsys, postgresql_base)
    server = psycopg.connect(postgresql_base.value, autocommit=True)
    server.execute(WAIT_AT_COMMIT)
    server.close()
    commit = PostgresConnection.commit

    # docker stop while psycopg waits for the answer to COMMIT: psycopg asks the server to cancel
    # it, and the server, still in the trigger deferred to the commit, undoes the import.
    def commit_during_a_sigterm(connection):
        threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGTERM)).start()
        commit(connection)

    monkeypatch.setattr(PostgresConnection, "commit", commit_during_a_sigterm)

    exit_code = cli.main(["import"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert count_raw_data(postgresql_base) == 0
    assert_the_journal_is_kept_with_the_outcome_unknown(
        tmp_path, capsys.readouterr().err
    )


def commit_after_the_cancel_timed_out(connection):
    """What psycopg does when the server does not answer its cancel within 5 s: it closes the
    connection, then raises the signal (psycopg 3.3.8, Connection.wait)."""
    connection._connection.pgconn.finish()
    raise StoppedBySigtermError


def test_a_connection_closed_by_psycopg_during_the_commit_still_exits_with_the_code_of_sigterm(
    monkeypatch, tmp_path, capsys, postgresql_base, sigterm_handler_of_the_test
):
    prepare_import_of_one_catalog(monkeypatch, tmp_path, capsys, postgresql_base)
    monkeypatch.setattr(PostgresConnection, "commit", commit_after_the_cancel_timed_out)

    exit_code = cli.main(["import"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert_the_journal_is_kept_with_the_outcome_unknown(
        tmp_path, capsys.readouterr().err
    )
