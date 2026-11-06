"""GET /health of an API of K-B from a job: the answer of the API checked within its bound and by
a closed schema."""

import asyncio

import httpx2
import pytest

from k_b.core.api_health import answer_health
from k_b.core.config import MAX_HEALTH_ANSWER_BYTES
from k_b.jobs.api_health import HealthCheckError, build_health_client, check_health

TEST_API_URL = (
    "https://ca-kb-data-api.internal.example.francecentral.azurecontainerapps.io"
)


@pytest.fixture
def health_body():
    """The body GET /health of both APIs answers, from their own route."""
    return bytes(asyncio.run(answer_health(None)).body)


def check_with(handle):
    """Check the health of an API answered by handle; the requests sent are returned."""
    requests_sent = []

    def keep_and_handle(request):
        requests_sent.append(request)
        return handle(request)

    with build_health_client(
        TEST_API_URL, transport=httpx2.MockTransport(keep_and_handle)
    ) as http_client:
        check_health(http_client)
    return requests_sent


def test_an_api_that_answers_its_health_passes(health_body):
    [request] = check_with(lambda request: httpx2.Response(200, content=health_body))

    assert request.method == "GET"
    assert str(request.url) == f"{TEST_API_URL}/health"


@pytest.mark.parametrize(
    ("response", "description"),
    [
        (httpx2.Response(503, content=b'{"status":"ok"}'), "health_failed, HTTP 503"),
        (
            httpx2.Response(307, headers={"Location": "https://elsewhere.example/"}),
            "health_failed, HTTP 307",
        ),
        (httpx2.Response(200, content=b"<html>ok</html>"), "health_invalid_response"),
        (httpx2.Response(200, content=b'{"status":"down"}'), "health_invalid_response"),
        (
            httpx2.Response(200, content=b'{"status":"ok","base":"open"}'),
            "health_invalid_response",
        ),
        (
            httpx2.Response(200, content=b" " * MAX_HEALTH_ANSWER_BYTES + b"{}"),
            "health_invalid_response",
        ),
    ],
)
def test_an_answer_other_than_its_health_fails_with_a_named_state(
    response, description
):
    with pytest.raises(HealthCheckError) as raised:
        check_with(lambda request: response)

    assert str(raised.value) == description


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (httpx2.ReadTimeout("read timed out"), "health_timeout"),
        (httpx2.ConnectTimeout("connect timed out"), "health_timeout"),
        (httpx2.ConnectError("connection refused"), "health_unavailable"),
    ],
)
def test_an_api_out_of_reach_fails_with_a_named_state(error, state):
    def refuse(request):
        raise error

    with pytest.raises(HealthCheckError) as raised:
        check_with(refuse)

    assert raised.value.state == state
    assert str(raised.value) == state
