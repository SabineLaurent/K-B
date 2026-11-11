"""The pages of the site and its errors: an HTML page for each, its security headers and its cache,
never the text of an exception, nor a document of an API."""

import logging
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jinja2 import StrictUndefined
from site_client import OPERATOR_HEADERS, PAGE_PATHS, make_client

from k_b.web.app import create_app
from k_b.web.errors import write_moment
from k_b.web.rendering import templates

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self';"
    " base-uri 'none'; frame-ancestors 'none'"
)
EXCEPTION_DETAIL = "a detail the exception holds"


@pytest.fixture
def client():
    return make_client()


@pytest.fixture
def failing_client():
    """The site with one more route, which fails as no page should."""
    app = create_app(operator_id=None)

    @app.get("/failing")
    def fail() -> None:
        raise RuntimeError(EXCEPTION_DETAIL)

    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("/", "Quoi de neuf · K-B"),
        ("/sources", "Sources et conditions d’utilisation · K-B"),
        ("/accessibilite", "Accessibilité · K-B"),
    ],
)
def test_each_page_is_served_in_html_with_its_title(client, path, title):
    response = client.get(path, headers=OPERATOR_HEADERS)

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert f"<title>{title}</title>" in response.text


def test_an_unknown_route_gets_the_page_not_found(client):
    response = client.get("/no-such-page", headers=OPERATOR_HEADERS)

    assert response.status_code == 404
    assert "Page introuvable" in response.text
    assert 'href="/"' in response.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/"),
        ("HEAD", "/"),
        ("POST", "/static/site.css"),
        ("DELETE", "/sources"),
    ],
)
def test_a_method_refused_gets_a_page_too(client, method, path):
    response = client.request(method, path, headers=OPERATOR_HEADERS)

    assert response.status_code == 405
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"


def test_an_unexpected_error_gets_the_page_500_without_its_detail(
    failing_client, caplog
):
    before = datetime.now(UTC).replace(microsecond=0)
    with caplog.at_level(logging.INFO, logger="k_b"):
        response = failing_client.get("/failing")

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 500
    assert "Erreur du serveur" in response.text
    assert EXCEPTION_DETAIL not in response.text
    assert request_id in response.text
    assert f"internal_error: RuntimeError request_id={request_id}" in [
        record.getMessage() for record in caplog.records
    ]
    assert not any(EXCEPTION_DETAIL in record.getMessage() for record in caplog.records)
    [moment] = re.findall(r'<time datetime="([0-9T:Z-]+)">', response.text)
    assert before <= datetime.fromisoformat(moment) <= before + timedelta(seconds=5)


@pytest.mark.parametrize(
    ("moment", "text"),
    [
        (datetime(2026, 11, 1, 9, 5, 59, tzinfo=UTC), "1er novembre 2026 à 09:05 UTC"),
        (datetime(2026, 2, 28, 23, 0, tzinfo=UTC), "28 février 2026 à 23:00 UTC"),
        (datetime(2027, 8, 15, 0, 30, tzinfo=UTC), "15 août 2027 à 00:30 UTC"),
    ],
)
def test_the_time_of_an_error_gives_its_month_in_letters(moment, text):
    """Opquast 2025, rule 4: 01/11/2026 reads 1 November or 11 January."""
    assert write_moment(moment) == text


def test_try_again_reloads_the_page_itself_never_a_path_received(failing_client):
    """A path received may be //host/x: written in a link, it would lead to another site."""
    response = failing_client.get("/failing")

    assert 'href="">Réessayer</a>' in response.text
    assert "/failing" not in response.text


@pytest.mark.parametrize(
    ("path", "headers", "status_code", "cache_control"),
    [
        ("/", OPERATOR_HEADERS, 200, "no-store"),
        ("/sources", OPERATOR_HEADERS, 200, "no-store"),
        ("/static/site.css", OPERATOR_HEADERS, 200, "no-cache"),
        ("/health", {}, 200, "no-store"),
        ("/", {}, 403, "no-store"),
        ("/no-such-page", OPERATOR_HEADERS, 404, "no-store"),
    ],
)
def test_every_answer_has_its_security_headers_and_its_cache(
    client, path, headers, status_code, cache_control
):
    response = client.get(path, headers=headers)

    assert response.status_code == status_code
    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == cache_control


def test_the_page_500_has_its_security_headers_and_is_not_kept(failing_client):
    response = failing_client.get("/failing")

    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["Cache-Control"] == "no-store"


def test_a_host_not_allowed_is_refused_with_the_security_headers():
    response = TestClient(
        create_app(operator_id=None), base_url="http://example.org"
    ).get("/")

    assert response.status_code == 400
    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY


def test_a_host_without_the_www_of_an_allowed_host_is_refused_never_redirected():
    """Starlette would build its redirection with the scheme it sees, http behind the ingress."""
    app = create_app(operator_id=None, allowed_hosts=("www.example.org",))
    client = TestClient(app, base_url="http://example.org")

    assert client.get("/", follow_redirects=False).status_code == 400


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/sources/"])
def test_no_document_of_an_api_nor_a_redirection_is_served(client, path):
    assert (
        client.get(path, headers=OPERATOR_HEADERS, follow_redirects=False).status_code
        == 404
    )


@pytest.mark.parametrize("path", PAGE_PATHS)
def test_a_page_is_compressed_for_a_browser_that_takes_gzip(client, path):
    response = client.get(path, headers={**OPERATOR_HEADERS, "Accept-Encoding": "gzip"})

    assert response.headers["Content-Encoding"] == "gzip"


def test_the_templates_escape_every_value_and_refuse_an_undefined_one():
    assert templates.env.autoescape is True
    assert templates.env.undefined is StrictUndefined
    assert templates.env.from_string("{{ value }}").render(value="<b>") == "&lt;b&gt;"


def test_an_error_page_is_compressed_too(client):
    """The page 403 and the page 404 hold an illustration: as large as a page, compressed too."""
    for headers in ({}, OPERATOR_HEADERS):
        response = client.get(
            "/no-such-page", headers={**headers, "Accept-Encoding": "gzip"}
        )

        assert response.headers["Content-Encoding"] == "gzip"
