"""The errors of the data API (docs/specs-api.md, "Erreurs"): a named state, no stack, no SQL,
no path, no value received."""

import logging

import pytest


def test_a_host_other_than_localhost_gives_400(client, authorization):
    response = client.get("/items", headers={**authorization, "Host": "evil.example"})

    assert response.status_code == 400


def test_an_unknown_route_gives_404_route_not_found(client, authorization):
    response = client.get("/secrets", headers=authorization)

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
    assert "database_error: DatabaseError" in caplog.text


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
