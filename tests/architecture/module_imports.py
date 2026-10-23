"""The reader of the imports of k_b and the lists of modules that the architecture tests
share."""

import ast
from pathlib import Path

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
    "post",
}
# Under k_b.etl, each module is in exactly one of the three.
ETL_COMPOSITION_MODULES = {"etl.source_kinds", "etl.collected_sources"}
ETL_SOURCES_PACKAGE = "etl.sources"
ETL_PIPELINE_MODULES = {
    "etl.pipeline",
    "etl.extract",
    "etl.transform",
    "etl.load",
    "etl.import_log",
    "etl.normalize",
    "etl.raw_files",
    "etl.raw_store",
    "etl.raw_purge",
    "etl.tops",
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
