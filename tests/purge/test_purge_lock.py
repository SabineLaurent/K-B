"""On PostgreSQL, a purge that writes in the base waits for the lock of the writers, as an import
does: it never deletes while an import writes; and a connection psycopg closed on a signal leaves
the signal its exit code."""

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from k_b.database import postgresql
from k_b.database.creation import create_database
from k_b.database.engine import connect_database, lock_for_writing
from k_b.etl.raw_store import RawStore
from k_b.purge import base as base_purge
from k_b.purge import registry as registry_purge
from k_b.purge.base import purge_expired_rows
from k_b.purge.registry import purge_registry

ITEMS_DATABASE_SCRIPT = Path(__file__).parents[1] / "fixtures" / "items_database.sql"
pytestmark = pytest.mark.postgresql

# Four years after the collections of the test base: the purge would delete its watch.
LATER = datetime(2030, 10, 8, 12, tzinfo=UTC)
STATE_CATALOG_SOURCE_CODES = frozenset({"cisa_kev", "zotero"})


@pytest.fixture
def location(postgresql_base):
    """The test base of the readers on a new PostgreSQL base, which the purges may change."""
    create_database(postgresql_base)
    connection = connect_database(postgresql_base)
    try:
        connection.executescript(ITEMS_DATABASE_SCRIPT.read_text())
        connection.commit()
    finally:
        connection.close()
    return postgresql_base


def count_items(location):
    with psycopg.connect(location.value) as connection:
        return connection.execute("SELECT count(*) FROM item").fetchone()[0]


PURGES = {
    "base": lambda location, data_dir: purge_expired_rows(
        location, LATER, STATE_CATALOG_SOURCE_CODES, []
    ),
    "registry": lambda location, data_dir: purge_registry(
        location, RawStore(data_dir), STATE_CATALOG_SOURCE_CODES
    ),
}


@pytest.mark.parametrize("purge", PURGES.values(), ids=PURGES.keys())
def test_a_purge_waits_for_the_lock_of_the_writers_then_fails_without_deleting(
    location, tmp_path, monkeypatch, purge
):
    monkeypatch.setattr(postgresql, "DATABASE_LOCK_TIMEOUT_SECONDS", 0.2)
    items_before = count_items(location)
    holder = connect_database(location)
    try:
        lock_for_writing(holder)

        with pytest.raises(psycopg.errors.LockNotAvailable):
            purge(location, tmp_path)
    finally:
        holder.close()

    assert count_items(location) == items_before


def test_once_the_lock_is_free_the_purge_of_the_base_deletes(location, tmp_path):
    """The lock does not stop the purge itself: the watch past its duration goes."""
    items_before = count_items(location)

    PURGES["base"](location, tmp_path)

    assert count_items(location) < items_before


@pytest.mark.parametrize(
    ("module", "step"),
    [(base_purge, "delete_expired_rows"), (registry_purge, "delete_rows_without_file")],
    ids=["base", "registry"],
)
def test_a_connection_closed_during_a_purge_leaves_the_signal_its_exit_code(
    location, tmp_path, monkeypatch, module, step
):
    """On a signal, psycopg may close the connection: a rollback would then raise in place of
    the signal, and kb would exit in 1, not in 143."""

    def close_then_stop(connection, *arguments):
        connection.close()
        raise SystemExit(143)

    monkeypatch.setattr(module, step, close_then_stop)

    with pytest.raises(SystemExit) as stopped:
        PURGES["base" if module is base_purge else "registry"](location, tmp_path)

    assert stopped.value.code == 143
