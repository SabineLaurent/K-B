"""A fake Azure Blob Storage and a fake identity endpoint: the transport of the Azure SDK answers
from a handler of the test, never from the network."""

import http
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formatdate
from urllib.parse import parse_qs, quote, unquote, urlsplit
from xml.sax.saxutils import escape

import requests
import urllib3
from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import RequestsTransport
from requests.adapters import HTTPAdapter

from k_b.exchange.storage import open_container_client

# The name of a clip is its title (etl/sources/clipping.py), the file name Web Clipper gives it:
# spotted in a log, it would name what Sabine reads.
SPOTTED_BLOB_NAME = "A title of a clip spotted in the log 7Q3ZK.md"


def names_the_spotted_blob(text):
    """Whether text holds the name of the spotted blob, as written or as a URL writes it."""
    return SPOTTED_BLOB_NAME in text or quote(SPOTTED_BLOB_NAME) in text


TEST_ACCOUNT_URL = "https://stkbexchangetest.blob.core.windows.net"
TEST_CLIENT_ID = "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"
TEST_TOKEN = "token-of-the-test"  # noqa: S105 — a token of the tests, which grants nothing
# The endpoint and the header of the identity of a container app (azure-identity reads them).
TEST_IDENTITY_ENDPOINT = "http://localhost:42356/msi/token"
TEST_IDENTITY_HEADER = "identity-header-of-the-test"
XML_HEADERS = {"Content-Type": "application/xml"}


class AnsweringAdapter(HTTPAdapter):
    """The adapter of requests under the transport of the SDK: each request is kept, then answered
    by handle with its status, its headers and its body."""

    def __init__(self, handle):
        super().__init__()
        self.handle = handle
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        status, headers, body = self.handle(request)
        # A body is bytes, or a stream that gives its own Content-Length in headers.
        is_bytes = isinstance(body, bytes)
        raw = urllib3.HTTPResponse(
            body=io.BytesIO(body) if is_bytes else body,
            headers={
                **({"Content-Length": str(len(body))} if is_bytes else {}),
                **headers,
            },
            status=status,
            reason=http.HTTPStatus(status).phrase,
            preload_content=False,
        )
        return self.build_response(request, raw)


class FakeTransport(RequestsTransport):
    """The transport of the SDK on a fake adapter; its retries do not wait."""

    def __init__(self, handle):
        self.adapter = AnsweringAdapter(handle)
        session = requests.Session()
        session.mount("https://", self.adapter)
        session.mount("http://", self.adapter)
        super().__init__(session=session, session_owner=False)

    def sleep(self, duration):
        pass


def answer_listing(*names):
    """The answer of List Blobs, its format as the REST API documents it
    (learn.microsoft.com/en-us/rest/api/storageservices/list-blobs, "Response body")."""
    blobs = "".join(f"<Blob><Name>{name}</Name></Blob>" for name in names)
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<EnumerationResults ServiceEndpoint="{TEST_ACCOUNT_URL}/" ContainerName="smoke-test">'
        f"<MaxResults>100</MaxResults><Blobs>{blobs}</Blobs><NextMarker />"
        "</EnumerationResults>"
    )

    def handle(request):
        return 200, XML_HEADERS, body.encode()

    return handle


def answer_error(status, code, message):
    """An error of Blob Storage: its code in x-ms-error-code and in the body, as the REST API
    documents it (learn.microsoft.com/en-us/rest/api/storageservices/status-and-error-codes2)."""
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f"<Error><Code>{code}</Code><Message>{message}</Message></Error>"
    )

    def handle(request):
        return status, {**XML_HEADERS, "x-ms-error-code": code}, body.encode()

    return handle


# A 403 whose body names the blob: AuthenticationFailed gives the resource it refused.
answer_forbidden_naming_the_blob = answer_error(
    403,
    "AuthenticationFailed",
    "Server failed to authenticate the request.\n"
    f"AuthenticationErrorDetail: resource /stkbexchangetest/smoke-test/{SPOTTED_BLOB_NAME}",
)


def answer_token(request):
    """The identity endpoint of a container app, as azure-identity reads it (api-version
    2019-08-01)."""
    body = {
        "access_token": TEST_TOKEN,
        "expires_on": "4102444800",
        "resource": "https://storage.azure.com",
        "token_type": "Bearer",
    }
    return 200, {"Content-Type": "application/json"}, json.dumps(body).encode()


# A forged line in the text of an answer: written unescaped, it would pass for a line of kb.
FORGED_LOG_LINE = "2026-11-06T00:00:00Z ERROR k_b.cli: a line forged by an answer"


def answer_identity_refusal(request):
    """The identity endpoint refusing a client id it does not know: an OAuth error, in JSON, whose
    text holds a forged line."""
    body = {
        "error": "invalid_request",
        "error_description": f"Identity not found\n{FORGED_LOG_LINE}",
    }
    return 400, {"Content-Type": "application/json"}, json.dumps(body).encode()


def answer_identity_with(status, content_type, body):
    """The identity endpoint answering a body that is not a token."""

    def handle(request):
        return status, {"Content-Type": content_type}, body

    return handle


# The variables of a run online: those of the job (exchange/storage.py), and those
# ManagedIdentityCredential reads to choose its way to a token (azure/identity/_constants.py,
# EnvironmentVariables, azure-identity 1.27.0).
ONLINE_VARIABLES = (
    "KB_EXCHANGE_BLOB_URL",
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
    "AZURE_AUTHORITY_HOST",
    "AZURE_FEDERATED_TOKEN_FILE",
    "AZURE_POD_IDENTITY_AUTHORITY_HOST",
    "AZURE_KUBERNETES_TOKEN_PROXY",
    "AZURE_KUBERNETES_CA_FILE",
    "AZURE_KUBERNETES_CA_DATA",
    "AZURE_KUBERNETES_SNI_NAME",
    "IDENTITY_ENDPOINT",
    "IDENTITY_HEADER",
    "IDENTITY_SERVER_THUMBPRINT",
    "IMDS_ENDPOINT",
    "MSI_ENDPOINT",
    "MSI_SECRET",
)


def remove_online_variables(monkeypatch):
    """A terminal that exports a variable of a run online must not make the tests reach Azure, nor
    change the way of the credential to its token."""
    for variable in ONLINE_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def set_identity_endpoint(monkeypatch):
    """The variables azure-identity reads in a container app."""
    monkeypatch.setenv("IDENTITY_ENDPOINT", TEST_IDENTITY_ENDPOINT)
    monkeypatch.setenv("IDENTITY_HEADER", TEST_IDENTITY_HEADER)


class FakeCredential:
    """A credential that gives the token of the tests, without an identity endpoint."""

    def get_token(self, *scopes, **kwargs):
        return AccessToken(TEST_TOKEN, 4102444800)


@dataclass
class FakeBlob:
    """A blob of the fake storage: its content, its last modification, its etag and its encoding."""

    content: bytes
    last_modified: datetime
    etag: str = ""
    content_encoding: str | None = None

    def __post_init__(self):
        self.etag = (
            self.etag or f'"0x{abs(hash((self.content, self.last_modified))):X}"'
        )


def write_name_element(name):
    """The Name element of a blob: escaped, or percent-encoded when it holds a character XML 1.0
    cannot carry (a control character but tab, line feed and carriage return)."""
    if any(ord(character) < 0x20 and character not in "\t\n\r" for character in name):
        return f'<Name Encoded="true">{quote(name, safe="")}</Name>'
    return f"<Name>{escape(name)}</Name>"


def format_http_date(moment):
    """A date as HTTP writes it (RFC 1123), the format of Last-Modified."""
    return formatdate(moment.timestamp(), usegmt=True)


# The code the storage gives with the status of a Get Blob, when the test gives the status only.
CODE_OF_NEXT_GET = {404: "BlobNotFound", 412: "ConditionNotMet"}
# The most names a page of List Blobs holds, and the page without maxresults (List Blobs, "URI
# parameters").
LISTING_PAGE_SIZE = 5000
# The marker the fake gives: the position of the next name; the storage's own is opaque.
MARKER_PREFIX = "position-"


class FakeContainer:
    """A container of the fake storage: List Blobs, Get Blob and Put Blob, answered as the REST API
    documents them (learn.microsoft.com/en-us/rest/api/storageservices/blob-service-rest-api);
    each request is kept. A name is listed escaped, or percent-encoded (Encoded="true") when XML
    cannot carry it, as the storage gives it; a listing reads prefix, maxresults and marker, and
    gives a NextMarker while names are left."""

    def __init__(self, name, blobs=None):
        self.name = name
        self.blobs = dict(blobs or {})
        self.requests = []
        # The blobs whose next Get answers this status instead (a blob changed or removed between
        # the listing and its download), or this status and this code (a container removed).
        self.status_of_next_get = {}
        # The most names of a page below maxresults: the storage may cut a page short, even to no
        # name, and give a NextMarker (List Blobs, "Remarks").
        self.listing_page_size = None

    def handle(self, request):
        self.requests.append(request)
        url = urlsplit(request.url)
        query = parse_qs(url.query)
        if query.get("comp") == ["list"]:
            return self.answer_listing(query)
        blob_name = unquote(url.path.removeprefix(f"/{self.name}/"))
        if request.method == "GET":
            return self.answer_get(blob_name, request.headers)
        if request.method == "PUT":
            return self.answer_put(blob_name, request.headers, request.body)
        raise AssertionError(f"request not simulated: {request.method} {request.url}")

    def answer_listing(self, query):
        prefix = query.get("prefix", [""])[0]
        page_size = min(
            int(query.get("maxresults", [LISTING_PAGE_SIZE])[0]), LISTING_PAGE_SIZE
        )
        if self.listing_page_size is not None:
            page_size = min(page_size, self.listing_page_size)
        start = int(
            query.get("marker", [MARKER_PREFIX + "0"])[0].removeprefix(MARKER_PREFIX)
        )
        names = [name for name in sorted(self.blobs) if name.startswith(prefix)]
        page = names[start : start + page_size]
        next_start = start + len(page)
        next_marker = f"{MARKER_PREFIX}{next_start}" if next_start < len(names) else ""
        blobs = "".join(
            f"<Blob>{write_name_element(name)}<Properties>"
            f"<Last-Modified>{format_http_date(blob.last_modified)}</Last-Modified>"
            f"<Etag>{escape(blob.etag)}</Etag>"
            f"<Content-Length>{len(blob.content)}</Content-Length>"
            + (
                f"<Content-Encoding>{blob.content_encoding}</Content-Encoding>"
                if blob.content_encoding
                else ""
            )
            + "<BlobType>BlockBlob</BlobType></Properties></Blob>"
            for name, blob in ((name, self.blobs[name]) for name in page)
        )
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<EnumerationResults ServiceEndpoint="{TEST_ACCOUNT_URL}/"'
            f' ContainerName="{self.name}"><Blobs>{blobs}</Blobs>'
            f"<NextMarker>{next_marker}</NextMarker></EnumerationResults>"
        )
        return 200, XML_HEADERS, body.encode()

    def listings(self):
        """The List Blobs requests, in order."""
        return [request for request in self.requests if "comp=list" in request.url]

    def answer_get(self, blob_name, headers):
        answer = self.status_of_next_get.pop(blob_name, None)
        if answer is not None:
            status, code = answer if isinstance(answer, tuple) else (answer, None)
            code = code or CODE_OF_NEXT_GET.get(
                status, http.HTTPStatus(status).phrase.replace(" ", "")
            )
            return answer_error(status, code, "Simulated.")(None)
        blob = self.blobs.get(blob_name)
        if blob is None:
            return answer_error(
                404, "BlobNotFound", "The specified blob does not exist."
            )(None)
        if headers.get("If-Match") not in (None, blob.etag):
            return answer_error(
                412,
                "ConditionNotMet",
                "The condition specified using HTTP conditional header(s) is not met.",
            )(None)
        content = blob.content
        response_headers = {
            "Last-Modified": format_http_date(blob.last_modified),
            "ETag": blob.etag,
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": "application/octet-stream",
        }
        if blob.content_encoding:
            response_headers["Content-Encoding"] = blob.content_encoding
        requested_range = headers.get("x-ms-range") or headers.get("Range")
        if requested_range is None:
            return 200, response_headers, content
        if not content:
            return answer_error(
                416,
                "InvalidRange",
                "The range specified is invalid for the current size.",
            )(None)
        start, end = (
            int(bound) for bound in requested_range.removeprefix("bytes=").split("-")
        )
        end = min(end, len(content) - 1)
        response_headers["Content-Range"] = f"bytes {start}-{end}/{len(content)}"
        return 206, response_headers, content[start : end + 1]

    def answer_put(self, blob_name, headers, body):
        if headers.get("If-None-Match") == "*" and blob_name in self.blobs:
            return answer_error(
                409, "BlobAlreadyExists", "The specified blob already exists."
            )(None)
        content = body if isinstance(body, bytes) else b"".join(body or [])
        blob = FakeBlob(content, datetime.now(UTC).replace(microsecond=0))
        self.blobs[blob_name] = blob
        return (
            201,
            {"ETag": blob.etag, "Last-Modified": format_http_date(blob.last_modified)},
            b"",
        )

    def downloaded_names(self):
        """The names of the blobs asked by Get Blob, in order."""
        return [
            unquote(urlsplit(request.url).path.removeprefix(f"/{self.name}/"))
            for request in self.requests
            if request.method == "GET" and "comp=list" not in request.url
        ]

    def uploads(self):
        """The Put Blob requests, in order."""
        return [request for request in self.requests if request.method == "PUT"]


def open_fake_container_client(container):
    """A client of the fake container, as open_container_client builds it, with a token of the
    tests."""
    return open_container_client(
        TEST_ACCOUNT_URL,
        container.name,
        FakeCredential(),
        FakeTransport(container.handle),
    )
