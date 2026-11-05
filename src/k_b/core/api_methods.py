"""The methods an API answers: those its routes declare, and no other (OWASP API8:2023)."""

from fastapi import FastAPI
from starlette.routing import Route


def remove_implicit_head(app: FastAPI) -> None:
    """Remove HEAD from each route of Starlette of the app that declares GET, to which Starlette
    adds it (starlette/routing.py, 1.8): a HEAD request then gets 405. The routes of an included
    router are not walked: a route of FastAPI never adds HEAD."""
    for route in app.routes:
        if isinstance(route, Route) and route.methods and "GET" in route.methods:
            route.methods.discard("HEAD")
