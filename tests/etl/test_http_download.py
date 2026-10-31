import gzip
import logging

import httpx2
import pytest
from http_helpers import CountedStream, answer

from k_b.core.config import HTTP_MAX_REDIRECTS, HTTP_TIMEOUT_SECONDS
from k_b.core.user_agent import USER_AGENT
from k_b.etl import http_download
from k_b.etl.http_download import RedirectedOutsideError, download
from k_b.etl.source_contract import PageRefusedError, SourceStatusError

BODY = b"<feed>one paper</feed>"
TRUSTED_URL_PREFIX = "https://example.org/"
URL = TRUSTED_URL_PREFIX + "feed?page=1"
TOKEN_HEADER = {"Authorization": "Bearer test-token"}


@pytest.fixture
def network(fake_network):
    fake_network.body = BODY
    return fake_network


def redirection(location, status=302):
    return answer(status, Location=location)


# === Redirections, checked before they are followed ===


@pytest.mark.parametrize(
    "location",
    [
        "http://example.org/feed?page=2",
        "https://example.com/feed",
        "https://example.org.example.com/feed",
        "https://example.org\\@example.com/feed",
    ],
    ids=["plain-http", "other-host", "host-prefixed", "user-info"],
)
def test_a_redirection_outside_the_prefix_is_refused_without_requesting_it(
    network, location
):
    network.answers = [redirection(location)]

    with pytest.raises(RedirectedOutsideError):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert network.requested_urls() == [URL]


@pytest.mark.parametrize(
    "location",
    ["https://example.org/feed/../../login", "../../login"],
    ids=["absolute", "relative"],
)
def test_a_redirection_whose_dot_segments_leave_the_prefix_is_refused(
    network, location
):
    prefix = "https://example.org/feed/"
    network.answers = [redirection(location)]

    with pytest.raises(RedirectedOutsideError):
        download(prefix + "2026-10-04", prefix, max_bytes=1000)

    assert network.requested_urls() == [prefix + "2026-10-04"]


def test_a_redirection_to_a_url_with_a_tab_is_never_requested(network):
    location = "https://example.org/feed\t/../../login"
    network.answers = [redirection(location), redirection(location)]

    # httpx2 refuses the Location itself: a failure of the answer, retried once.
    with pytest.raises(httpx2.RemoteProtocolError, match="location header"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert network.requested_urls() == [URL, URL]


@pytest.mark.parametrize(
    "location",
    [b"https://a]b/", b"//a]b/x", " //\N{SOFT HYPHEN}".encode()],
    ids=["urljoin-refuses", "urljoin-refuses-relative", "httpx2-refuses-the-target"],
)
def test_a_redirection_httpx2_reads_but_not_its_resolution_is_refused(
    network, location
):
    # httpx2 reads these Locations; urljoin, or httpx2 once urljoin has resolved them, does not.
    network.answers = [answer(302, Location=location)]

    with pytest.raises(PageRefusedError, match="unreadable location"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert network.requested_urls() == [URL]


def test_a_refused_redirection_tells_its_target_resolved_on_the_requested_url(network):
    network.answers = [redirection("/landing")]

    with pytest.raises(RedirectedOutsideError) as refusal:
        download(URL, URL, max_bytes=1000)

    assert refusal.value.redirect_url == "https://example.org/landing"
    assert isinstance(refusal.value, ValueError)
    assert str(refusal.value) == (
        f"response redirected to https://example.org/landing, outside {URL}, refused"
    )


def test_a_refused_redirection_is_quoted_without_its_query_nor_fragment(network):
    target = "https://example.com/landing?session=secret#part"
    network.answers = [redirection(target)]

    with pytest.raises(RedirectedOutsideError) as refusal:
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert refusal.value.redirect_url == target
    assert "secret" not in str(refusal.value)
    assert "part" not in str(refusal.value)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirection_inside_the_prefix_is_followed_without_the_token(network, status):
    network.answers = [redirection("/feed?page=2", status)]

    body = download(
        URL,
        TRUSTED_URL_PREFIX,
        max_bytes=1000,
        headers={"Accept": "application/atom+xml"},
        unredirected_headers=TOKEN_HEADER,
    )

    assert body == BODY
    first, second = network.requests
    assert str(second.url) == "https://example.org/feed?page=2"
    assert second.method == "GET"
    assert first.headers["Authorization"] == "Bearer test-token"
    assert "Authorization" not in second.headers
    assert second.headers["Accept"] == "application/atom+xml"
    assert second.headers["User-Agent"] == USER_AGENT


def test_a_token_is_not_sent_again_to_the_same_url_after_a_redirection(network):
    network.answers = [redirection(URL)]

    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000, unredirected_headers=TOKEN_HEADER)

    assert "Authorization" not in network.requests[1].headers


def test_the_last_redirection_allowed_is_followed(network):
    network.answers = [redirection(URL)] * HTTP_MAX_REDIRECTS

    assert download(URL, TRUSTED_URL_PREFIX, max_bytes=1000) == BODY
    assert len(network.requests) == HTTP_MAX_REDIRECTS + 1


def test_one_redirection_too_many_is_refused(network):
    network.answers = [redirection(URL)] * (HTTP_MAX_REDIRECTS + 1)

    with pytest.raises(PageRefusedError, match="redirections"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert len(network.requests) == HTTP_MAX_REDIRECTS + 1


def test_a_redirection_without_location_is_a_status_error(network):
    network.answers = [answer(302)]

    with pytest.raises(SourceStatusError) as failure:
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert failure.value.status == 302
    assert len(network.requests) == 1


def test_the_body_of_a_redirection_is_never_read(network):
    stream = CountedStream([b"<html>moved</html>"])
    network.answers = [
        httpx2.Response(302, headers={"Location": "/feed?page=2"}, stream=stream)
    ]

    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert stream.pieces_read == 0


# === The request ===


def test_the_body_is_returned_unchanged(network):
    assert download(URL, TRUSTED_URL_PREFIX, max_bytes=1000) == BODY


def test_the_request_names_k_b_and_has_a_timeout(network):
    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    request = network.requests[0]
    assert str(request.url) == URL
    assert request.method == "GET"
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.extensions["timeout"] == {
        "connect": HTTP_TIMEOUT_SECONDS,
        "read": HTTP_TIMEOUT_SECONDS,
        "write": HTTP_TIMEOUT_SECONDS,
        "pool": HTTP_TIMEOUT_SECONDS,
    }


def test_the_given_headers_are_sent(network):
    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000, headers={"Accept": "text/csv"})

    assert network.requests[0].headers["Accept"] == "text/csv"


def test_the_user_agent_of_k_b_is_never_replaced_by_a_given_header(network):
    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000, headers={"User-Agent": "other"})

    assert network.requests[0].headers["User-Agent"] == USER_AGENT


def test_an_unredirected_header_is_sent_with_the_first_request(network):
    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000, unredirected_headers=TOKEN_HEADER)

    assert network.requests[0].headers["Authorization"] == "Bearer test-token"


@pytest.mark.parametrize(
    ("url", "trusted_url_prefix"),
    [
        (URL, "https://"),
        ("http://example.org/feed", "http://example.org/"),
        (URL, "https://example.org"),
        (URL, "https://example.com/"),
        ("https://user@example.org/feed", "https://user@example.org/"),
        ("https://@/feed", "https://@/"),
        ("https://example.org/feed/../login", "https://example.org/feed/"),
    ],
    ids=[
        "prefix-without-host",
        "prefix-not-https",
        "prefix-without-path",
        "url-outside-prefix",
        "prefix-with-user-info",
        "prefix-with-empty-host",
        "url-outside-prefix-once-normalized",
    ],
)
def test_a_badly_set_prefix_is_refused_before_any_request(
    network, url, trusted_url_prefix
):
    with pytest.raises(ValueError, match="trusted"):
        download(url, trusted_url_prefix, max_bytes=1000)

    assert network.requests == []


# === The body ===


def test_a_body_larger_than_the_limit_is_refused(network):
    with pytest.raises(PageRefusedError, match="larger than"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=len(BODY) - 1)


def test_a_body_exactly_at_the_limit_is_returned(network):
    assert download(URL, TRUSTED_URL_PREFIX, max_bytes=len(BODY)) == BODY


def test_a_body_announced_larger_than_the_limit_is_refused_without_reading_it(
    network,
):
    stream = CountedStream([BODY])
    network.answers = [
        httpx2.Response(200, headers={"Content-Length": "1001"}, stream=stream)
    ]

    with pytest.raises(PageRefusedError, match="larger than"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert stream.pieces_read == 0


def test_a_compressed_body_too_large_once_decoded_is_refused_before_its_end(network):
    compressed = gzip.compress(bytes(1_000_000))
    pieces = [compressed[start : start + 16] for start in range(0, len(compressed), 16)]
    stream = CountedStream(pieces)
    network.answers = [
        httpx2.Response(200, headers={"Content-Encoding": "gzip"}, stream=stream)
    ]

    # The compressed body fits; decoded, it does not.
    max_bytes = 2 * len(compressed)
    with pytest.raises(PageRefusedError, match="larger than"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=max_bytes)

    assert stream.pieces_read < len(pieces)


def test_a_body_that_cannot_be_decoded_is_refused(network):
    network.answers = [
        httpx2.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=CountedStream([b"not gzip"]),
        )
    ]

    with pytest.raises(PageRefusedError, match="body not decodable"):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)


# === Status errors and retries ===


def test_a_status_error_is_raised_to_the_caller(network):
    network.answers = [answer(304)]

    with pytest.raises(SourceStatusError) as failure:
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert failure.value.status == 304
    assert str(failure.value) == "HTTP 304 Not Modified"


def test_a_status_without_reason_is_named_by_its_number_alone(network):
    network.answers = [answer(499)]

    with pytest.raises(SourceStatusError) as failure:
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert str(failure.value) == "HTTP 499"


def test_the_headers_of_a_status_error_are_read_whatever_their_case(network):
    network.answers = [answer(404, retry_after="3600")]

    with pytest.raises(SourceStatusError) as failure:
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert failure.value.headers["Retry-After"] == "3600"


def test_a_429_is_retried_once_after_its_retry_after(network, no_wait_before_a_retry):
    network.answers = [answer(429, Retry_After="12")]

    assert download(URL, TRUSTED_URL_PREFIX, max_bytes=1000) == BODY
    assert len(network.requests) == 2
    assert no_wait_before_a_retry == [12]


def test_a_429_without_retry_after_waits_the_given_rate_limited_wait(
    network, no_wait_before_a_retry
):
    network.answers = [answer(429)]

    download(URL, TRUSTED_URL_PREFIX, max_bytes=1000, rate_limited_wait_seconds=60)

    assert no_wait_before_a_retry == [60]


@pytest.mark.parametrize(
    "error",
    [
        httpx2.ConnectError("[Errno 61] Connection refused"),
        httpx2.ReadError("[Errno 54] Connection reset by peer"),
    ],
    ids=["refused", "dropped"],
)
def test_a_failed_connection_is_retried(network, no_wait_before_a_retry, error):
    network.answers = [error]

    assert download(URL, TRUSTED_URL_PREFIX, max_bytes=1000) == BODY
    assert no_wait_before_a_retry == [http_download.RETRY_WAIT_SECONDS]


def test_a_timeout_is_raised_without_a_retry(network, no_wait_before_a_retry):
    network.answers = [httpx2.ReadTimeout("timed out")]

    with pytest.raises(httpx2.TimeoutException):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert len(network.requests) == 1
    assert no_wait_before_a_retry == []


def test_a_second_failure_is_raised_without_a_third_request(
    network, no_wait_before_a_retry
):
    network.answers = [answer(503), answer(503)]

    with pytest.raises(SourceStatusError):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert len(network.requests) == 2
    assert no_wait_before_a_retry == [http_download.RETRY_WAIT_SECONDS]


def test_an_answer_not_retried_is_raised_at_once(network, no_wait_before_a_retry):
    network.answers = [answer(429, Retry_After="3600")]

    with pytest.raises(SourceStatusError):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert len(network.requests) == 1
    assert no_wait_before_a_retry == []


def test_a_rate_limit_with_no_request_left_is_raised_with_its_reset(network):
    network.answers = [
        answer(403, x_ratelimit_remaining="0", x_ratelimit_reset="1792944000")
    ]

    with pytest.raises(SourceStatusError) as failure:
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    assert failure.value.__notes__ == [
        "rate limit reached, no request left until 2026-10-25T16:00:00+00:00"
    ]


def test_the_retry_is_logged_without_the_query_of_the_url(network, caplog):
    network.answers = [answer(502)]

    with caplog.at_level(logging.WARNING):
        download(URL, TRUSTED_URL_PREFIX, max_bytes=1000)

    [record] = caplog.records
    assert record.getMessage() == (
        "GET 'https://example.org/feed' failed: 'HTTP 502 Bad Gateway'; one retry in 5 s"
    )
