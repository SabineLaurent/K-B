"""The pages of the site: the home page, the sources and the accessibility (docs/site-web.md,
"Pages")."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from k_b.web.rendering import render_page

HOME_PATH = "/"
SOURCES_PATH = "/sources"
ACCESSIBILITY_PATH = "/accessibilite"

router = APIRouter(default_response_class=HTMLResponse)


@router.get(HOME_PATH)
def show_home(request: Request) -> Response:
    """The home page; the watch feed takes its place (#563)."""
    return render_page(request, "home.html", current_path=HOME_PATH)


@router.get(SOURCES_PATH)
def show_sources(request: Request) -> Response:
    return render_page(request, "sources.html", current_path=SOURCES_PATH)


@router.get(ACCESSIBILITY_PATH)
def show_accessibility(request: Request) -> Response:
    return render_page(request, "accessibilite.html", current_path=ACCESSIBILITY_PATH)
