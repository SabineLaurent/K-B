"""The limit of each route of the data API, per client (docs/specs-api.md, "Débit")."""

from fastapi.routing import iter_route_contexts

from k_b.core.api_rate_limit import RateLimiter
from k_b.core.config import (
    DATA_API_RATE_LIMITS,
    MAX_ITEMS_PER_DIGEST_REQUEST,
    RateLimit,
)

PUBLIC_ROUTES = {"/docs", "/openapi.json", "/health", "/health/database"}
# The most a trend report reads (core/config.py, "The bound of a trend report request").
TREND_REPORT_READINGS = 32


def limit_each_route_to_one_call(client):
    client.app.state.rate_limiter = RateLimiter(
        dict.fromkeys(DATA_API_RATE_LIMITS, RateLimit(requests=1, window_seconds=60))
    )


def test_every_data_route_has_its_limit(client):
    data_routes = {
        route.path
        for route in iter_route_contexts(client.app.routes)
        if route.path not in PUBLIC_ROUTES
    }

    assert data_routes
    assert data_routes == set(DATA_API_RATE_LIMITS)


def test_beyond_its_limit_a_client_gets_429_with_its_wait_and_its_id(
    client, authorization
):
    limit_each_route_to_one_call(client)

    assert client.get("/items", headers=authorization).status_code == 200
    response = client.get("/items", headers=authorization)

    assert response.status_code == 429
    assert response.json() == {"error": "rate_limit_exceeded"}
    assert response.headers["Retry-After"] == "60"
    assert "X-Request-ID" in response.headers


def test_the_limit_is_per_client_and_per_route(client, api_keys, authorization):
    limit_each_route_to_one_call(client)
    client.get("/items", headers=authorization)
    other_client = {"Authorization": f"Bearer {api_keys['AGENT'].get_secret_value()}"}

    assert client.get("/items", headers=other_client).status_code == 200
    assert client.get("/items/1", headers=authorization).status_code != 429
    assert client.get("/items", headers=authorization).status_code == 429


def test_a_request_without_a_valid_key_counts_for_nothing(client, authorization):
    limit_each_route_to_one_call(client)

    for _ in range(3):
        assert client.get("/items").status_code == 401

    assert client.get("/items", headers=authorization).status_code == 200


def test_a_parameter_refused_counts(client, authorization):
    limit_each_route_to_one_call(client)

    assert client.get("/items?limit=0", headers=authorization).status_code == 422

    assert client.get("/items", headers=authorization).status_code == 429


def test_the_public_routes_have_no_limit(client):
    limit_each_route_to_one_call(client)

    for _ in range(3):
        assert client.get("/health").status_code == 200
        assert client.get("/health/database").status_code == 200


def test_a_digest_and_a_trend_report_at_their_caps_stay_under_the_limits():
    assert (
        DATA_API_RATE_LIMITS["/items/{item_id}"].requests
        >= MAX_ITEMS_PER_DIGEST_REQUEST
    )
    assert DATA_API_RATE_LIMITS["/trends"].requests >= TREND_REPORT_READINGS
