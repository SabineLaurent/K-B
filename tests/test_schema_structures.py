"""schema_postgresql.sql has the structure of schema.sql, which stays the reference: for each table,
the same columns in the same order, the same NOT NULL, keys, unique constraints, foreign keys with
their ON DELETE, and indexes; the differences wanted are listed (left to #418 by #417)."""

import sqlite3

import psycopg
import pytest

from k_b.database.creation import DATABASE_SCRIPTS, create_database

pytestmark = pytest.mark.postgresql

# What PostgreSQL holds otherwise, on purpose: the URL of a clip is unique by its md5, as a B-tree
# entry cannot hold a URL of more than about 2,700 bytes (docs/stockage.md).
WANTED_DIFFERENCES = {
    ("clip", "unique"): {"sqlite": [("url",)], "postgresql": [("md5(url)",)]},
}
# The ON DELETE of each engine, as each names it.
ON_DELETE_BY_CODE = {"a": "NO ACTION", "c": "CASCADE", "r": "RESTRICT", "n": "SET NULL"}


def read_sqlite_structure():
    """The structure of each table of schema.sql, read by the PRAGMA of SQLite."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(DATABASE_SCRIPTS.joinpath("schema.sql").read_text())
        tables = [
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
            )
        ]
        return {table: read_sqlite_table(connection, table) for table in tables}
    finally:
        connection.close()


def read_sqlite_table(connection, table):
    # Names of schema.sql only: nothing from outside enters the statements.
    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    primary_key = tuple(
        name for _, name, _, _, _, rank in sorted(columns, key=lambda c: c[5]) if rank
    )
    indexes = connection.execute(f"PRAGMA index_list({table})").fetchall()
    foreign_keys = {}
    for key_id, _, target, source, target_column, _, on_delete, _ in connection.execute(
        f"PRAGMA foreign_key_list({table})"
    ):
        sources, target_table, targets, action = foreign_keys.get(
            key_id, ((), target, (), on_delete)
        )
        foreign_keys[key_id] = (
            (*sources, source),
            target_table,
            (*targets, target_column),
            action,
        )

    def index_columns(name):
        return tuple(row[2] for row in connection.execute(f"PRAGMA index_info({name})"))

    return {
        # A column of the primary key cannot be NULL, in SQLite as in PostgreSQL.
        "columns": [
            (name, bool(not_null) or name in primary_key)
            for _, name, _, not_null, _, _ in columns
        ],
        "primary_key": primary_key,
        "unique": sorted(
            index_columns(name)
            for _, name, unique, origin, _ in indexes
            if unique and origin != "pk"
        ),
        "foreign_keys": sorted(foreign_keys.values()),
        "indexes": sorted(
            index_columns(name) for _, name, unique, _, _ in indexes if not unique
        ),
    }


POSTGRESQL_COLUMNS = """
SELECT column_name, is_nullable = 'NO' FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position
"""
# The columns of each constraint, in the order of its key.
POSTGRESQL_CONSTRAINTS = """
SELECT constraint_row.contype,
    ARRAY(SELECT attribute.attname FROM unnest(constraint_row.conkey) WITH ORDINALITY AS key(number, position)
        JOIN pg_attribute AS attribute ON attribute.attrelid = constraint_row.conrelid
            AND attribute.attnum = key.number
        ORDER BY key.position),
    target.relname,
    ARRAY(SELECT attribute.attname FROM unnest(constraint_row.confkey) WITH ORDINALITY AS key(number, position)
        JOIN pg_attribute AS attribute ON attribute.attrelid = constraint_row.confrelid
            AND attribute.attnum = key.number
        ORDER BY key.position),
    constraint_row.confdeltype
FROM pg_constraint AS constraint_row
LEFT JOIN pg_class AS target ON target.oid = constraint_row.confrelid
WHERE constraint_row.conrelid = %s::regclass AND constraint_row.contype IN ('p', 'u', 'f')
"""
# The indexes that back no constraint: each column, or the expression it indexes.
POSTGRESQL_INDEXES = """
SELECT index_row.indisunique,
    ARRAY(SELECT pg_get_indexdef(index_row.indexrelid, position, true)
        FROM generate_series(1, index_row.indnkeyatts) AS position)
FROM pg_index AS index_row
WHERE index_row.indrelid = %s::regclass
    AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conindid = index_row.indexrelid)
"""


def read_postgresql_structure(location):
    """The structure of each table kb create-db wrote on PostgreSQL, read from its catalog."""
    with psycopg.connect(location.value) as connection:
        tables = [
            name
            for (name,) in connection.execute(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_schema = 'public' ORDER BY table_name"
            )
        ]
        return {table: read_postgresql_table(connection, table) for table in tables}


def read_postgresql_table(connection, table):
    constraints = connection.execute(POSTGRESQL_CONSTRAINTS, (table,)).fetchall()
    indexes = connection.execute(POSTGRESQL_INDEXES, (table,)).fetchall()
    [primary_key] = [tuple(columns) for kind, columns, *_ in constraints if kind == "p"]
    return {
        "columns": connection.execute(POSTGRESQL_COLUMNS, (table,)).fetchall(),
        "primary_key": primary_key,
        "unique": sorted(
            [tuple(columns) for kind, columns, *_ in constraints if kind == "u"]
            + [tuple(columns) for unique, columns in indexes if unique]
        ),
        "foreign_keys": sorted(
            (tuple(columns), target, tuple(targets), ON_DELETE_BY_CODE[on_delete])
            for kind, columns, target, targets, on_delete in constraints
            if kind == "f"
        ),
        "indexes": sorted(tuple(columns) for unique, columns in indexes if not unique),
    }


def remove_wanted_differences(structure, engine):
    """The structure with each difference wanted set apart, after checking it is there."""
    for (table, part), values in WANTED_DIFFERENCES.items():
        kept = structure[table][part]
        for value in values[engine]:
            assert value in kept, (table, part, value)
            kept.remove(value)
    return structure


def test_schema_postgresql_has_the_structure_of_schema_sql(postgresql_base):
    create_database(postgresql_base)

    on_sqlite = remove_wanted_differences(read_sqlite_structure(), "sqlite")
    on_postgresql = remove_wanted_differences(
        read_postgresql_structure(postgresql_base), "postgresql"
    )

    assert sorted(on_postgresql) == sorted(on_sqlite)
    for table in on_sqlite:
        assert on_postgresql[table] == on_sqlite[table], table
