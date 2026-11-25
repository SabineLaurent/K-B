"""The templates of the site, read from the package: every value escaped, whatever the name of the
template, and an undefined one refused (docs/site-web.md, "Gabarits")."""

from collections.abc import Mapping
from typing import Any

from fastapi import Request, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, PackageLoader, StrictUndefined


def add_layout_context(request: Request) -> dict[str, Any]:
    """What the layout of every page reads: whether the operator is checked, which shows the link to
    sign out of Microsoft Entra, and the version deployed, which its footer gives."""
    return {
        "is_operator_checked": request.app.state.operator_id is not None,
        "version": request.app.state.version,
    }


# autoescape=True rather than the select_autoescape() of Starlette, which escapes .html, .htm and
# .xml only (starlette/templating.py, 1.8). StrictUndefined: a value missing fails the page, never
# shows it empty.
templates = Jinja2Templates(
    env=Environment(
        loader=PackageLoader("k_b.web", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
    ),
    context_processors=[add_layout_context],
)


def render_page(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    current_path: str | None = None,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """The page of the template name; the link of current_path, if the navigation holds it, is
    marked as the current page."""
    return templates.TemplateResponse(
        request,
        name,
        {"current_path": current_path, **(context or {})},
        status_code=status_code,
        headers=headers,
    )
