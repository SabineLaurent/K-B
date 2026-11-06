"""schema_postgresql.sql refuses what schema.sql refuses, and accepts what it accepts: the rows of
test_schema.py written on PostgreSQL (conventions.md, rule 4); and kb create-db on PostgreSQL."""

import re

import psycopg
import pytest
from test_schema import (
    MAX_INT64,
    REFUSED_VALUES,
    VALID_ROW_BY_TABLE,
    fill_database,
    insert_row,
    list_maximums_of_the_items,
    validate_trend_row,
)

from k_b import cli
from k_b.commands.exit_codes import ExitCode
from k_b.database import creation
from k_b.database.creation import DATABASE_SCRIPTS, create_database
from k_b.database.engine import connect_database
from k_b.database.location import DATABASE_URL_VARIABLE
from k_b.items import (
    HIGHLIGHT_MAX_LENGTH_BY_FIELD,
    MAX_COUNT_BY_KIND,
    MAX_LENGTH_BY_KIND,
    TAG_MAX_LENGTH,
    TREND_REPOSITORY_NAME_MAX_LENGTH,
)

pytestmark = pytest.mark.postgresql

# The tables whose rows test_schema.py writes with their id: the identity of each then starts
# after the largest one, as SQLite does.
TABLES_WITH_GIVEN_IDS = ("raw_data", "item", "tracked_repository")


@pytest.fixture(scope="module")
def schema_base(make_postgresql_base):
    """One base for the tests of the module, created by create_database."""
    location = make_postgresql_base()
    create_database(location)
    return location


@pytest.fixture
def filled_database(schema_base):
    """The base with the rows a valid row of each table points to, in a transaction the test
    leaves undone."""
    connection = connect_database(schema_base)
    fill_database(connection)
    for table in TABLES_WITH_GIVEN_IDS:
        # Names of the schema only: nothing from outside enters the statement.
        connection.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), max(id))"  # noqa: S608
            f" FROM {table}"
        )
    yield connection
    connection.rollback()
    connection.close()


@pytest.mark.parametrize("table", VALID_ROW_BY_TABLE)
def test_the_valid_row_of_each_table_is_accepted(filled_database, table):
    insert_row(filled_database, table)


@pytest.mark.parametrize("table, check, changes", REFUSED_VALUES)
def test_a_value_a_check_of_schema_sql_forbids_is_refused(
    filled_database, table, check, changes
):
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_row(filled_database, table, **changes)


@pytest.mark.parametrize(
    "field, value",
    [
        ("repository_id", 1),
        ("repository_id", MAX_INT64),
        ("repository_name", "morluto/" + "x" * 247),
        ("stars_gained", 0),
        ("stars_gained", MAX_INT64),
        ("forks_gained", 0),
        ("forks_gained", MAX_INT64),
    ],
)
def test_a_value_at_a_bound_of_the_trend_row_is_accepted_by_the_base(
    filled_database, field, value
):
    row = validate_trend_row(**{field: value})

    insert_row(filled_database, "trend", **{field: getattr(row, field)})


def test_a_tracked_repository_name_is_unique_whatever_its_ascii_case(filled_database):
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_row(
            filled_database,
            "tracked_repository",
            repository_name="Anthropics/Claude-Code",
        )


def read_postgresql_table_definitions():
    """The definition of each table of schema_postgresql.sql, without its comments."""
    schema = DATABASE_SCRIPTS.joinpath("schema_postgresql.sql").read_text()
    statements = "\n".join(line.split("--")[0] for line in schema.splitlines())
    return dict(re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", statements, re.DOTALL))


def read_maximums_of_the_postgresql_schema(check_pattern):
    return {
        (table, column): int(maximum)
        for table, definition in read_postgresql_table_definitions().items()
        for column, maximum in re.findall(check_pattern, definition)
    }


def test_each_maximum_length_of_the_items_is_the_check_of_its_postgresql_column():
    assert read_maximums_of_the_postgresql_schema(
        r"\blength\((\w+)\) <= (\d+)"
    ) == list_maximums_of_the_items(MAX_LENGTH_BY_KIND) | {
        ("trend", "repository_name"): TREND_REPOSITORY_NAME_MAX_LENGTH
    } | {
        ("highlight", field): maximum
        for field, maximum in HIGHLIGHT_MAX_LENGTH_BY_FIELD.items()
    } | {("tag", "name"): TAG_MAX_LENGTH}


def test_each_maximum_count_of_the_items_is_the_check_of_its_postgresql_column():
    assert read_maximums_of_the_postgresql_schema(
        r"json_array_length\((\w+)::json\) <= (\d+)"
    ) == list_maximums_of_the_items(MAX_COUNT_BY_KIND)


def run_create_db(monkeypatch, tmp_path, location):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, location.value)
    return cli.main(["create-db"])


def count_tables(location):
    connection = psycopg.connect(location.value)
    try:
        (count,) = connection.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
        ).fetchone()
        return count
    finally:
        connection.close()


def test_kb_create_db_creates_the_tables_and_the_sources_of_a_postgresql_base(
    monkeypatch, tmp_path, capsys, postgresql_base
):
    assert run_create_db(monkeypatch, tmp_path, postgresql_base) == ExitCode.SUCCEEDED

    connection = connect_database(postgresql_base)
    try:
        (source_count,) = connection.execute("SELECT count(*) FROM source").fetchone()
    finally:
        connection.close()
    assert source_count == 7
    assert count_tables(postgresql_base) == 15
    assert (
        capsys.readouterr().out
        == f"database created: PostgreSQL base {postgresql_base.value.rsplit('/', 1)[1]}\n"
    )
    # kb create-db writes no SQLite file beside it.
    assert not (tmp_path / "k-b.sqlite").exists()


def test_kb_create_db_refuses_a_postgresql_base_that_has_its_tables(
    monkeypatch, tmp_path, capsys, postgresql_base
):
    run_create_db(monkeypatch, tmp_path, postgresql_base)

    assert run_create_db(monkeypatch, tmp_path, postgresql_base) == ExitCode.NOT_STARTED
    assert "already has its tables" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("encoding", "collation", "refusal"),
    [
        ("SQL_ASCII", "C", "encoding SQL_ASCII"),
        ("UTF8", "en_US.UTF-8", "collation en_US.UTF-8"),
    ],
)
def test_kb_create_db_refuses_a_postgresql_base_out_of_utf8_or_of_the_collation_c(
    monkeypatch, tmp_path, capsys, make_postgresql_base, encoding, collation, refusal
):
    location = make_postgresql_base(encoding=encoding, collation=collation)

    assert run_create_db(monkeypatch, tmp_path, location) == ExitCode.NOT_STARTED
    assert refusal in capsys.readouterr().err
    assert count_tables(location) == 0


def test_a_failed_creation_leaves_no_table_in_the_postgresql_base(
    monkeypatch, tmp_path, postgresql_base
):
    class ScriptsWithAFailingSeed:
        def joinpath(self, name):
            return (
                FailingSeed()
                if name == "seed_sources.sql"
                else DATABASE_SCRIPTS.joinpath(name)
            )

    class FailingSeed:
        def read_text(self):
            return "INSERT INTO no_such_table VALUES (1);"

    monkeypatch.setattr(creation, "DATABASE_SCRIPTS", ScriptsWithAFailingSeed())

    assert run_create_db(monkeypatch, tmp_path, postgresql_base) == ExitCode.FAILED
    assert count_tables(postgresql_base) == 0
