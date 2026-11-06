"""The connections the data API reads PostgreSQL with: read only, in REPEATABLE READ, stopped past
their deadline, given back to the pool without transaction, and never a part of the URL or a text
of libpq in what kb writes."""

import logging
import threading
from pathlib import Path

import psycopg
import pytest

from k_b.database import reading
from k_b.database.creation import create_database
from k_b.database.engine import connect_database, connect_reader, open_readers
from k_b.database.errors import is_query_timeout
from k_b.database.location import PostgresUrl, UnreadableDatabaseUrlError
from k_b.database.reading import read_item_detail, read_items

ITEMS_DATABASE_SCRIPT = Path(__file__).parents[1] / "fixtures" / "items_database.sql"
PASSWORD = "S3cret-of-the-test"  # noqa: S105 — a marker the test looks for, no secret
# libpq stops at the [ of an IPv6 host never closed, and its error quotes the whole URL.
MALFORMED_URL = PostgresUrl(f"postgresql://kb:{PASSWORD}@[::1/kb")
TIMEOUT_SECONDS = 0.1

on_postgresql = pytest.mark.postgresql


@pytest.mark.parametrize("timeout_seconds", [0, 0.0004, -1])
def test_a_deadline_below_one_millisecond_is_refused_as_statement_timeout_0_disables_it(
    timeout_seconds,
):
    with (
        pytest.raises(ValueError, match="below 1 ms"),
        open_readers(PostgresUrl("postgresql://kb@127.0.0.1:1/kb"), timeout_seconds),
    ):
        pass


def test_a_url_libpq_cannot_read_is_refused_before_the_pool_without_its_text():
    with (
        pytest.raises(UnreadableDatabaseUrlError) as refusal,
        open_readers(MALFORMED_URL, TIMEOUT_SECONDS),
    ):
        pass

    assert str(refusal.value) == "KB_DATABASE_URL is not a URL libpq reads"
    assert refusal.value.__cause__ is None
    assert refusal.value.__suppress_context__


@pytest.fixture
def readers(items_postgresql_base):
    """A pool of the test, its deadline short."""
    with open_readers(items_postgresql_base, TIMEOUT_SECONDS) as readers:
        yield readers


def read_setting(connection, name):
    return connection.execute("SELECT current_setting(?)", (name,)).fetchone()[0]


@on_postgresql
def test_a_connection_of_the_pool_reads_in_repeatable_read_read_only_with_its_deadline(
    readers,
):
    with connect_reader(readers, TIMEOUT_SECONDS) as connection:
        assert read_setting(connection, "transaction_isolation") == "repeatable read"
        assert read_setting(connection, "transaction_read_only") == "on"
        assert read_setting(connection, "statement_timeout") == "100ms"


@on_postgresql
def test_a_write_through_a_connection_of_the_pool_is_refused(readers):
    with (
        pytest.raises(psycopg.errors.ReadOnlySqlTransaction),
        connect_reader(readers, TIMEOUT_SECONDS) as connection,
    ):
        connection.execute("DELETE FROM trend")


def hold_the_table(location, table):
    """A connection that holds the table locked until it is closed: a reading of it waits."""
    holder = psycopg.connect(location.value)
    # Names of the test only: nothing from outside enters the statement.
    holder.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
    return holder


@on_postgresql
def test_a_reading_past_its_deadline_is_stopped_and_its_connection_given_back_idle(
    readers, items_postgresql_base, caplog
):
    holder = hold_the_table(items_postgresql_base, "item")
    try:
        with (
            caplog.at_level(logging.INFO, logger="psycopg"),
            pytest.raises(psycopg.errors.QueryCanceled) as stopped,
            connect_reader(readers, TIMEOUT_SECONDS) as connection,
        ):
            read_items(connection, limit=1)
    finally:
        holder.close()

    assert is_query_timeout(stopped.value)
    with readers.connection() as connection:
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    assert not [
        record for record in caplog.records if "returned connection" in record.message
    ]


@on_postgresql
def test_a_connection_is_given_back_to_the_pool_without_transaction(readers, caplog):
    with (
        caplog.at_level(logging.INFO, logger="psycopg"),
        connect_reader(readers, TIMEOUT_SECONDS) as connection,
    ):
        read_items(connection, limit=1)
        assert connection.in_transaction

    # The pool rolls back and logs a connection given back in a transaction: none here.
    assert not [
        record for record in caplog.records if "returned connection" in record.message
    ]
    with readers.connection() as connection:
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def end_the_session_of(location, connection):
    """The server ends the session of the connection, as a restart or a cut of the network would;
    the connection does not know it until its next statement."""
    process_id = connection.execute("SELECT pg_backend_pid()").fetchone()[0]
    with psycopg.connect(location.value, autocommit=True) as administrator:
        # Waits for the end of the session, 5 s at most: true once it has ended.
        [ended] = administrator.execute(
            "SELECT pg_terminate_backend(%s, 5000)", (process_id,)
        ).fetchone()
    assert ended is True


class RequestFailedError(Exception):
    """An error a request raises after its connection was lost."""


LOST_SESSION_LINE = "reader_session_lost: AdminShutdown"


def lines_of_k_b(caplog):
    return [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("k_b")
    ]


@on_postgresql
def test_a_request_that_read_is_served_when_its_connection_is_lost_before_given_back(
    readers, items_postgresql_base, caplog
):
    """The loss is logged once, by the type of the error: its message may name the server."""
    with (
        caplog.at_level(logging.INFO),
        connect_reader(readers, TIMEOUT_SECONDS) as connection,
    ):
        page = read_items(connection, limit=1)
        end_the_session_of(items_postgresql_base, connection)

    assert len(page.items) == 1
    assert lines_of_k_b(caplog) == [LOST_SESSION_LINE]
    # The pool lends another connection.
    with connect_reader(readers, TIMEOUT_SECONDS) as connection:
        assert len(read_items(connection, limit=1).items) == 1


@on_postgresql
def test_the_error_of_a_request_passes_when_its_connection_is_lost_before_given_back(
    readers, items_postgresql_base
):
    """A rollback that fails on the lost connection must not replace the error: a query_timeout
    would become a database_error."""
    with (
        pytest.raises(RequestFailedError),
        connect_reader(readers, TIMEOUT_SECONDS) as connection,
    ):
        read_items(connection, limit=1)
        end_the_session_of(items_postgresql_base, connection)
        raise RequestFailedError


def ending_the_session_after_each_detail(monkeypatch, location, error=None):
    """Each reader of a detail of a kind ends the session of its connection once it has read, as
    a restart of the server between the last reading and the end of the detail would; then
    raises the error given, if any."""

    def end_after(read_detail):
        def read_then_end(connection, item_id):
            detail = read_detail(connection, item_id)
            end_the_session_of(location, connection)
            if error is not None:
                raise error
            return detail

        return read_then_end

    for kind, read_detail in list(reading.READ_DETAILS_BY_KIND.items()):
        monkeypatch.setitem(reading.READ_DETAILS_BY_KIND, kind, end_after(read_detail))


@on_postgresql
def test_a_detail_that_read_is_served_when_its_connection_is_lost_before_its_end(
    readers, items_postgresql_base, monkeypatch, caplog
):
    ending_the_session_after_each_detail(monkeypatch, items_postgresql_base)

    with (
        caplog.at_level(logging.INFO),
        connect_reader(readers, TIMEOUT_SECONDS) as connection,
    ):
        detail = read_item_detail(connection, 1)

    assert detail is not None
    assert detail.listed.id == 1
    assert lines_of_k_b(caplog) == [LOST_SESSION_LINE]


@on_postgresql
def test_the_error_of_a_detail_passes_when_its_connection_is_lost_before_its_end(
    readers, items_postgresql_base, monkeypatch
):
    ending_the_session_after_each_detail(
        monkeypatch, items_postgresql_base, RequestFailedError()
    )

    with (
        pytest.raises(RequestFailedError),
        connect_reader(readers, TIMEOUT_SECONDS) as connection,
    ):
        read_item_detail(connection, 1)


@on_postgresql
def test_the_detail_reads_one_state_of_the_base_while_a_writer_commits(
    postgresql_base, monkeypatch
):
    """The highlights are read by the third statement of the detail: a writer that commits
    between the first and the third does not change what the detail reads."""
    create_database(postgresql_base)
    writer = connect_database(postgresql_base)
    writer.executescript(ITEMS_DATABASE_SCRIPT.read_text())
    writer.commit()
    read_highlights = reading.read_highlights

    def withdraw_every_highlight_first(connection, item_id):
        writer.execute("UPDATE highlight SET withdrawn_at = '2026-11-06T00:00:00Z'")
        writer.commit()
        return read_highlights(connection, item_id)

    monkeypatch.setattr(reading, "read_highlights", withdraw_every_highlight_first)
    try:
        with (
            open_readers(postgresql_base, TIMEOUT_SECONDS) as readers,
            connect_reader(readers, TIMEOUT_SECONDS) as connection,
        ):
            detail = read_item_detail(connection, 14)
    finally:
        writer.close()

    assert detail is not None
    assert [highlight.withdrawn_at for highlight in detail.details.highlights] == [
        None,
        None,
        "2026-10-06T09:30:00Z",
    ]


@on_postgresql
def test_the_pool_lends_no_connection_beyond_its_wait(
    items_postgresql_base, monkeypatch
):
    """Every connection lent, the next request waits for its bound, then fails."""
    from k_b.database import postgresql

    monkeypatch.setattr(postgresql, "READING_POOL_MAX_SIZE", 1)
    monkeypatch.setattr(postgresql, "READING_POOL_WAIT_SECONDS", 0.2)
    with open_readers(items_postgresql_base, TIMEOUT_SECONDS) as readers:
        lent = threading.Event()
        release = threading.Event()

        def hold_a_connection():
            with connect_reader(readers, TIMEOUT_SECONDS):
                lent.set()
                release.wait(5)

        thread = threading.Thread(target=hold_a_connection)
        thread.start()
        try:
            assert lent.wait(5)
            with (
                pytest.raises(psycopg.OperationalError) as refused,
                connect_reader(readers, TIMEOUT_SECONDS),
            ):
                pass
        finally:
            release.set()
            thread.join(5)

    assert type(refused.value).__name__ == "PoolTimeout"
