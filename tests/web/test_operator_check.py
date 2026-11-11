"""Every request but /health reaches the site only with the object id of its operator, in the header
Azure Container Apps sets once she is signed in (docs/site-web.md, "Accès")."""

import logging

import pytest
from site_client import OPERATOR_HEADER, OPERATOR_HEADERS, OPERATOR_ID, make_client

ANOTHER_ID = "11111111-2222-4333-8444-555555555555"


@pytest.fixture
def client():
    return make_client()


def test_a_request_without_the_header_is_refused(client):
    response = client.get("/")

    assert response.status_code == 403
    assert "Accès réservé" in response.text
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "value",
    [
        ANOTHER_ID,
        "",
        f" {OPERATOR_ID}",
        f"{{{OPERATOR_ID}}}",
        f"urn:uuid:{OPERATOR_ID}",
        OPERATOR_ID.replace("-", ""),
        f"{OPERATOR_ID[:8]}{OPERATOR_ID[9:13]}-{OPERATOR_ID[13:]}",
    ],
)
def test_a_header_of_another_account_or_malformed_is_refused(client, value):
    assert client.get("/", headers={OPERATOR_HEADER: value}).status_code == 403


def test_a_header_given_twice_is_refused(client):
    headers = [(OPERATOR_HEADER, OPERATOR_ID), (OPERATOR_HEADER, OPERATOR_ID)]

    assert client.get("/", headers=headers).status_code == 403


@pytest.mark.parametrize("value", [OPERATOR_ID, OPERATOR_ID.upper()])
def test_the_object_id_of_the_operator_is_let_through(client, value):
    assert client.get("/", headers={OPERATOR_HEADER: value}).status_code == 200


def test_health_answers_without_the_header(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/static/site.css", "/no-such-page"])
def test_the_stylesheet_and_an_unknown_route_are_checked_too(client, path):
    assert client.get(path).status_code == 403
    assert client.get(path, headers=OPERATOR_HEADERS).status_code != 403


@pytest.mark.parametrize(
    ("headers", "refusal"),
    [
        ({}, "header_absent"),
        (
            [(OPERATOR_HEADER, ANOTHER_ID), (OPERATOR_HEADER, ANOTHER_ID)],
            "header_repeated",
        ),
        ({OPERATOR_HEADER: f"{{{ANOTHER_ID}}}"}, "header_malformed"),
        ({OPERATOR_HEADER: ANOTHER_ID}, "header_other"),
    ],
)
def test_a_refusal_is_logged_by_its_state_never_with_the_value(
    client, caplog, headers, refusal
):
    with caplog.at_level(logging.INFO, logger="k_b"):
        response = client.get("/", headers=headers)

    lines = [record.getMessage() for record in caplog.records]
    assert (
        f"operator_refused: {refusal} request_id={response.headers['X-Request-ID']}"
        in lines
    )
    assert not any(ANOTHER_ID in line for line in lines)


def test_the_refusal_offers_to_sign_out(client):
    assert 'href="/.auth/logout"' in client.get("/").text


def test_without_the_check_a_page_needs_no_header_and_offers_no_sign_out():
    response = make_client(operator_id=None).get("/")

    assert response.status_code == 200
    assert "/.auth/logout" not in response.text


def test_with_the_check_a_page_offers_to_sign_out():
    assert (
        'href="/.auth/logout"' in make_client().get("/", headers=OPERATOR_HEADERS).text
    )


@pytest.mark.parametrize("operator_id", [OPERATOR_ID, ANOTHER_ID])
def test_no_identity_header_reaches_the_log_or_a_page(client, caplog, operator_id):
    """Azure Container Apps also sends the name the person signed in with, a personal datum."""
    name = "operator@example.org"
    headers = {OPERATOR_HEADER: operator_id, "X-MS-CLIENT-PRINCIPAL-NAME": name}
    with caplog.at_level(logging.INFO, logger="k_b"):
        responses = [
            client.get(path, headers=headers) for path in ("/", "/no-such-page")
        ]

    assert not any(name in response.text for response in responses)
    assert not any(
        name in record.getMessage() or operator_id in record.getMessage()
        for record in caplog.records
    )
