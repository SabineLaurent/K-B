import sqlite3

import pytest

from k_b.database import connect_database, create_database


def test_a_new_database_has_the_sources_and_the_wal_mode(tmp_path):
    database_path = tmp_path / "k-b.sqlite"

    create_database(database_path)

    connection = sqlite3.connect(database_path)
    assert connection.execute("SELECT count(*) FROM source").fetchone() == (7,)
    assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    connection.close()


def test_an_existing_database_is_refused_and_left_untouched(tmp_path):
    database_path = tmp_path / "k-b.sqlite"
    database_path.write_bytes(b"not a database")

    with pytest.raises(FileExistsError, match="k-b.sqlite"):
        create_database(database_path)

    assert database_path.read_bytes() == b"not a database"


def test_a_connection_checks_the_foreign_keys(tmp_path):
    database_path = tmp_path / "k-b.sqlite"
    create_database(database_path)

    connection = connect_database(database_path)

    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO item (source_code, source_item_id, title, url, collection_id)"
            " VALUES ('rss', 'x', 'A title', 'https://example.com/', 1)"
        )
    connection.close()
