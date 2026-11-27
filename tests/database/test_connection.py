"""The read-only connection the readers of the base use, and the connection of the commands to a base
kb create-db has created."""

import sqlite3

import pytest

from k_b.database import postgresql
from k_b.database.creation import create_database
from k_b.database.engine import connect_database_read_only, connect_existing_database
from k_b.database.location import MissingDatabaseError, PostgresUrl

INSERT_SOURCE = (
    "INSERT INTO source (source_code, label, source_type, acquisition_mode)"
    " VALUES ('test', 'Test', 'file', 'watch')"
)


def test_a_base_in_a_folder_named_with_characters_a_uri_escapes_is_read(items_database):
    folder_name = items_database.parent.name
    assert all(character in folder_name for character in " #?%")

    connection = connect_database_read_only(items_database)
    try:
        assert connection.execute("SELECT count(*) FROM item").fetchone() == (18,)
    finally:
        connection.close()


def test_a_read_only_connection_cannot_write(tmp_path):
    database_path = tmp_path / "k-b.sqlite"
    create_database(database_path)
    connection = connect_database_read_only(database_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute(INSERT_SOURCE)
    finally:
        connection.close()


def test_a_missing_database_is_refused_and_not_created(tmp_path):
    with pytest.raises(MissingDatabaseError):
        connect_database_read_only(tmp_path / "k-b.sqlite")

    assert list(tmp_path.iterdir()) == []


def test_a_relative_database_path_is_read(monkeypatch, tmp_path):
    create_database(tmp_path / "k-b.sqlite")
    monkeypatch.chdir(tmp_path.parent)
    relative_path = tmp_path.relative_to(tmp_path.parent) / "k-b.sqlite"

    connection = connect_database_read_only(relative_path)
    try:
        assert connection.execute("SELECT count(*) FROM source").fetchone() == (7,)
    finally:
        connection.close()


class BaseWithoutTables:
    """A connection to a PostgreSQL base whose catalog has no table source."""

    def __init__(self):
        self.closed = False

    def execute(self, sql, parameters=()):
        return self

    def fetchone(self):
        return (False,)

    def close(self):
        self.closed = True


def test_a_postgresql_base_without_its_tables_is_refused_and_its_connection_closed(
    monkeypatch,
):
    """The base of kb import and kb purge: the server answers, but kb create-db has not run."""
    connection = BaseWithoutTables()
    monkeypatch.setattr(postgresql, "connect_postgresql", lambda location: connection)

    with pytest.raises(MissingDatabaseError, match="has no tables of K-B"):
        connect_existing_database(PostgresUrl("postgresql://kb@127.0.0.1/kb"))

    assert connection.closed
