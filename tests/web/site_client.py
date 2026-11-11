"""The site in a TestClient, and the header Azure Container Apps sets once its operator is signed in."""

from fastapi.testclient import TestClient

from k_b.web.app import create_app

# An object id of the form Microsoft Entra gives, made for the tests.
OPERATOR_ID = "0f1e2d3c-4b5a-4968-8776-a5b4c3d2e1f0"
OPERATOR_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
OPERATOR_HEADERS = {OPERATOR_HEADER: OPERATOR_ID}
# The pages of the site, each with the header that lets it through.
PAGE_PATHS = ("/", "/sources", "/accessibilite")


def make_client(operator_id: str | None = OPERATOR_ID) -> TestClient:
    """A client of the site; base_url localhost, a host the site answers by default."""
    return TestClient(
        create_app(operator_id=operator_id),
        base_url="http://localhost",
        raise_server_exceptions=False,
    )
