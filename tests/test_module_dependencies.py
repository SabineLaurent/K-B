"""The dependencies go one way: composition → sources → generic modules (plan ETL)."""

import ast
import pkgutil
from pathlib import Path

import pytest

import k_b

PACKAGE_DIR = Path(k_b.__file__).parent
SOURCES_DIR = PACKAGE_DIR / "sources"
GENERIC_MODULES = {
    "items",
    "source",
    "collect",
    "raw_store",
    "raw_items",
    "merge",
    "import_items",
    "database",
    "http_download",
    "user_agent",
}
# The package k_b.sources: every source, and what only sources use.
SOURCES_PACKAGE = "sources"
COMPOSITION_MODULES = {"cli", "source_kinds"}


def list_imported_modules(path: Path, package: str) -> set[str]:
    """The k_b modules imported by the module at path, of the given package."""
    return parse_imported_modules(path.read_text(), package)


def parse_imported_modules(code: str, package: str = "k_b") -> set[str]:
    """The k_b modules imported by `import k_b.x`, `from k_b import x`, `from k_b.x import y`,
    and their relative forms (`from . import x`, `from .x import y`, `from .. import x`),
    resolved against the package of the module. A module of k_b.sources is seen as "sources".

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
            if origin == "k_b":
                names = [f"{origin}.{alias.name}" for alias in node.names]
            else:
                names = [origin]
        else:
            continue
        imported |= {name.split(".")[1] for name in names if name.startswith("k_b.")}
    return imported


@pytest.mark.parametrize(
    "code",
    [
        "import k_b.sources.arxiv",
        "import k_b.sources.arxiv as source",
        "from k_b import sources",
        "from k_b.sources import arxiv",
        "from k_b.sources.arxiv import ArxivSource",
        "from . import sources",
        "from .sources.arxiv import ArxivSource",
        "def f():\n    from k_b.sources.arxiv import ArxivSource",
    ],
)
def test_every_form_of_import_is_seen(code):
    assert parse_imported_modules(code) == {"sources"}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("from . import github_api", {"sources"}),
        ("from .github_api import get_from_github_api", {"sources"}),
        ("from .. import cli", {"cli"}),
        ("from ..cli import main", {"cli"}),
    ],
)
def test_relative_imports_inside_sources_are_resolved(code, expected):
    assert parse_imported_modules(code, package="k_b.sources") == expected


def test_a_relative_import_above_k_b_is_refused():
    with pytest.raises(ValueError, match="level 3 above the package k_b.sources"):
        parse_imported_modules("from ... import cli", package="k_b.sources")


def test_every_module_is_in_exactly_one_list():
    modules = {module.name for module in pkgutil.iter_modules([str(PACKAGE_DIR)])}
    lists = (GENERIC_MODULES, {SOURCES_PACKAGE}, COMPOSITION_MODULES)

    assert modules == set().union(*lists)
    assert sum(len(modules_of_list) for modules_of_list in lists) == len(modules)


def list_generic_modules() -> list[tuple[Path, str]]:
    """Each generic module: its path, and the package its relative imports start from."""
    modules = []
    for module in GENERIC_MODULES:
        path = PACKAGE_DIR / f"{module}.py"
        if path.exists():
            modules.append((path, "k_b"))
        else:
            modules.append((PACKAGE_DIR / module / "__init__.py", f"k_b.{module}"))
    return modules


def test_no_generic_module_imports_the_sources_or_the_composition():
    for path, package in list_generic_modules():
        forbidden = list_imported_modules(path, package) & (
            {SOURCES_PACKAGE} | COMPOSITION_MODULES
        )
        assert forbidden == set(), path


def test_no_module_of_the_sources_imports_the_composition():
    paths = sorted(SOURCES_DIR.glob("*.py"))

    assert paths
    for path in paths:
        imported = list_imported_modules(path, f"k_b.{SOURCES_PACKAGE}")
        assert imported & COMPOSITION_MODULES == set(), path
