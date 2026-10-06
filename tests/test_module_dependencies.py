"""The dependencies go one way: composition → sources → generic modules (plan ETL)."""

import ast
import pkgutil
from pathlib import Path

import k_b

PACKAGE_DIR = Path(k_b.__file__).parent
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
SOURCE_MODULES = {
    "arxiv_source",
    "arxiv_papers",
    "cisa_kev_source",
    "cisa_kev",
    "github_releases_source",
    "github_releases",
    "github_advisories_source",
    "github_advisories",
    "github_most_starred_source",
    "github_most_starred",
    "tldr_source",
    "github_api",
    "github_dates",
    "tracked_repositories",
}
COMPOSITION_MODULES = {"cli", "source_kinds"}


def list_imported_modules(module: str) -> set[str]:
    """The k_b modules a module imports, whatever the form of its import statements."""
    path = PACKAGE_DIR / f"{module}.py"
    if not path.exists():
        path = PACKAGE_DIR / module / "__init__.py"
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "k_b":
                names = [f"k_b.{alias.name}" for alias in node.names]
            else:
                names = [node.module]
        else:
            continue
        imported |= {name.split(".")[1] for name in names if name.startswith("k_b.")}
    return imported


def test_every_module_is_in_exactly_one_list():
    modules = {module.name for module in pkgutil.iter_modules([str(PACKAGE_DIR)])}
    lists = (GENERIC_MODULES, SOURCE_MODULES, COMPOSITION_MODULES)

    assert modules == set().union(*lists)
    assert sum(len(modules_of_list) for modules_of_list in lists) == len(modules)


def test_no_generic_module_imports_a_source_or_the_composition():
    for module in GENERIC_MODULES:
        forbidden = list_imported_modules(module) & (
            SOURCE_MODULES | COMPOSITION_MODULES
        )
        assert forbidden == set(), module


def test_no_source_module_imports_the_composition():
    for module in SOURCE_MODULES:
        assert list_imported_modules(module) & COMPOSITION_MODULES == set(), module
