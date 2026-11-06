"""The connections the data API reads PostgreSQL with: read only, in REPEATABLE READ, stopped past
their deadline, given back to the pool without transaction, and never a part of the URL or a text
of libpq in what kb writes."""

import logging
import threading

import psycopg
import pytest
from conftest import ITEMS_DATABASE_SCRIPT

from k_b.database import reading
from k_b.database.creation import create_database
from k_b.database.engine import connect_database, connect_reader, open_readers
from k_b.database.errors import is_query_timeout
from k_b.database.location import PostgresUrl, UnreadableDatabaseUrlError
from k_b.database.reading import read_item_detail, read_items

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
    with pytest.raises(UnreadableDatabaseUrlError) as refusal:
        with open_readers(MALFORMED_URL, TIMEOUT_SECONDS):
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
    with caplog.at_level(logging.INFO, logger="psycopg"):
        with connect_reader(readers, TIMEOUT_SECONDS) as connection:
            read_items(connection, limit=1)
            assert connection.in_transaction

    # The pool rolls back and logs a connection given back in a transaction: none here.
    assert not [
        record for record in caplog.records if "returned connection" in record.message
    ]
    with readers.connection() as connection:
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


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

    monkeypatch.setattr(postgresql, "DATA_API_POOL_MAX_SIZE", 1)
    monkeypatch.setattr(postgresql, "DATA_API_POOL_WAIT_SECONDS", 0.2)
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
