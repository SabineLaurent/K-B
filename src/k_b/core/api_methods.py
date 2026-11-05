"""The methods an API answers: those its routes declare, and no other (OWASP API8:2023)."""

from fastapi import FastAPI
from starlette.routing import Route


def refuse_head_on_every_route(app: FastAPI) -> None:
    """Remove HEAD, which Starlette adds to each GET route (starlette/routing.py, 1.8), from the
    routes of the app: a HEAD request gets 405, as any method a route does not declare."""
    for route in app.routes:
        if isinstance(route, Route) and route.methods:
            route.methods.discard("HEAD")
