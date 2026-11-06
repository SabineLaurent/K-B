"""SIGTERM during a query of kb import on PostgreSQL: the import is undone whole, and kb exits with
its code of a stop by SIGTERM (.claude/rules/poc.md, rule 6)."""

import os
import signal
import threading

import psycopg
import pytest
from etl.test_transform import copy_fixture

from k_b import cli
from k_b.database import writing
from k_b.database.location import DATABASE_URL_VARIABLE

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
