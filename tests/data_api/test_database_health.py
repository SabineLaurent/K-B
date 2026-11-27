"""GET /health/database: whether the data API reads its base, served without key, one call at a
time, never asked by a probe of Azure Container Apps (docs/specs-api.md, "Santé"); a failure gets
the answer a data route gets for the same cause."""

import logging
import re
from pathlib import Path

import pytest
from database.connected_readers import open_connected_readers

from k_b.core.config import DATA_API_QUERY_TIMEOUT_SECONDS, READING_POOL_WAIT_SECONDS
from k_b.database import engine, postgresql
from k_b.database.engine import connect_database, open_readers
from k_b.database.location import PostgresUrl

DATABASE_HEALTH_PATH = "/health/database"
INFRA_DIR = Path(__file__).parents[2] / "infra"
# Statements of the test only, on the bases it creates.
SELECT_SOURCE_CODES = "SELECT source_code FROM source"
DELETE_SOURCES = "DELETE FROM source"
# No server listens on port 1: each connection of the pool is refused at once.
UNREACHABLE_BASE = PostgresUrl("postgresql://kb@127.0.0.1:1/kb")


def ask_database_health(client, caplog):
    """GET /health/database, its lines of the data API kept."""
    with caplog.at_level(logging.INFO, logger="k_b"):
        return client.get(DATABASE_HEALTH_PATH)


def test_the_database_health_answers_ok_without_key_on_each_engine(reading_client):
    response = reading_client.get(DATABASE_HEALTH_PATH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_answer_holds_no_value_of_the_row_read(client, items_database):
    """The body is the one of /health, byte for byte: no source of the base is in it."""
    connection = connect_database(items_database)
    try:
        source_codes = [code for (code,) in connection.execute(SELECT_SOURCE_CODES)]
    finally:
        connection.close()

    response = client.get(DATABASE_HEALTH_PATH)

    assert source_codes
    assert response.content == b'{"status":"ok"}'


def test_a_base_without_any_source_answers_ok(make_client, new_base, api_keys):
    """The statement reads one row at most: an empty table is a base the API reads."""
    connection = connect_database(new_base)
    try:
        connection.execute(DELETE_SOURCES)
        connection.commit()
    finally:
        connection.close()

    with open_connected_readers(new_base, DATA_API_QUERY_TIMEOUT_SECONDS) as readers:
        response = make_client(readers, api_keys).get(DATABASE_HEALTH_PATH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_a_missing_base_gives_503_database_missing_as_a_data_route(
    make_client, tmp_path, api_keys, caplog
):
    client = make_client(tmp_path / "k-b.sqlite", api_keys)

    response = ask_database_health(client, caplog)

    assert response.status_code == 503
    assert response.json() == {"error": "database_missing"}
    assert f"route={DATABASE_HEALTH_PATH} status=503" in caplog.text
    assert str(tmp_path) not in caplog.text


@pytest.mark.postgresql
def test_on_postgresql_a_base_without_its_tables_gives_503_database_missing(
    make_client, postgresql_base, api_keys, caplog
):
    """A base not yet migrated (42P01): the answer of a data route, not a 200 of the server."""
    with open_connected_readers(
        postgresql_base, DATA_API_QUERY_TIMEOUT_SECONDS
    ) as readers:
        response = ask_database_health(make_client(readers, api_keys), caplog)

    assert response.status_code == 503
    assert response.json() == {"error": "database_missing"}
    request_id = response.headers["X-Request-ID"]
    assert (
        f"database_missing: UndefinedTable 42P01 request_id={request_id}" in caplog.text
    )


def test_a_broken_base_gives_500_database_error_and_logs_its_class_only(
    make_client, tmp_path, api_keys, caplog
):
    database_path = tmp_path / "k-b.sqlite"
    database_path.write_text("not an SQLite base")
    client = make_client(database_path, api_keys)

    response = ask_database_health(client, caplog)

    assert response.status_code == 500
    assert response.json() == {"error": "database_error"}
    request_id = response.headers["X-Request-ID"]
    assert f"database_error: DatabaseError request_id={request_id}" in caplog.text
    assert "not a database" not in caplog.text


def test_a_reading_beyond_its_deadline_gives_503_query_timeout(
    client, monkeypatch, caplog
):
    """At 0 s, the first check of SQLite stops the statement."""
    monkeypatch.setattr(engine, "INSTRUCTIONS_BETWEEN_CHECKS", 1)
    client.app.state.query_timeout_seconds = 0

    response = ask_database_health(client, caplog)

    assert response.status_code == 503
    assert response.json() == {"error": "query_timeout"}
    request_id = response.headers["X-Request-ID"]
    assert f"query_timeout: 0 s request_id={request_id}" in caplog.text
    assert "interrupted" not in caplog.text


def test_a_pool_that_lends_no_connection_gives_503_database_unavailable(
    make_client, api_keys, monkeypatch, caplog
):
    """A base that does not answer: the check waits for the pool, then PoolTimeout."""
    monkeypatch.setattr(postgresql, "READING_POOL_WAIT_SECONDS", 0.1)
    with open_readers(UNREACHABLE_BASE, DATA_API_QUERY_TIMEOUT_SECONDS) as readers:
        response = ask_database_health(make_client(readers, api_keys), caplog)

    assert response.status_code == 503
    assert response.json() == {"error": "database_unavailable"}
    request_id = response.headers["X-Request-ID"]
    assert f"database_unavailable: PoolTimeout request_id={request_id}" in caplog.text
    # The pool quotes the host, under a logger kb holds at ERROR (LIBRARY_LOG_LEVELS).
    assert not [
        record
        for record in caplog.records
        if record.name.startswith("k_b") and "127.0.0.1" in record.getMessage()
    ]


def test_a_call_while_another_runs_gets_429_with_the_wait_of_the_one_under_way(
    client,
):
    """Without key, the route would otherwise let anyone hold every connection of the pool."""
    slot = client.app.state.database_health_slot
    slot.acquire()
    try:
        response = client.get(DATABASE_HEALTH_PATH)
    finally:
        slot.release()

    assert response.status_code == 429
    assert response.json() == {"error": "request_already_running"}
    assert response.headers["Retry-After"] == str(
        READING_POOL_WAIT_SECONDS + DATA_API_QUERY_TIMEOUT_SECONDS
    )
    assert client.get(DATABASE_HEALTH_PATH).status_code == 200


def test_the_slot_is_given_back_after_a_failure(make_client, tmp_path, api_keys):
    client = make_client(tmp_path / "k-b.sqlite", api_keys)

    assert client.get(DATABASE_HEALTH_PATH).status_code == 503
    assert client.get(DATABASE_HEALTH_PATH).status_code == 503


def test_a_check_that_answers_200_is_logged_by_its_path(client, caplog):
    """Unlike /health: no probe asks it every few seconds."""
    response = ask_database_health(client, caplog)

    request_id = response.headers["X-Request-ID"]
    assert (
        f"route={DATABASE_HEALTH_PATH} status=200 duration_ms=" in caplog.text
        and f"client=- request_id={request_id}" in caplog.text
    )


def test_the_database_health_is_out_of_the_openapi(client):
    assert DATABASE_HEALTH_PATH not in client.get("/openapi.json").json()["paths"]


def test_a_host_other_than_the_allowed_ones_gives_400(client):
    response = client.get(DATABASE_HEALTH_PATH, headers={"Host": "evil.example"})

    assert response.status_code == 400


def test_no_probe_of_azure_container_apps_asks_the_database_health():
    """A probe that opened the base would restart the API at each failure of the base: the only
    probes are those of the module of the apps, each the request whose path is /health."""
    bicep_texts = {
        path.name: path.read_text("utf-8") for path in INFRA_DIR.rglob("*.bicep")
    }
    probe_module = bicep_texts["api-container-app.bicep"]

    assert [name for name, text in bicep_texts.items() if "probes:" in text] == [
        "api-container-app.bicep"
    ]
    assert re.findall(r"httpGet: (\w+)", probe_module) == ["probeRequest"] * 3
    assert re.findall(r"path: '([^']*)'", probe_module) == ["/health"]
