"""The rules of a connection K-B opens by HTTP: the URL it accepts, its HTTP client, and the
bound of a body read."""

import gzip

import httpx2
import pytest

from k_b.core.outbound import (
    BodyTooLargeError,
    BodyTooLateError,
    find_internal_api_url_refusal,
    find_url_refusal,
    open_http_client,
    read_body_head,
    read_bounded_body,
)

VARIABLE = "KB_TEST_URL"
HTTP_REFUSAL = f"{VARIABLE}: https required; http only to the machine (127.0.0.1 or localhost) or, in the sandbox, a compose service (api-donnees or api-ia)"


SANDBOX = {"KB_DEPLOYMENT_ENVIRONMENT": "sandbox"}
PRODUCTION = {"KB_DEPLOYMENT_ENVIRONMENT": "production"}


@pytest.mark.parametrize(
    ("url", "environ"),
    [
        ("http://127.0.0.1:8000", {}),
        ("http://localhost:8001", {}),
        ("http://127.0.0.1:8000", PRODUCTION),
        ("https://ca-kb-data-api.internal.test.example", {}),
        ("https://ca-kb-data-api.internal.test.example", PRODUCTION),
        ("http://api-donnees:8000", SANDBOX),
        ("http://api-ia:8001", SANDBOX),
    ],
    ids=[
        "ipv4-loopback",
        "localhost",
        "loopback-in-production",
        "https",
        "https-in-production",
        "data-api-service-in-the-sandbox",
        "ai-api-service-in-the-sandbox",
    ],
)
def test_an_internal_api_url_in_https_on_the_machine_or_to_a_compose_service_is_accepted(
    url, environ
):
    assert find_internal_api_url_refusal(VARIABLE, url, environ) is None


@pytest.mark.parametrize(
    ("url", "environ", "refusal"),
    [
        ("http://api-donnees:8000", {}, HTTP_REFUSAL),
        ("http://api-donnees:8000", PRODUCTION, HTTP_REFUSAL),
        (
            "http://api-donnees:8000",
            {"KB_DEPLOYMENT_ENVIRONMENT": "Sandbox"},
            HTTP_REFUSAL,
        ),
        ("http://ca-kb-data-api.internal.test.example", {}, HTTP_REFUSAL),
        ("http://ca-kb-ai-api.test.example", SANDBOX, HTTP_REFUSAL),
        ("http://134744072", SANDBOX, HTTP_REFUSAL),
        ("http://api-ai:8001", SANDBOX, HTTP_REFUSAL),
        ("http://127.0.0.2:8000", {}, HTTP_REFUSAL),
        ("http://localhost.test.example", {}, HTTP_REFUSAL),
        ("ftp://127.0.0.1", {}, f"{VARIABLE}: scheme not http nor https"),
    ],
    ids=[
        "service-without-environment",
        "service-in-production",
        "service-sandbox-capitalised",
        "internal-name",
        "public-name-in-the-sandbox",
        "ipv4-as-one-number-in-the-sandbox",
        "service-misspelt-in-the-sandbox",
        "other-loopback",
        "localhost-prefix",
        "ftp",
    ],
)
def test_an_internal_api_url_in_http_elsewhere_is_refused(url, environ, refusal):
    assert find_internal_api_url_refusal(VARIABLE, url, environ) == refusal


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000", "https://api-donnees:8000/kb", "http://localhost"]
)
def test_a_url_of_an_allowed_scheme_is_accepted(url):
    assert find_url_refusal(VARIABLE, url, ("http", "https")) is None


@pytest.mark.parametrize(
    ("url", "schemes", "refusal"),
    [
        ("ftp://host", ("https",), "KB_TEST_URL: scheme not https"),
        ("ftp://host", ("http", "https"), "KB_TEST_URL: scheme not http nor https"),
        ("http://", ("http",), "KB_TEST_URL: no host"),
        ("http://ho_st", ("http",), "KB_TEST_URL: host not a lowercase host name"),
        ("http://host:99999", ("http",), "KB_TEST_URL: not a URL"),
        ("http://user:secret@host", ("http",), "KB_TEST_URL: with user information"),
        (
            "http://host/?key=secret",
            ("http",),
            "KB_TEST_URL: with a query or a fragment",
        ),
        ("http://host/#secret", ("http",), "KB_TEST_URL: with a query or a fragment"),
    ],
)
def test_a_url_refused_is_named_by_its_variable_never_quoted(url, schemes, refusal):
    assert find_url_refusal(VARIABLE, url, schemes) == refusal


def test_the_client_reads_no_proxy_of_the_environment_and_follows_no_redirection(
    monkeypatch,
):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")

    # Without transport: with one, httpx2 never reads the proxies of the environment, so the
    # behavior would prove nothing.
    with open_http_client(
        "http://127.0.0.1:8000", {}, httpx2.Timeout(1.0), transport=None
    ) as http_client:
        assert http_client.trust_env is False
        assert http_client.follow_redirects is False


class CountedPieces:
    """A body sent in pieces, counting those read."""

    def __init__(self, *pieces):
        self.pieces = pieces
        self.pieces_read = 0

    def __iter__(self):
        for piece in self.pieces:
            self.pieces_read += 1
            yield piece


def test_the_head_of_a_body_is_kept_up_to_its_bound_the_rest_left_unread():
    body = CountedPieces(b"a" * 6, b"b" * 6, b"c" * 6)

    head = read_body_head(httpx2.Response(200, content=body), 8)

    assert head == b"a" * 6 + b"b" * 2
    assert body.pieces_read == 2


def test_a_body_within_the_bound_of_a_head_is_kept_whole():
    assert read_body_head(httpx2.Response(200, content=iter([b"abc"])), 8) == b"abc"


def test_the_head_ignores_a_length_announced_beyond_its_bound():
    response = httpx2.Response(
        200, content=iter([b"a" * 12]), headers={"Content-Length": "1000000"}
    )

    assert read_body_head(response, 8) == b"a" * 8


def test_the_head_of_a_gzip_body_is_kept_once_decoded():
    response = httpx2.Response(
        200,
        content=iter([gzip.compress(b"a" * 100_000)]),
        headers={"Content-Encoding": "gzip"},
    )

    assert read_body_head(response, 10) == b"a" * 10


def test_the_head_stops_at_its_deadline():
    with pytest.raises(BodyTooLateError):
        read_body_head(
            httpx2.Response(200, content=iter([b"a", b"b"])), 8, lambda: True
        )


def test_a_bounded_body_is_still_refused_beyond_its_bound():
    with pytest.raises(BodyTooLargeError):
        read_bounded_body(httpx2.Response(200, content=iter([b"a" * 9])), 8)
