"""kb migrate-database: the base created when it has no tables yet, left as it is when it has them,
so that the job caj-kb-migrate-database run at each delivery changes nothing the second time."""

import psycopg
import pytest
from azure.core.exceptions import ClientAuthenticationError
from database.online_roles import MIGRATE_DATABASE_ROLE, as_role
from jobs.storage_fakes import FORGED_LOG_LINE, TEST_CLIENT_ID

from k_b import cli
from k_b.commands.exit_codes import ExitCode
from k_b.database import entra
from k_b.database.location import (
    CLIENT_ID_VARIABLE,
    DATABASE_AUTH_VARIABLE,
    DATABASE_URL_VARIABLE,
)

# What the second run must leave as it found it: each table, its columns, its rights and its
# storage (a rewrite changes relfilenode), and each row of source with the transaction that wrote it.
SELECT_TABLES = """
SELECT c.relname, c.relowner::regrole::text, c.relacl::text, c.relfilenode::text
FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace ORDER BY c.relname
"""
SELECT_COLUMNS = """
SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
WHERE table_schema = 'public' ORDER BY table_name, column_name
"""
SELECT_SOURCES = "SELECT xmin::text, * FROM source ORDER BY id"


def read_what_a_migration_could_change(location):
    """The catalog of the base and its sources, read by the administrator."""
    with psycopg.connect(location.value) as administrator:
        return [
            administrator.execute(query).fetchall()
            for query in (SELECT_TABLES, SELECT_COLUMNS, SELECT_SOURCES)
        ]


def test_kb_migrate_database_creates_a_sqlite_base_then_leaves_it_as_it_is(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    database_path = tmp_path / "k-b.sqlite"

    assert cli.main(["migrate-database"]) == ExitCode.SUCCEEDED
    assert f"database created: {database_path}" in capsys.readouterr().out
    database_content = database_path.read_bytes()

    assert cli.main(["migrate-database"]) == ExitCode.SUCCEEDED
    assert (
        f"database unchanged: {database_path} already exists" in capsys.readouterr().out
    )
    assert database_path.read_bytes() == database_content


@pytest.mark.postgresql
def test_kb_migrate_database_run_twice_creates_the_postgresql_base_then_changes_nothing(
    monkeypatch, tmp_path, capsys, administered_base
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        DATABASE_URL_VARIABLE, as_role(administered_base, MIGRATE_DATABASE_ROLE).value
    )

    assert cli.main(["migrate-database"]) == ExitCode.SUCCEEDED
    assert (
        "database created: the PostgreSQL base of KB_DATABASE_URL"
        in capsys.readouterr().out
    )
    before = read_what_a_migration_could_change(administered_base)

    assert cli.main(["migrate-database"]) == ExitCode.SUCCEEDED
    assert (
        "database unchanged: the PostgreSQL base of KB_DATABASE_URL already has its tables"
        in capsys.readouterr().out
    )
    assert read_what_a_migration_could_change(administered_base) == before


@pytest.mark.postgresql
def test_kb_migrate_database_refuses_a_base_out_of_the_collation_c_before_writing(
    monkeypatch, tmp_path, capsys, make_postgresql_base
):
    location = make_postgresql_base(collation="en_US.UTF-8")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, location.value)

    assert cli.main(["migrate-database"]) == ExitCode.NOT_STARTED
    assert "not in the collation C" in capsys.readouterr().err
    with psycopg.connect(location.value) as administrator:
        (has_tables,) = administrator.execute(
            "SELECT to_regclass('source') IS NOT NULL"
        ).fetchone()
    assert not has_tables


def test_an_identity_without_token_stops_kb_migrate_database_by_a_named_failure(
    monkeypatch, tmp_path, capsys
):
    class RefusingCredential:
        def get_token(self, *scopes, **kwargs):
            raise ClientAuthenticationError(f"refused\n{FORGED_LOG_LINE}")

    monkeypatch.setattr(
        entra, "build_database_credential", lambda client_id: RefusingCredential()
    )
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        DATABASE_URL_VARIABLE,
        "postgresql://id-kb-migrate-database@127.0.0.1:1/kb?sslmode=verify-full",
    )
    monkeypatch.setenv(DATABASE_AUTH_VARIABLE, "entra")
    monkeypatch.setenv(CLIENT_ID_VARIABLE, TEST_CLIENT_ID)

    assert cli.main(["migrate-database"]) == ExitCode.FAILED
    error_output = capsys.readouterr().err
    assert (
        "ERROR k_b.cli: the PostgreSQL base of KB_DATABASE_URL: DatabaseNoTokenError"
        in error_output
    )
    assert FORGED_LOG_LINE not in error_output
    assert "Traceback" not in error_output
