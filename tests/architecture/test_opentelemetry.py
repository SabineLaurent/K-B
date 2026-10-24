"""OpenTelemetry and the HTTP client of its exporter are imported by two modules of the AI API
only (decision of Sabine of 2026-10-24, plan of #162): the app, the router and the commands see
ModelMetrics alone, so that the rules of the export (no OTEL_* variable, a closed resource, a
session blind to the environment) are in one place."""

import ast

import pytest
from module_imports import PACKAGE_DIR

ALLOWED_MODULES_BY_LIBRARY = {
    "opentelemetry": {
        "ai_api/connectors/metrics_export.py",
        "ai_api/metric_instruments.py",
    },
    "requests": {"ai_api/connectors/metrics_export.py"},
}


def list_imported_top_level_names(code: str) -> set[str]:
    """The top-level names of the absolute imports of code (`opentelemetry` for
    `from opentelemetry.sdk.metrics import MeterProvider`)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("library", sorted(ALLOWED_MODULES_BY_LIBRARY))
def test_a_library_of_the_export_is_imported_by_its_modules_only(library):
    importers = {
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in PACKAGE_DIR.rglob("*.py")
        if library in list_imported_top_level_names(path.read_text())
    }

    assert importers == ALLOWED_MODULES_BY_LIBRARY[library]


@pytest.mark.parametrize(
    ("code", "names"),
    [
        ("import opentelemetry.metrics", {"opentelemetry"}),
        ("from opentelemetry.sdk.metrics import MeterProvider", {"opentelemetry"}),
        ("import requests as http", {"requests"}),
        ("from . import metrics", set()),
        ("from k_b.ai_api.metric_instruments import ModelMetrics", {"k_b"}),
    ],
)
def test_the_reader_of_imports_gives_the_top_level_names(code, names):
    assert list_imported_top_level_names(code) == names
