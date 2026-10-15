"""One log line per request (docs/specs-api.md, "Journal"): the client named, never its key, a
value of a parameter or a raw path."""

import logging

import pytest

from k_b.data_api.request_log import format_request_line


@pytest.fixture
def request_lines(caplog):
    """The request lines logged while the test runs."""
    caplog.set_level(logging.INFO, logger="k_b.data_api.request_log")

    def read():
        return [
            record.getMessage()
            for record in caplog.records
            if record.name == "k_b.data_api.request_log"
        ]

    return read


def test_a_request_line_names_the_client_never_the_key_a_value_or_the_path(
    client, api_keys, authorization, request_lines
):
    client.get("/items?q=langchain&limit=3", headers=authorization)

    [line] = request_lines()
    assert line.startswith("request method='GET' route=/items status=200 duration_ms=")
    assert line.endswith(" client=TERMINAL")
    for absent in (api_keys["TERMINAL"].get_secret_value(), "langchain", "limit", "?"):
        assert absent not in line


def test_a_401_is_logged_without_name_nor_received_value(client, request_lines):
    client.get("/items", headers={"Authorization": "Bearer key-received-by-the-api"})

    [line] = request_lines()
    assert "status=401" in line
    assert line.endswith(" client=-")
    assert "key-received-by-the-api" not in line


def test_a_400_of_the_host_is_logged(client, authorization, request_lines):
    client.get("/items", headers={**authorization, "Host": "evil.example"})

    [line] = request_lines()
    assert "status=400" in line
    assert "evil.example" not in line


def test_an_unknown_route_is_logged_without_its_path(
    client, authorization, request_lines
):
    client.get("/secret-path-of-the-test", headers=authorization)

    [line] = request_lines()
    assert "route=- status=404" in line
    assert "secret-path-of-the-test" not in line


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_a_public_route_is_logged_by_its_path(client, request_lines, path):
    client.get(path)

    [line] = request_lines()
    assert f"route={path} status=200" in line


def test_a_health_check_that_answers_200_is_not_logged(client, request_lines):
    """A probe every few seconds would bury the requests of the clients."""
    client.get("/health")

    assert request_lines() == []


@pytest.mark.parametrize(
    ("method", "headers", "status"),
    [("GET", {"Host": "evil.example"}, 400), ("POST", {}, 405)],
)
def test_a_health_check_that_fails_is_logged_by_its_path(
    client, request_lines, method, headers, status
):
    """A probe set wrong shows in the log."""
    client.request(method, "/health", headers=headers)

    [line] = request_lines()
    assert f"route=/health status={status}" in line


def test_a_request_without_response_is_logged_without_status():
    line = format_request_line("GET", "/items", None, 3, "-")

    assert line == "request method='GET' route=/items status=- duration_ms=3 client=-"


def test_the_method_is_quoted():
    line = format_request_line("GET\nfake line", "-", 400, 0, "-")

    assert "\n" not in line
    assert (
        line
        == r"request method='GET\nfake line' route=- status=400 duration_ms=0 client=-"
    )


def test_a_detail_is_logged_by_its_route_template_never_its_id(
    client, authorization, request_lines
):
    client.get("/items/14", headers=authorization)

    [line] = request_lines()
    assert " route=/items/{item_id} status=200 " in line
    assert "14" not in line.split(" duration_ms=")[0]
