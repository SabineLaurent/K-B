"""The drivers of the base are imported by the access layer only: sqlite3 by database/engine.py
and database/errors.py (and the Zotero source, whose base is Zotero's), psycopg by
database/postgresql.py and database/errors.py (MEMORY.md, "Accès à la base")."""

import ast

import pytest
from module_imports import PACKAGE_DIR

MODULES_ALLOWED_BY_DRIVER = {
    "sqlite3": {"database/engine.py", "database/errors.py", "etl/sources/zotero.py"},
    "psycopg": {"database/postgresql.py", "database/errors.py"},
}


def list_modules_importing(driver):
    """The modules of k_b that import the driver, or a module of it, as paths below k_b."""
    importers = set()
    for path in PACKAGE_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            if any(name == driver or name.startswith(f"{driver}.") for name in names):
                importers.add(path.relative_to(PACKAGE_DIR).as_posix())
    return importers


@pytest.mark.parametrize("driver", MODULES_ALLOWED_BY_DRIVER)
def test_only_the_access_layer_imports_a_driver_of_the_base(driver):
    assert list_modules_importing(driver) == MODULES_ALLOWED_BY_DRIVER[driver]
