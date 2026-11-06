"""The roles of the base online (infra/postgresql/grant-roles.sql, then kb migrate-database): the
data API reads and writes nothing, the daily routine writes the data, on the test server as on
Azure."""

import psycopg
import pytest
from database.online_roles import (
    DAILY_ROUTINE_ROLE,
    DATA_API_ROLE,
    GRANT_ROLES_SCRIPT,
    MIGRATE_DATABASE_ROLE,
    as_role,
)
from psycopg import errors

from k_b.database.creation import migrate_database

pytestmark = pytest.mark.postgresql

# A row of source that no seed holds.
INSERT_SOURCE = (
    "INSERT INTO source (source_code, label, source_type, acquisition_mode)"
    " VALUES ('test_source', 'Source of the test', 'file', 'watch')"
)


@pytest.fixture
def migrated_base(administered_base):
    """The base created by kb migrate-database under the role of its identity, its owner."""
    migrate_database(as_role(administered_base, MIGRATE_DATABASE_ROLE))
    return administered_base


@pytest.fixture
def daily_routine_member(identity_roles, postgresql_server_url):
    """The daily routine a member of kb_writer, as #330 will make it on Azure."""
    with psycopg.connect(postgresql_server_url, autocommit=True) as server:
        server.execute(f'GRANT kb_writer TO "{DAILY_ROUTINE_ROLE}"')


def connect_as(location, role):
    """A plain connection under role: not one of the pool, whose READ ONLY would refuse the write
    by itself (25006), whatever the rights of the role."""
    return psycopg.connect(as_role(location, role).value, autocommit=True)


def test_the_data_api_reads_the_tables(migrated_base):
    with connect_as(migrated_base, DATA_API_ROLE) as reader:
        (count,) = reader.execute("SELECT count(*) FROM source").fetchone()

    assert count > 0


@pytest.mark.parametrize(
    "statement",
    [
        INSERT_SOURCE,
        "UPDATE source SET label = 'changed'",
        "DELETE FROM source",
        "CREATE TABLE written_by_the_data_api (id integer)",
        "CREATE TEMP TABLE written_by_the_data_api (id integer)",
    ],
    ids=["insert", "update", "delete", "create table", "create temp table"],
)
def test_the_data_api_writes_nothing_in_the_base(migrated_base, statement):
    with (
        connect_as(migrated_base, DATA_API_ROLE) as reader,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        reader.execute(statement)


def test_the_daily_routine_writes_the_data_of_a_table_with_an_identity_column(
    migrated_base, daily_routine_member
):
    with connect_as(migrated_base, DAILY_ROUTINE_ROLE) as writer:
        (source_id,) = writer.execute(f"{INSERT_SOURCE} RETURNING id").fetchone()
        writer.execute(
            "UPDATE source SET label = 'changed' WHERE id = %s", (source_id,)
        )
        writer.execute("DELETE FROM source WHERE id = %s", (source_id,))


def test_the_daily_routine_changes_no_table(migrated_base, daily_routine_member):
    with (
        connect_as(migrated_base, DAILY_ROUTINE_ROLE) as writer,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        writer.execute("DROP TABLE source")


def test_the_tables_belong_to_the_identity_of_kb_migrate_database(migrated_base):
    with psycopg.connect(migrated_base.value) as administrator:
        owners = administrator.execute(
            "SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()

    assert owners == [(MIGRATE_DATABASE_ROLE,)]


def test_grant_roles_sql_runs_again_without_error(migrated_base):
    with psycopg.connect(migrated_base.value, autocommit=True) as administrator:
        administrator.execute(GRANT_ROLES_SCRIPT.read_text())
