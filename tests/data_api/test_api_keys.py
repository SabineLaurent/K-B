"""The key of each client (docs/specs-api.md, "Accès par clé")."""

import secrets

import pytest

from k_b.data_api.app import create_app

INVALID_API_KEY = {"error": "invalid_api_key"}


def list_data_routes(items_database, api_keys):
    """The routes the app documents, read from it: a route added later is tested as well. /docs
    and /openapi.json are not documented."""
    return list(create_app(items_database, api_keys).openapi()["paths"])


def test_the_data_routes_are_listed(items_database, api_keys):
    assert list_data_routes(items_database, api_keys) == ["/items"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-key-of-the-test"},
        {"Authorization": "Basic dGVzdDp0ZXN0"},
        {"Authorization": "Bearer"},
    ],
)
def test_every_data_route_refuses_a_missing_and_a_wrong_key_with_the_same_body(
    client, items_database, api_keys, headers
):
    for path in list_data_routes(items_database, api_keys):
        response = client.get(path, headers=headers)

        assert response.status_code == 401
        assert response.json() == INVALID_API_KEY
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("client_name", ["TERMINAL", "AGENT"])
def test_each_client_is_served_with_its_key(client, api_keys, client_name):
    key = api_keys[client_name].get_secret_value()

    response = client.get("/items", headers={"Authorization": f"Bearer {key}"})

    assert response.status_code == 200


def test_a_non_ascii_key_gives_401_not_500(client):
    # httpx sends a header given as bytes as it is: é in Latin-1, as a client could.
    response = client.get(
        "/items", headers={"Authorization": "Bearer clé".encode("latin-1")}
    )

    assert response.status_code == 401
    assert response.json() == INVALID_API_KEY


def test_a_removed_key_gives_401_and_the_other_clients_are_still_served(
    make_client, items_database, api_keys
):
    agent_key = api_keys["AGENT"].get_secret_value()
    terminal_key = api_keys["TERMINAL"].get_secret_value()
    # The app restarted without the variable of the agent.
    client = make_client(items_database, {"TERMINAL": api_keys["TERMINAL"]})

    agent_response = client.get(
        "/items", headers={"Authorization": f"Bearer {agent_key}"}
    )
    terminal_response = client.get(
        "/items", headers={"Authorization": f"Bearer {terminal_key}"}
    )

    assert agent_response.status_code == 401
    assert terminal_response.status_code == 200


def test_an_app_without_key_refuses_every_data_route(make_client, items_database):
    client = make_client(items_database, {})

    response = client.get(
        "/items", headers={"Authorization": f"Bearer {secrets.token_urlsafe(32)}"}
    )

    assert response.status_code == 401


def test_without_a_key_a_wrong_parameter_gives_401(client):
    response = client.get("/items?limit=101")

    assert response.status_code == 401
    assert response.json() == INVALID_API_KEY


def test_with_a_key_a_wrong_parameter_and_no_database_gives_503(
    make_client, tmp_path, api_keys, authorization
):
    """The connection is a dependency: it is opened before the parameters are checked."""
    client = make_client(tmp_path / "k-b.sqlite", api_keys)

    response = client.get("/items?limit=101", headers=authorization)

    assert response.status_code == 503


def test_docs_and_openapi_are_public_and_redoc_is_not_served(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/redoc").status_code == 404
