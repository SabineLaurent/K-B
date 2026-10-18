"""The dependencies go one way, read at two levels (conventions.md, rule 5).

Under k_b: core and items are the common vocabulary, database reads and writes the base (its
writers under database/writers, behind database/writing), etl runs the pipeline, data_api serves
the base, ai_api calls the model, cli and commands compose. Under k_b.etl: the composition
(source_kinds, collected_sources) → the sources → the modules of the pipeline.
"""

import pytest
from module_imports import (
    COMPOSITION_MODULES,
    ETL_COMPOSITION_MODULES,
    ETL_PIPELINE_MODULES,
    ETL_SOURCES_PACKAGE,
    PACKAGE_DIR,
    find_package,
    is_within,
    list_imported_modules,
    list_python_files,
    parse_imported_modules,
    reaches,
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


# database/writing.py is the only door to the writers: outside database, no module imports
# database/writers (#251).
def list_imports_of_the_writers(imported: set[str]) -> set[str]:
    """The names, outside database, that give access to the writers: `from k_b import
    database` reaches them, `from k_b.database import writing` does not."""
    return {name for name in imported if reaches(name, {"database.writers"})}


def test_only_database_imports_its_writers():
    paths = [
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in sorted(PACKAGE_DIR.rglob("*.py"))
        if not path.is_relative_to(PACKAGE_DIR / "database")
        and list_imports_of_the_writers(list_imported_modules(path, find_package(path)))
    ]

    assert paths == []


@pytest.mark.parametrize(
    ("package", "code", "is_refused"),
    [
        ("k_b.etl", "from k_b.database import writers", True),
        ("k_b.etl", "import k_b.database.writers.paper_writer as writer", True),
        ("k_b.etl", "from ..database.writers.discard import Discard", True),
        ("k_b.etl.sources", "from ...database import writers", True),
        ("k_b.etl", "from k_b import database", True),
        ("k_b.etl", "from k_b.database.writing import write_item", False),
        ("k_b.commands", "from k_b.database import writing", False),
    ],
)
def test_the_rule_of_the_writers_refuses_every_way_to_them(package, code, is_refused):
    imported = parse_imported_modules(code, package=package)

    assert bool(list_imports_of_the_writers(imported)) is is_refused


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
