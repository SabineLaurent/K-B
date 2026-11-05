"""The methods an API answers: those its routes declare, and no other (OWASP API8:2023)."""

from fastapi import FastAPI
from starlette.routing import Route


def remove_implicit_head(app: FastAPI) -> None:
    """Remove the HEAD that Starlette adds to each GET route (starlette/routing.py, 1.8) from the
    routes of Starlette of the app: a HEAD request then gets 405. A route of FastAPI never adds
    it; the routes of an included router are not walked, and the tests of both APIs read them."""
    for route in app.routes:
        if isinstance(route, Route) and route.methods and "GET" in route.methods:
            route.methods.discard("HEAD")
