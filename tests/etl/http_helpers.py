"""The fake network and the fake status errors the tests of the downloads share."""

import httpx2

from k_b.core import outbound
from k_b.etl.source_contract import SourceStatusError


def status_error(status, **headers):
    """A SourceStatusError; a header name is given with _ for -."""
    return SourceStatusError(status, answer_headers(headers))


def answer(status, body=b"", **headers):
    """An answer of the fake network; a header name is given with _ for -."""
    return httpx2.Response(status, headers=answer_headers(headers), content=body)


def answer_headers(headers):
    return httpx2.Headers(
        {name.replace("_", "-"): value for name, value in headers.items()}
    )


class CountedStream(httpx2.SyncByteStream):
    """A body sent piece by piece, without Content-Length; counts the pieces read."""

    def __init__(self, pieces):
        self.pieces = pieces
        self.pieces_read = 0

    def __iter__(self):
        for piece in self.pieces:
            self.pieces_read += 1
            yield piece


class FakeNetwork:
    """Stands for the network: records each request, answers the next queued answer (an
    httpx2.Response, or an exception raised), else 200 with body."""

    def __init__(self, body=b""):
        self.body = body
        self.answers = []
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        if not self.answers:
            return httpx2.Response(200, content=self.body)
        queued = self.answers.pop(0)
        if isinstance(queued, Exception):
            raise queued
        return queued

    def open_http_client(self, base_url, headers, timeout, transport):
        return outbound.open_http_client(
            base_url, headers, timeout, httpx2.MockTransport(self.handle)
        )

    def requested_urls(self):
        return [str(request.url) for request in self.requests]


def refuse_any_request(request):
    raise AssertionError(f"a test reached for the network: {request.url}")


def open_offline_http_client(base_url, headers, timeout, transport):
    """A client whose every request fails the test: a test without its fake network never
    leaves the machine."""
    return outbound.open_http_client(
        base_url, headers, timeout, httpx2.MockTransport(refuse_any_request)
    )
