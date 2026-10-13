"""The dependencies go one way, read at two levels (conventions.md, rule 5).

Under k_b: core and items are the common vocabulary, database reads and writes the base, etl runs
the pipeline, cli composes. Under k_b.etl: the composition (source_kinds) → the sources → the
modules of the pipeline.
"""

import ast
import pkgutil
from pathlib import Path

import pytest

import k_b

PACKAGE_DIR = Path(k_b.__file__).parent
TOP_LEVEL_MODULES = {"cli", "items", "core", "database", "etl"}
# Under k_b.etl, each module is in exactly one of the three.
ETL_COMPOSITION_MODULES = {"etl.source_kinds"}
ETL_SOURCES_PACKAGE = "etl.sources"
ETL_PIPELINE_MODULES = {
    "etl.extract",
    "etl.transform",
    "etl.load",
    "etl.normalize",
    "etl.raw_store",
    "etl.source_contract",
    "etl.http_download",
    "etl.user_agent",
}
COMPOSITION_MODULES = {"cli"} | ETL_COMPOSITION_MODULES


def list_imported_modules(path: Path, package: str) -> set[str]:
    """The k_b modules imported by the module at path, of the given package."""
    return parse_imported_modules(path.read_text(), package)


def parse_imported_modules(code: str, package: str = "k_b") -> set[str]:
    """The k_b modules imported by `import k_b.x`, `from k_b import x`, `from k_b.x import y`,
    and their relative forms (`from . import x`, `from .x import y`, `from .. import x`),
    resolved against the package of the module.

    Each name is given below k_b, cut at two levels: `etl.sources` for any module of
    k_b.etl.sources, `core.config` for k_b.core.config. A name imported from a module counts as
    its second level (`items.Item`): a rule compares by prefix (see is_within).

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
            ".".join(name.split(".")[1:3]) for name in names if name.startswith("k_b.")
        }
    return imported


def is_within(name: str, modules: set[str]) -> bool:
    """Whether name is one of the modules, or a part of one of them."""
    return any(name == module or name.startswith(f"{module}.") for module in modules)


def list_python_files(module: str) -> list[Path]:
    """The Python files of a k_b module (`items`) or package (`etl.sources`)."""
    path = PACKAGE_DIR.joinpath(*module.split("."))
    if path.with_suffix(".py").exists():
        return [path.with_suffix(".py")]
    paths = sorted(path.glob("*.py"))
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


def test_items_imports_neither_the_sources_nor_the_composition():
    forbidden = {ETL_SOURCES_PACKAGE} | COMPOSITION_MODULES
    for path in list_python_files("items"):
        imported = list_imported_modules(path, find_package(path))
        assert {name for name in imported if is_within(name, forbidden)} == set(), path


def test_no_module_of_the_pipeline_imports_the_sources_or_the_composition():
    forbidden = {ETL_SOURCES_PACKAGE} | COMPOSITION_MODULES
    for module in sorted(ETL_PIPELINE_MODULES):
        for path in list_python_files(module):
            imported = list_imported_modules(path, find_package(path))
            assert {name for name in imported if is_within(name, forbidden)} == set(), (
                path
            )


def test_no_module_of_the_sources_imports_the_composition():
    for path in list_python_files(ETL_SOURCES_PACKAGE):
        imported = list_imported_modules(path, find_package(path))
        assert {
            name for name in imported if is_within(name, COMPOSITION_MODULES)
        } == set(), path
