"""The HEAD that Starlette adds to a GET route, removed (src/k_b/core/api_methods.py)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from k_b.core.api_methods import remove_implicit_head


def answer_ok(request):
    return PlainTextResponse("ok")


def test_a_route_declaring_head_only_keeps_it_and_refuses_any_other_method():
    """Emptied, its methods would let any method through (starlette/routing.py, 1.8)."""
    app = FastAPI()
    app.add_route("/head-only", answer_ok, methods=["HEAD"])

    remove_implicit_head(app)
    client = TestClient(app)

    assert client.head("/head-only").status_code == 200
    assert client.post("/head-only").status_code == 405
