"""Where the items database is: the SQLite file of the data directory, or the PostgreSQL base of
KB_DATABASE_URL, never quoted, and never with a variable libpq would read besides it."""

from pathlib import Path

import pytest
from psycopg import pq

from k_b.database.location import (
    CLIENT_ID_VARIABLE,
    DATABASE_AUTH_VARIABLE,
    DATABASE_URL_VARIABLE,
    LIBPQ_VARIABLES,
    PostgresUrl,
    describe_location,
    read_database_location_or_refusal,
)

DATA_DIR = Path("/data dir")
# A password the tests look for in what kb writes.
PASSWORD = "S3cret-of-the-test"  # noqa: S105 — a marker the test looks for, no secret
URL = f"postgresql://kb:{PASSWORD}@db.example:5432/kb_production?sslmode=verify-full"


def test_without_kb_database_url_the_base_is_the_sqlite_file_of_the_data_directory():
    assert read_database_location_or_refusal({}, DATA_DIR) == DATA_DIR / "k-b.sqlite"


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_a_postgresql_url_names_a_postgresql_base(scheme):
    url = URL.replace("postgresql", scheme, 1)

    assert read_database_location_or_refusal(
        {DATABASE_URL_VARIABLE: url}, DATA_DIR
    ) == PostgresUrl(url)


# Empty: a secret not given to the container must not make kb write into a SQLite file.
@pytest.mark.parametrize(
    "value",
    ["", f"sqlite:///{DATA_DIR}/k-b.sqlite", f"mysql://kb:{PASSWORD}@db/kb", URL[1:]],
    ids=["empty", "sqlite", "mysql", "no scheme"],
)
def test_a_value_that_is_not_a_postgresql_url_is_refused_without_being_quoted(value):
    refusal = read_database_location_or_refusal(
        {DATABASE_URL_VARIABLE: value}, DATA_DIR
    )

    assert refusal == (
        f"{DATABASE_URL_VARIABLE} is neither a postgresql:// nor a postgres:// URL"
    )


def test_a_variable_libpq_reads_is_refused_with_a_postgresql_base_by_its_name_only():
    refusal = read_database_location_or_refusal(
        {DATABASE_URL_VARIABLE: URL, "PGPASSWORD": PASSWORD, "PGHOST": "other.example"},
        DATA_DIR,
    )

    assert refusal == (
        "PGHOST, PGPASSWORD set: libpq reads these variables besides KB_DATABASE_URL"
    )


def test_a_variable_libpq_does_not_read_is_accepted_with_a_postgresql_base():
    # PGDATA, which Homebrew sets, is a variable of the server, not of libpq.
    assert read_database_location_or_refusal(
        {DATABASE_URL_VARIABLE: URL, "PGDATA": "/opt/homebrew/var/postgresql@18"},
        DATA_DIR,
    ) == PostgresUrl(URL)


def test_a_variable_libpq_reads_is_left_alone_with_the_sqlite_base():
    assert read_database_location_or_refusal({"PGHOST": "localhost"}, DATA_DIR) == (
        DATA_DIR / "k-b.sqlite"
    )


def test_the_variables_refused_cover_every_one_the_libpq_installed_reads():
    declared = {
        option.envvar.decode()
        for option in pq.Conninfo.get_defaults()
        if option.envvar is not None
    }

    assert declared <= LIBPQ_VARIABLES


def test_a_postgresql_url_is_never_shown():
    location = PostgresUrl(URL)

    assert PASSWORD not in repr(location)
    assert PASSWORD not in str(location)
    assert describe_location(location) == "the PostgreSQL base of KB_DATABASE_URL"


# A slash not encoded ends the netloc of urlsplit early, and a fullwidth slash or colon makes it
# raise an error that quotes the netloc: the password must not reach the description either way.
@pytest.mark.parametrize(
    "password",
    [
        f"Ab3/{PASSWORD}/Q=",
        f"Ab3{chr(0xFF0F)}{PASSWORD}",
        f"Ab3{chr(0xFF1A)}{PASSWORD}",
    ],
    ids=["slash", "fullwidth slash", "fullwidth colon"],
)
def test_a_postgresql_base_is_described_without_any_part_of_its_url(password):
    location = PostgresUrl(f"postgresql://kb:{password}@127.0.0.1:1/kb")

    assert describe_location(location) == "the PostgreSQL base of KB_DATABASE_URL"


def test_the_sqlite_file_is_described_by_its_path():
    assert describe_location(DATA_DIR / "k-b.sqlite") == "/data dir/k-b.sqlite"


# The client id of a user-assigned identity, as Azure gives it.
CLIENT_ID = "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"
ENTRA_URL = "postgresql://id-kb-data-api@pgsql-kb.example/kb?sslmode=verify-full"


def test_without_kb_database_auth_libpq_authenticates_as_the_url_says():
    location = read_database_location_or_refusal(
        {DATABASE_URL_VARIABLE: URL, CLIENT_ID_VARIABLE: CLIENT_ID}, DATA_DIR
    )

    assert location == PostgresUrl(URL)
    assert location.entra_client_id is None


def test_kb_database_auth_entra_names_the_identity_of_azure_client_id():
    location = read_database_location_or_refusal(
        {
            DATABASE_URL_VARIABLE: ENTRA_URL,
            DATABASE_AUTH_VARIABLE: "entra",
            CLIENT_ID_VARIABLE: CLIENT_ID,
        },
        DATA_DIR,
    )

    assert location == PostgresUrl(ENTRA_URL, entra_client_id=CLIENT_ID)


@pytest.mark.parametrize(
    ("settings", "refusal"),
    [
        (
            {DATABASE_AUTH_VARIABLE: "password"},
            "KB_DATABASE_AUTH is neither libpq nor entra",
        ),
        (
            {DATABASE_AUTH_VARIABLE: "entra"},
            "AZURE_CLIENT_ID: not set, KB_DATABASE_AUTH is entra",
        ),
        (
            {DATABASE_AUTH_VARIABLE: "entra", CLIENT_ID_VARIABLE: f"{{{CLIENT_ID}}}"},
            "AZURE_CLIENT_ID: not a GUID",
        ),
    ],
    ids=["unknown", "no client id", "not a guid"],
)
def test_a_setting_of_the_authentication_refused_names_the_variable(settings, refusal):
    environ = {DATABASE_URL_VARIABLE: ENTRA_URL, **settings}

    assert read_database_location_or_refusal(environ, DATA_DIR) == refusal


def test_kb_database_auth_is_left_alone_with_the_sqlite_base():
    assert read_database_location_or_refusal(
        {DATABASE_AUTH_VARIABLE: "entra"}, DATA_DIR
    ) == (DATA_DIR / "k-b.sqlite")


def test_the_client_id_of_the_identity_is_never_shown():
    location = PostgresUrl(ENTRA_URL, entra_client_id=CLIENT_ID)

    assert CLIENT_ID not in repr(location)
