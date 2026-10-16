"""The savepoint each item is written in (conventions.md, rule 1): what it keeps, what it
undoes, and how a refusal of the base is described without the value refused."""

import sqlite3

import pytest

from k_b.database.connection import connect_database
from k_b.database.savepoint import (
    ENTRY_REFUSAL_ERRORS,
    NoTransactionError,
    describe_refusal,
    write_in_savepoint,
)


@pytest.fixture
def connection(tmp_path):
    connection = connect_database(tmp_path / "test.sqlite")
    connection.execute(
        "CREATE TABLE note (text TEXT NOT NULL CHECK (length(text) > 0))"
    )
    # The import opens its transaction with its first write, before any savepoint.
    connection.execute("INSERT INTO note VALUES ('before')")
    yield connection
    connection.close()


def read_notes(connection):
    return [
        text for (text,) in connection.execute("SELECT text FROM note ORDER BY rowid")
    ]


def test_what_is_written_in_a_savepoint_is_kept(connection):
    with write_in_savepoint(connection):
        connection.execute("INSERT INTO note VALUES ('kept')")

    assert read_notes(connection) == ["before", "kept"]
    assert connection.in_transaction


def test_an_error_in_a_savepoint_undoes_it_alone_and_is_raised_again(connection):
    with pytest.raises(sqlite3.IntegrityError), write_in_savepoint(connection):
        connection.execute("INSERT INTO note VALUES ('undone')")
        connection.execute("INSERT INTO note VALUES ('')")

    assert read_notes(connection) == ["before"]
    # The savepoint is released: the next one starts from a stack without it.
    with write_in_savepoint(connection):
        connection.execute("INSERT INTO note VALUES ('after')")
    # No release committed anything: the rollback of the transaction undoes it all.
    connection.rollback()
    assert read_notes(connection) == []


def test_an_error_after_the_base_undid_the_transaction_is_raised_unchanged(connection):
    # SQLite undoes the whole transaction on a full disk, for instance: no savepoint is left
    # to roll back to, and the error of the base is the one raised.
    with (
        pytest.raises(sqlite3.OperationalError, match="database or disk is full"),
        write_in_savepoint(connection),
    ):
        connection.rollback()
        raise sqlite3.OperationalError("database or disk is full")


def test_a_savepoint_outside_a_transaction_is_refused(tmp_path):
    connection = connect_database(tmp_path / "test.sqlite")
    try:
        # Outside a transaction, its release would commit what it wrote.
        with pytest.raises(NoTransactionError), write_in_savepoint(connection):
            pass
        assert not connection.in_transaction
    finally:
        connection.close()


def test_only_the_errors_due_to_an_entry_are_those_of_a_refusal():
    assert ENTRY_REFUSAL_ERRORS == (
        sqlite3.IntegrityError,
        OverflowError,
        UnicodeEncodeError,
    )


def test_a_constraint_refused_is_named_with_its_state_on_one_line(connection):
    with pytest.raises(sqlite3.IntegrityError) as refusal:
        connection.execute("INSERT INTO note VALUES ('')")

    assert (
        describe_refusal(refusal.value)
        == "SQLITE_CONSTRAINT_CHECK: CHECK constraint failed: length(text) > 0"
    )


def test_a_check_written_on_several_lines_is_described_on_one(tmp_path):
    connection = connect_database(tmp_path / "test.sqlite")
    try:
        connection.execute("CREATE TABLE note (rank INTEGER CHECK (\n    rank > 0\n))")
        with pytest.raises(sqlite3.IntegrityError) as refusal:
            connection.execute("INSERT INTO note VALUES (0)")
    finally:
        connection.close()

    assert describe_refusal(refusal.value) == (
        "SQLITE_CONSTRAINT_CHECK: CHECK constraint failed: rank > 0"
    )


def test_an_integer_beyond_64_bits_is_described_without_its_value(connection):
    with pytest.raises(OverflowError) as refusal:
        connection.execute("SELECT ?", (2**63,))

    description = describe_refusal(refusal.value)

    assert description.startswith("OverflowError: ")
    assert str(2**63) not in description


def test_a_lone_surrogate_is_described_by_its_position_without_the_character(
    connection,
):
    with pytest.raises(UnicodeEncodeError) as refusal:
        connection.execute("SELECT ?", ("ab\ud800",))

    description = describe_refusal(refusal.value)

    assert description == "UnicodeEncodeError: surrogates not allowed at position 2"
    assert "ud800" not in description
