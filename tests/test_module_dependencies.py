"""The dependencies go one way, read at two levels, three under k_b.ai_api (conventions.md,
rule 5).

Under k_b: core and items are the common vocabulary, database reads and writes the base (its
writers under database/writers), etl runs the pipeline, data_api serves the base, ai_api calls the
model, cli and commands compose. Under k_b.etl: the composition (source_kinds, collected_sources) →
the sources → the modules of the pipeline. Under k_b.ai_api: digests → the stages → the clients →
the settings → outbound and llm_replay → deadline and watch_items; a module imports only the layers
below its own.
"""

import ast
import pkgutil
from pathlib import Path

import pytest

import k_b

PACKAGE_DIR = Path(k_b.__file__).parent
TOP_LEVEL_MODULES = {
    "cli",
    "commands",
    "items",
    "core",
    "database",
    "etl",
    "data_api",
    "ai_api",
}
# Under k_b.etl, each module is in exactly one of the three.
ETL_COMPOSITION_MODULES = {"etl.source_kinds", "etl.collected_sources"}
ETL_SOURCES_PACKAGE = "etl.sources"
ETL_PIPELINE_MODULES = {
    "etl.extract",
    "etl.transform",
    "etl.load",
    "etl.import_log",
    "etl.normalize",
    "etl.raw_store",
    "etl.source_contract",
    "etl.http_download",
    "etl.user_agent",
}
COMPOSITION_MODULES = {"cli", "commands"} | ETL_COMPOSITION_MODULES


def list_imported_modules(path: Path, package: str, depth: int = 2) -> set[str]:
    """The k_b modules imported by the module at path, of the given package, cut at depth
    levels (see parse_imported_modules)."""
    return parse_imported_modules(path.read_text(), package, depth)


def parse_imported_modules(code: str, package: str = "k_b", depth: int = 2) -> set[str]:
    """The k_b modules imported by `import k_b.x`, `from k_b import x`, `from k_b.x import y`,
    and their relative forms (`from . import x`, `from .x import y`, `from .. import x`),
    resolved against the package of the module.

    Each name is given below k_b, cut at two levels: `etl.sources` for any module of
    k_b.etl.sources, `core.config` for k_b.core.config. A name imported from a module counts as
    its second level (`items.Item`): a rule compares by prefix (see is_within). A depth of three
    tells the modules of a sub-folder apart (`ai_api.connectors.llm_client`).

    A dynamic import (importlib.import_module) is not seen: there is none in k_b.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # A relative import starts from the package, one level up per extra dot.
                package_parts = package.split(".")
                if node.level > len(package_parts):
                    raise ValueError(
                        f"relative import of level {node.level} above the package {package}"
                    )
                base = ".".join(package_parts[: len(package_parts) - node.level + 1])
                origin = f"{base}.{node.module}" if node.module else base
            else:
                origin = node.module or ""
            # The imported name may be a module of the package (`from k_b.etl import sources`).
            names = [f"{origin}.{alias.name}" for alias in node.names]
        else:
            continue
        imported |= {
            ".".join(name.split(".")[1 : 1 + depth])
            for name in names
            if name.startswith("k_b.")
        }
    return imported


def is_within(name: str, modules: set[str]) -> bool:
    """Whether name is one of the modules, or a part of one of them."""
    return any(name == module or name.startswith(f"{module}.") for module in modules)


def reaches(name: str, modules: set[str]) -> bool:
    """Whether importing name gives access to one of the modules: name is within one of them, or
    is a package that holds one (`etl` holds `etl.sources`)."""
    return is_within(name, modules) or any(
        module.startswith(f"{name}.") for module in modules
    )


def list_python_files(module: str) -> list[Path]:
    """The Python files of a k_b module (`items`) or package (`etl.sources`), those of its
    sub-folders included (`database/writers`)."""
    path = PACKAGE_DIR.joinpath(*module.split("."))
    if path.with_suffix(".py").exists():
        return [path.with_suffix(".py")]
    paths = sorted(path.rglob("*.py"))
    assert paths, f"no Python file in {path}"
    return paths


def find_package(path: Path) -> str:
    """The package of the relative imports of the module at path."""
    return ".".join(("k_b", *path.parent.relative_to(PACKAGE_DIR).parts))


@pytest.mark.parametrize(
    "code",
    [
        "import k_b.etl.sources.arxiv",
        "import k_b.etl.sources.arxiv as source",
        "from k_b.etl import sources",
        "from k_b.etl.sources import arxiv",
        "from k_b.etl.sources.arxiv import ArxivSource",
        "from .etl import sources",
        "from .etl.sources.arxiv import ArxivSource",
        "def f():\n    from k_b.etl.sources.arxiv import ArxivSource",
    ],
)
def test_every_form_of_import_is_seen(code):
    assert parse_imported_modules(code) == {"etl.sources"}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("from k_b import cli", {"cli"}),
        ("from k_b.items import Item", {"items.Item"}),
        ("from k_b.core.config import TrackedRepository", {"core.config"}),
    ],
)
def test_a_name_is_cut_at_two_levels(code, expected):
    assert parse_imported_modules(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("from k_b import ai_api", {"ai_api"}),
        ("from k_b.ai_api import connectors", {"ai_api.connectors"}),
        (
            "from k_b.ai_api.connectors.llm_client import call_model",
            {"ai_api.connectors.llm_client"},
        ),
        ("from k_b.ai_api.deadline import Deadline", {"ai_api.deadline.Deadline"}),
        ("from .llm_replay import ReplayTransport", {"ai_api.connectors.llm_replay"}),
    ],
)
def test_a_name_is_cut_at_three_levels_when_asked(code, expected):
    imported = parse_imported_modules(code, package="k_b.ai_api.connectors", depth=3)

    assert imported == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("from . import github_api", {"etl.sources"}),
        ("from .github_api import get_from_github_api", {"etl.sources"}),
        ("from .. import source_kinds", {"etl.source_kinds"}),
        ("from ... import cli", {"cli"}),
        ("from ...cli import main", {"cli.main"}),
    ],
)
def test_relative_imports_inside_the_sources_are_resolved(code, expected):
    assert parse_imported_modules(code, package="k_b.etl.sources") == expected


def test_a_relative_import_above_k_b_is_refused():
    with pytest.raises(ValueError, match="level 4 above the package k_b.etl.sources"):
        parse_imported_modules("from .... import cli", package="k_b.etl.sources")


@pytest.mark.parametrize(
    ("name", "expected"),
    [("core", True), ("core.config", True), ("corepart", False), ("items.Item", False)],
)
def test_a_name_is_within_a_module_by_prefix(name, expected):
    assert is_within(name, {"core"}) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("from k_b import etl", True),
        ("import k_b.etl", True),
        ("from k_b.etl import sources", True),
        ("from k_b.etl import transform", False),
    ],
)
def test_an_import_of_a_package_that_holds_a_forbidden_module_is_seen(code, expected):
    forbidden = {ETL_SOURCES_PACKAGE} | COMPOSITION_MODULES
    imported = parse_imported_modules(code)

    assert any(reaches(name, forbidden) for name in imported) is expected


def test_every_module_of_k_b_is_listed():
    modules = {module.name for module in pkgutil.iter_modules([str(PACKAGE_DIR)])}

    assert modules == TOP_LEVEL_MODULES


def test_every_module_of_etl_is_in_exactly_one_list():
    modules = {
        f"etl.{module.name}"
        for module in pkgutil.iter_modules([str(PACKAGE_DIR / "etl")])
    }
    lists = (ETL_COMPOSITION_MODULES, {ETL_SOURCES_PACKAGE}, ETL_PIPELINE_MODULES)

    assert modules == set().union(*lists)
    assert sum(len(modules_of_list) for modules_of_list in lists) == len(modules)


def test_the_modules_of_a_sub_folder_of_a_package_are_listed():
    paths = list_python_files("database")

    assert PACKAGE_DIR / "database" / "writers" / "paper_writer.py" in paths
    assert find_package(PACKAGE_DIR / "database" / "writers" / "paper_writer.py") == (
        "k_b.database.writers"
    )


def test_core_imports_nothing_of_k_b():
    for path in list_python_files("core"):
        imported = list_imported_modules(path, find_package(path))
        assert {name for name in imported if not is_within(name, {"core"})} == set(), (
            path
        )


def test_database_imports_only_items_and_core():
    allowed = {"database", "items", "core"}
    for path in list_python_files("database"):
        imported = list_imported_modules(path, find_package(path))
        assert {name for name in imported if not is_within(name, allowed)} == set(), (
            path
        )


# The data API reads the base: never the pipeline nor the writers (conventions.md, rule 5).
DATA_API_ALLOWED_MODULES = {"data_api", "database", "items", "core"}
DATA_API_FORBIDDEN_MODULES = {"database.writers"}


def list_forbidden_imports_of_the_data_api(imported: set[str]) -> set[str]:
    """The names a module of data_api may not import. A name is cut at two levels: `from k_b
    import database` gives `database`, allowed; `from k_b.database import writers` gives
    `database.writers`, refused."""
    return {
        name
        for name in imported
        if not is_within(name, DATA_API_ALLOWED_MODULES)
        or is_within(name, DATA_API_FORBIDDEN_MODULES)
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
        ("from k_b import database", False),
        ("from k_b.database.reading import read_items", False),
        ("from k_b.data_api.errors import ApiError", False),
    ],
)
def test_the_data_api_rule_refuses_etl_and_the_writers(code, is_refused):
    imported = parse_imported_modules(code, package="k_b.data_api")

    assert bool(list_forbidden_imports_of_the_data_api(imported)) is is_refused


# api_router.py gathers the routers; the app plugs in it alone, and routers/__init__.py stays
# empty (code.md, "Séparation des responsabilités"; #246).
def test_the_app_of_the_data_api_imports_no_router():
    path = PACKAGE_DIR / "data_api" / "app.py"
    imported = list_imported_modules(path, find_package(path), depth=3)

    assert {name for name in imported if is_within(name, {"data_api.routers"})} == set()


def test_the_package_of_the_routers_imports_nothing():
    path = PACKAGE_DIR / "data_api" / "routers" / "__init__.py"
    nodes = ast.walk(ast.parse(path.read_text()))

    assert not any(isinstance(node, ast.Import | ast.ImportFrom) for node in nodes)


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
    {"ai_api.deadline", "ai_api.watch_items"},
    {"ai_api.connectors.outbound", "ai_api.connectors.llm_replay"},
    {"ai_api.connectors.llm_settings", "ai_api.connectors.data_api_settings"},
    {"ai_api.connectors.llm_client", "ai_api.connectors.data_api_client"},
    {"ai_api.stages.classification", "ai_api.stages.writing"},
    {"ai_api.digests"},
)


def name_module(path: Path) -> str:
    """The name below k_b of the module at path (`ai_api.connectors.llm_client`)."""
    return ".".join(path.relative_to(PACKAGE_DIR).with_suffix("").parts)


def list_upward_imports_of_the_ai_api(module: str, imported: set[str]) -> set[str]:
    """The names a module of ai_api may not import: those that reach a module of its layer or
    of a layer above (`from k_b import ai_api` reaches them all)."""
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


def test_the_packages_of_ai_api_import_nothing_of_ai_api():
    for path in list_python_files("ai_api"):
        if path.name != "__init__.py":
            continue
        imported = list_imported_modules(path, find_package(path), depth=3)
        assert {name for name in imported if is_within(name, {"ai_api"})} == set(), path


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
        ("ai_api.connectors.outbound", "from .llm_replay import ReplayTransport", True),
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


# The command line is the top: commands/ does not import cli, which imports it; the composition of
# etl, which commands/ imports, imports neither (#247).
COMMAND_LINE_FORBIDDEN_MODULES = {"commands": {"cli"}} | {
    module: {"cli", "commands"} for module in ETL_COMPOSITION_MODULES
}


def test_neither_commands_nor_the_composition_of_etl_imports_the_command_line_above():
    for module, forbidden in sorted(COMMAND_LINE_FORBIDDEN_MODULES.items()):
        for path in list_python_files(module):
            imported = list_imported_modules(path, find_package(path))
            assert {name for name in imported if reaches(name, forbidden)} == set(), (
                path
            )


def test_items_imports_neither_the_sources_nor_the_composition():
    forbidden = {ETL_SOURCES_PACKAGE} | COMPOSITION_MODULES
    for path in list_python_files("items"):
        imported = list_imported_modules(path, find_package(path))
        assert {name for name in imported if reaches(name, forbidden)} == set(), path


def test_no_module_of_the_pipeline_imports_the_sources_or_the_composition():
    forbidden = {ETL_SOURCES_PACKAGE} | COMPOSITION_MODULES
    for module in sorted(ETL_PIPELINE_MODULES):
        for path in list_python_files(module):
            imported = list_imported_modules(path, find_package(path))
            assert {name for name in imported if reaches(name, forbidden)} == set(), (
                path
            )


def test_no_module_of_the_sources_imports_the_composition():
    for path in list_python_files(ETL_SOURCES_PACKAGE):
        imported = list_imported_modules(path, find_package(path))
        assert {
            name for name in imported if reaches(name, COMPOSITION_MODULES)
        } == set(), path
