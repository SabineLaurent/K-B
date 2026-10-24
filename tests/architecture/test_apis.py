"""What the data API and the AI API may import (conventions.md, rule 5); under k_b.ai_api, read
at three levels, a module imports only the layers below its own."""

import importlib
from pathlib import Path

import pytest
from module_imports import (
    PACKAGE_DIR,
    find_package,
    is_within,
    list_imported_modules,
    list_python_files,
    parse_imported_modules,
    reaches,
)

# The data API reads the base: never the pipeline, the writers nor their door (conventions.md,
# rule 5).
DATA_API_ALLOWED_MODULES = {"data_api", "database", "items", "core"}
DATA_API_FORBIDDEN_MODULES = {"database.writers", "database.writing"}


def list_forbidden_imports_of_the_data_api(imported: set[str]) -> set[str]:
    """The names a module of data_api may not import, read by reaches: `database.reading` is
    allowed, `database.writers` and the package `database` refused."""
    return {
        name
        for name in imported
        if not is_within(name, DATA_API_ALLOWED_MODULES)
        or reaches(name, DATA_API_FORBIDDEN_MODULES)
    }


def test_data_api_imports_only_data_api_database_items_and_core():
    for path in list_python_files("data_api"):
        imported = list_imported_modules(path, find_package(path))
        assert list_forbidden_imports_of_the_data_api(imported) == set(), path


@pytest.mark.parametrize(
    ("code", "is_refused"),
    [
        ("from k_b.etl import load", True),
        ("from k_b.etl.sources.arxiv import ArxivSource", True),
        ("from k_b import cli", True),
        ("from k_b.database.writers import paper_writer", True),
        ("from k_b.database import writers", True),
        ("from k_b.database.writers.paper_writer import write", True),
        ("from k_b.database.writing import write_item", True),
        ("from k_b.database import writing", True),
        ("from k_b import database", True),
        ("from k_b.database import reading", False),
        ("from k_b.database.reading import read_items", False),
        ("from k_b.data_api.errors import ApiError", False),
    ],
)
def test_the_data_api_rule_refuses_etl_and_the_writers(code, is_refused):
    imported = parse_imported_modules(code, package="k_b.data_api")

    assert bool(list_forbidden_imports_of_the_data_api(imported)) is is_refused


# api_router.py gathers the routers; the app plugs in it alone (code.md, "Séparation des
# responsabilités"; #246), in both APIs.
@pytest.mark.parametrize("api", ["data_api", "ai_api"])
def test_the_app_of_an_api_imports_no_router(api):
    path = PACKAGE_DIR / api / "app.py"
    imported = list_imported_modules(path, find_package(path), depth=3)

    assert {name for name in imported if is_within(name, {f"{api}.routers"})} == set()


# Each router declares its prefix and its tags on its APIRouter, in both APIs: the tags group the
# routes in /docs and the OpenAPI (decision of Sabine of 2026-10-21, #156; skill fastapi,
# references/path-operations.md).
@pytest.mark.parametrize("api", ["data_api", "ai_api"])
def test_each_router_of_an_api_declares_its_prefix_and_its_tags(api):
    paths = [
        path
        for path in list_python_files(f"{api}.routers")
        if path.name != "__init__.py"
    ]

    assert paths
    for path in paths:
        router = importlib.import_module(f"k_b.{name_module(path)}").router
        assert router.prefix, path
        assert router.tags, path


# The AI API reads the watch through the data API, never the base (docs/fiches-veille.md, "Le
# parcours d'une demande"), and writes nothing that must outlive it (.claude/rules/poc.md, rule
# 7): neither database, its writers included, nor etl and its raw store.
AI_API_ALLOWED_MODULES = {"ai_api", "items", "core"}


def list_forbidden_imports_of_the_ai_api(imported: set[str]) -> set[str]:
    return {name for name in imported if not is_within(name, AI_API_ALLOWED_MODULES)}


def test_ai_api_imports_only_ai_api_items_and_core():
    for path in list_python_files("ai_api"):
        imported = list_imported_modules(path, find_package(path))
        assert list_forbidden_imports_of_the_ai_api(imported) == set(), path


@pytest.mark.parametrize(
    ("code", "is_refused"),
    [
        ("from k_b import database", True),
        ("from k_b.database.reading import read_items", True),
        ("from k_b.database.writers import paper_writer", True),
        ("from k_b.etl import raw_store", True),
        ("from k_b.etl.raw_store import write_file_atomically", True),
        ("from k_b import data_api", True),
        ("from k_b import cli", True),
        ("from k_b.core.config import LLM_CALL_TIMEOUT_SECONDS", False),
        ("from k_b.core.quoting import quote_value", False),
        ("from .llm_replay import ReplayTransport", False),
    ],
)
def test_the_ai_api_rule_refuses_the_base_the_pipeline_and_the_other_apis(
    code, is_refused
):
    imported = parse_imported_modules(code, package="k_b.ai_api")

    assert bool(list_forbidden_imports_of_the_ai_api(imported)) is is_refused


# Under k_b.ai_api, each module is in exactly one layer, from the bottom up (#242). A module
# imports only the layers below its own: two modules of one layer do not import each other.
AI_API_LAYERS = (
    {
        "ai_api.deadline",
        "ai_api.watch_items",
        "ai_api.settings",
        "ai_api.connectors.metrics_export",
    },
    {"ai_api.connectors.llm_replay"},
    {"ai_api.connectors.llm_settings", "ai_api.connectors.data_api_settings"},
    {"ai_api.connectors.llm_client", "ai_api.connectors.data_api_client"},
    {"ai_api.stages.classification", "ai_api.stages.writing"},
    {"ai_api.digests"},
    {
        "ai_api.errors",
        "ai_api.dependencies",
        "ai_api.schemas.digest_schema",
        "ai_api.metrics",
    },
    {"ai_api.metric_instruments"},
    {"ai_api.routers.digest_router"},
    {"ai_api.api_router"},
    {"ai_api.app"},
)


def name_module(path: Path) -> str:
    """The name below k_b of the module at path (`ai_api.connectors.llm_client`)."""
    return ".".join(path.relative_to(PACKAGE_DIR).with_suffix("").parts)


def list_upward_imports_of_the_ai_api(module: str, imported: set[str]) -> set[str]:
    """The names a module of ai_api may not import: those that reach its layer or a layer above."""
    layer = next(
        (i for i, modules in enumerate(AI_API_LAYERS) if module in modules), None
    )
    assert layer is not None, f"{module} is in no layer of AI_API_LAYERS"
    own_layer_and_above = set().union(*AI_API_LAYERS[layer:])
    return {name for name in imported if reaches(name, own_layer_and_above)}


def test_every_module_of_ai_api_is_in_exactly_one_layer():
    modules = {
        name_module(path)
        for path in list_python_files("ai_api")
        if path.name != "__init__.py"
    }

    assert modules == set().union(*AI_API_LAYERS)
    assert sum(len(layer) for layer in AI_API_LAYERS) == len(modules)


def test_a_module_of_ai_api_imports_only_the_layers_below_its_own():
    for path in list_python_files("ai_api"):
        if path.name == "__init__.py":
            continue
        imported = list_imported_modules(path, find_package(path), depth=3)
        assert (
            list_upward_imports_of_the_ai_api(name_module(path), imported) == set()
        ), path


@pytest.mark.parametrize(
    ("module", "code", "is_refused"),
    [
        (
            "ai_api.digests",
            "from k_b.ai_api.stages.writing import write_subject",
            False,
        ),
        ("ai_api.digests", "from k_b import ai_api", True),
        ("ai_api.stages.writing", "from k_b.ai_api import connectors", False),
        ("ai_api.stages.writing", "from k_b.ai_api import stages", True),
        ("ai_api.stages.classification", "from ..digests import build_digests", True),
        ("ai_api.connectors.llm_client", "from .. import deadline", False),
        ("ai_api.connectors.llm_client", "from k_b.ai_api import connectors", True),
        ("ai_api.connectors.llm_client", "from ..stages import writing", True),
        ("ai_api.connectors.llm_settings", "from . import llm_replay", False),
        ("ai_api.connectors.llm_settings", "from .llm_client import call_model", True),
        ("ai_api.connectors.llm_replay", "from .llm_settings import LlmSettings", True),
        ("ai_api.deadline", "from k_b.core.config import LLM_REPLAY_BASE_URL", False),
        ("ai_api.deadline", "from k_b.ai_api.watch_items import WatchItem", True),
    ],
)
def test_the_rule_of_ai_api_refuses_its_layer_and_the_layers_above(
    module, code, is_refused
):
    package = "k_b." + module.rpartition(".")[0]
    imported = parse_imported_modules(code, package=package, depth=3)

    assert bool(list_upward_imports_of_the_ai_api(module, imported)) is is_refused
