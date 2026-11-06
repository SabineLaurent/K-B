"""The errors of the data API: a named state, no stack, no SQL, no path, no value received."""

import logging

import psycopg
import pytest
from fastapi.routing import iter_route_contexts

from k_b.core.config import (
    DATA_API_QUERY_TIMEOUT_SECONDS,
    DATA_API_READ_TIMEOUT_SECONDS,
    READING_POOL_WAIT_SECONDS,
)
from k_b.data_api.routers import item_router
from k_b.database import engine
from k_b.database.engine import make_deadline_check, open_readers

# The methods of RFC 9110 (section 9) and PATCH (RFC 5789), all sent by the test client.
HTTP_METHODS = (
    "GET",
    "HEAD",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "TRACE",
    "CONNECT",
)


def read_status_allow_and_body(response):
    """The status, the Allow header and the JSON body of a response; None for an empty body, as
    a response to HEAD always is (RFC 9110, section 9.3.2)."""
    return (
        response.status_code,
        response.headers.get("allow"),
        response.json() if response.content else None,
    )


def test_a_host_other_than_localhost_gives_400(client, authorization):
    response = client.get("/items", headers={**authorization, "Host": "evil.example"})

    assert response.status_code == 400


def test_an_unknown_route_gives_404_route_not_found(client, authorization):
    response = client.get("/secrets", headers=authorization)

    assert response.status_code == 404
    assert response.json() == {"error": "route_not_found"}


def test_a_final_slash_gives_404_not_a_redirection(client, authorization):
    response = client.get("/items/", headers=authorization, follow_redirects=False)

    assert response.status_code == 404
    assert response.json() == {"error": "route_not_found"}


def test_a_missing_database_gives_503_without_its_path(
    make_client, tmp_path, api_keys, authorization
):
    client = make_client(tmp_path / "k-b.sqlite", api_keys)

    response = client.get("/items", headers=authorization)

    assert response.status_code == 503
    assert response.json() == {"error": "database_missing"}


def test_a_database_error_gives_500_without_detail_and_logs_its_type(
    make_client, tmp_path, api_keys, authorization, caplog
):
    database_path = tmp_path / "k-b.sqlite"
    database_path.write_text("not an SQLite base")
    client = make_client(database_path, api_keys)

    with caplog.at_level(logging.ERROR, logger="k_b.data_api"):
        response = client.get("/items", headers=authorization)

    assert response.status_code == 500
    assert response.json() == {"error": "database_error"}
    request_id = response.headers["X-Request-ID"]
    assert f"database_error: DatabaseError request_id={request_id}" in caplog.text


@pytest.mark.parametrize("path", ["/items", "/items/14", "/trends"])
def test_a_request_beyond_its_deadline_gives_503_query_timeout_without_detail(
    client, authorization, caplog, monkeypatch, path
):
    """Each data route reads through the connection that carries the deadline: at 0 s, its first
    check stops the first reading."""
    # The detail and the trends of the test base run fewer instructions than one step.
    monkeypatch.setattr(engine, "INSTRUCTIONS_BETWEEN_CHECKS", 1)
    client.app.state.query_timeout_seconds = 0

    with caplog.at_level(logging.WARNING, logger="k_b.data_api"):
        response = client.get(path, headers=authorization)

    assert response.status_code == 503
    assert response.json() == {"error": "query_timeout"}
    request_id = response.headers["X-Request-ID"]
    assert f"query_timeout: 0 s request_id={request_id}" in caplog.text
    assert "interrupted" not in caplog.text
    assert "SELECT" not in caplog.text


# The deadline of the tests on PostgreSQL: statement_timeout at 0 would disable it.
POSTGRESQL_TIMEOUT_SECONDS = 0.1


@pytest.mark.postgresql
@pytest.mark.parametrize(
    ("path", "table"),
    [("/items", "item"), ("/items/14", "item"), ("/trends", "trend")],
)
def test_on_postgresql_a_request_beyond_its_deadline_gives_503_query_timeout_without_detail(
    make_client, items_postgresql_base, api_keys, authorization, caplog, path, table
):
    """A reading that waits for a table another connection holds is stopped by statement_timeout
    (57014): the same 503 as on SQLite."""
    holder = psycopg.connect(items_postgresql_base.value)
    try:
        # Names of the test only: nothing from outside enters the statement.
        holder.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
        with open_readers(items_postgresql_base, POSTGRESQL_TIMEOUT_SECONDS) as readers:
            client = make_client(readers, api_keys)
            client.app.state.query_timeout_seconds = POSTGRESQL_TIMEOUT_SECONDS
            with caplog.at_level(logging.WARNING):
                response = client.get(path, headers=authorization)
            # The connection is given back without transaction, and the pool says nothing.
            with readers.connection() as connection:
                status = connection.info.transaction_status
    finally:
        holder.close()

    assert response.status_code == 503
    assert response.json() == {"error": "query_timeout"}
    request_id = response.headers["X-Request-ID"]
    assert f"query_timeout: 0.1 s request_id={request_id}" in caplog.text
    assert "canceling statement" not in caplog.text
    assert "SELECT" not in caplog.text
    assert status == psycopg.pq.TransactionStatus.IDLE
    assert not [
        record for record in caplog.records if record.name.startswith("psycopg")
    ]


@pytest.mark.postgresql
def test_on_postgresql_a_database_error_gives_500_without_detail_and_logs_its_type(
    make_client, postgresql_base, api_keys, authorization, caplog
):
    """A base without the tables of K-B: the type of the error only, never its message."""
    with open_readers(postgresql_base, DATA_API_QUERY_TIMEOUT_SECONDS) as readers:
        client = make_client(readers, api_keys)
        with caplog.at_level(logging.ERROR, logger="k_b.data_api"):
            response = client.get("/items", headers=authorization)

    assert response.status_code == 500
    assert response.json() == {"error": "database_error"}
    request_id = response.headers["X-Request-ID"]
    assert f"database_error: UndefinedTable request_id={request_id}" in caplog.text
    assert "does not exist" not in caplog.text


def test_the_deadline_starts_at_the_first_check_of_sqlite_not_at_the_opening():
    """The wait for a thread between the dependency and the route is not counted."""
    now = [100.0]
    check_deadline = make_deadline_check(5, clock=lambda: now[0])

    now[0] = 130.0
    assert check_deadline() == 0
    now[0] = 134.9
    assert check_deadline() == 0
    now[0] = 135.0
    assert check_deadline() == 1


def test_the_deadline_of_a_request_is_below_the_read_timeout_of_the_ai_api_client(
    client,
):
    assert client.app.state.query_timeout_seconds == DATA_API_QUERY_TIMEOUT_SECONDS
    assert DATA_API_QUERY_TIMEOUT_SECONDS < DATA_API_READ_TIMEOUT_SECONDS


def test_the_wait_for_a_connection_and_one_reading_hold_below_the_read_timeout_of_the_client():
    """On PostgreSQL, a request may first wait for a connection of the pool."""
    assert (
        READING_POOL_WAIT_SECONDS + DATA_API_QUERY_TIMEOUT_SECONDS
        < DATA_API_READ_TIMEOUT_SECONDS
    )


@pytest.fixture
def error_responses(make_client, client, tmp_path, api_keys, authorization):
    """A response of each error status a data route gives."""
    missing = make_client(tmp_path / "missing" / "k-b.sqlite", api_keys)
    broken_path = tmp_path / "k-b.sqlite"
    broken_path.write_text("not an SQLite base")
    broken = make_client(broken_path, api_keys)
    return [
        client.get("/items"),
        client.get("/items?limit=101", headers=authorization),
        missing.get("/items", headers=authorization),
        broken.get("/items", headers=authorization),
    ]


def test_no_error_body_holds_a_raw_file_path_or_a_path(error_responses, tmp_path):
    assert [response.status_code for response in error_responses] == [
        401,
        422,
        503,
        500,
    ]
    for response in error_responses:
        for absent in (
            "raw_file_path",
            "selected_library/",
            str(tmp_path),
            "k-b.sqlite",
        ):
            assert absent not in response.text


def test_an_unexpected_error_gives_500_internal_error_and_logs_its_type_only(
    client, authorization, monkeypatch, caplog
):
    def fail(*_, **__):
        raise RuntimeError("value received by the test")

    monkeypatch.setattr(item_router, "read_items", fail)

    with caplog.at_level(logging.INFO, logger="k_b"):
        response = client.get("/items", headers=authorization)

    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    request_id = response.headers["X-Request-ID"]
    assert f"internal_error: RuntimeError request_id={request_id}" in caplog.text
    assert "status=500" in caplog.text
    assert "value received by the test" not in caplog.text
    assert "Traceback" not in caplog.text


def test_every_route_answers_get_only_and_405_to_any_other_method(
    client, authorization
):
    """HEAD too, which Starlette adds to a GET route (OWASP API8:2023, verbs)."""
    answers = {
        (route.path, method): read_status_allow_and_body(
            client.request(method, route.path.format(item_id=1), headers=authorization)
        )
        for route in iter_route_contexts(client.app.routes)
        for method in HTTP_METHODS
        if method != "GET"
    }

    assert answers
    assert answers == {
        (path, method): (
            405,
            "GET",
            None if method == "HEAD" else {"error": "method_not_allowed"},
        )
        for path, method in answers
    }


@pytest.mark.parametrize("path", ["/items", "/items/1", "/trends"])
def test_no_route_answers_cors(client, authorization, path):
    """No CORS: a page of another origin cannot read a response in a browser."""
    origin = {"Origin": "https://evil.example"}

    response = client.get(path, headers={**authorization, **origin})
    preflight = client.options(
        path, headers={**origin, "Access-Control-Request-Method": "GET"}
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in preflight.headers


def test_a_body_the_data_api_never_reads_gives_no_400_nor_422(client, authorization):
    """A data route reads no body: the 400 of an unreadable body, answered 422, does not reach
    the data API."""
    response = client.request(
        "GET",
        "/items",
        content=b"\xff",
        headers={**authorization, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
