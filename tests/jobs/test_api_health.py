"""GET /health of an API of K-B from a job: the answer of the API checked within its bound and by
a closed schema."""

import asyncio
from functools import partial

import httpx2
import pytest

from k_b.core.api_health import DATABASE_HEALTH_PATH, answer_health
from k_b.core.config import (
    HEALTH_CONNECT_TIMEOUT_SECONDS,
    HEALTH_READ_TIMEOUT_SECONDS,
    MAX_HEALTH_ANSWER_BYTES,
)
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


def test_the_health_of_the_base_is_asked_at_its_own_path(health_body):
    requests_sent = []

    def keep_and_answer(request):
        requests_sent.append(request)
        return httpx2.Response(200, content=health_body)

    with build_health_client(
        TEST_API_URL, transport=httpx2.MockTransport(keep_and_answer)
    ) as http_client:
        check_health(http_client, DATABASE_HEALTH_PATH)

    [request] = requests_sent
    assert (request.method, str(request.url)) == (
        "GET",
        f"{TEST_API_URL}/health/database",
    )


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


def make_clock(*times):
    """A clock that gives each time in turn, then the last one."""
    remaining = list(times)

    def clock():
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return clock


@pytest.mark.parametrize(
    ("seconds_to_answer", "is_late"),
    [
        # Connection, then a whole read: the wake of an API at 0 replica.
        (HEALTH_CONNECT_TIMEOUT_SECONDS + HEALTH_READ_TIMEOUT_SECONDS - 1, False),
        (HEALTH_CONNECT_TIMEOUT_SECONDS + HEALTH_READ_TIMEOUT_SECONDS + 1, True),
    ],
)
def test_the_answer_has_the_time_of_a_connection_then_of_a_read(
    health_body, seconds_to_answer, is_late
):
    with build_health_client(
        TEST_API_URL,
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(200, content=health_body)
        ),
    ) as http_client:
        check = partial(
            check_health, http_client, clock=make_clock(0, seconds_to_answer)
        )
        if not is_late:
            check()
            return
        with pytest.raises(HealthCheckError) as raised:
            check()

    assert str(raised.value) == "health_timeout"
