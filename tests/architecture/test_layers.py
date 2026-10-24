"""The dependencies go one way, read at two levels (conventions.md, rule 5).

Under k_b: core and items are the common vocabulary, database reads and writes the base (its
writers under database/writers, behind database/writing), etl runs the pipeline, post writes
the digests and the sheets above it, data_api serves the base, ai_api calls the model, cli and
commands compose. Under k_b.etl: the composition (source_kinds, collected_sources) → the
sources → the modules of the pipeline. Among those, the three stages never import each other:
they talk to each other through raw/, and only etl/pipeline.py chains them.
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


# post held four modules of the pipeline until they left etl (step 0 of
# docs/refactoring/plan.md): the rule they had there follows them.
def test_post_imports_neither_the_sources_nor_the_composition():
    forbidden = {ETL_SOURCES_PACKAGE} | COMPOSITION_MODULES
    for path in list_python_files("post"):
        imported = list_imported_modules(path, find_package(path))
        assert {name for name in imported if reaches(name, forbidden)} == set(), path


# The three stages of the ETL talk to each other through raw/, never by their code: the
# collection writes it, the import reads it, and only etl/pipeline.py chains them
# (docs/refactoring/plan.md, part 2, rule 4). What they share is the vocabulary of
# etl/raw_files.py; a rejection goes through etl/rejections.py. A subset of
# ETL_PIPELINE_MODULES: the other modules of the pipeline run below the stages.
ETL_STAGE_MODULES = {"etl.extract", "etl.transform", "etl.load"}


def list_imports_of_another_stage(imported: set[str], stage: str) -> set[str]:
    """The names, in the module of a stage, that give access to another stage: `from k_b.etl
    import load` reaches the load, `from k_b.etl.raw_files import RawReading` reaches no
    stage, and the stage's own name is its own business."""
    return {name for name in imported if reaches(name, ETL_STAGE_MODULES - {stage})}


def test_no_stage_of_the_etl_imports_another_stage():
    for stage in sorted(ETL_STAGE_MODULES):
        for path in list_python_files(stage):
            imported = list_imported_modules(path, find_package(path))
            assert list_imports_of_another_stage(imported, stage) == set(), path


@pytest.mark.parametrize(
    ("stage", "code", "is_refused"),
    [
        ("etl.load", "from k_b.etl.transform import reject", True),
        ("etl.load", "from k_b.etl import transform", True),
        ("etl.load", "from .transform import reject", True),
        ("etl.transform", "import k_b.etl.load", True),
        ("etl.transform", "from k_b.etl.extract import collect_one_source", True),
        ("etl.extract", "from k_b import etl", True),
        ("etl.load", "from k_b.etl.raw_files import RawReading", False),
        ("etl.load", "from k_b.etl.rejections import reject", False),
        # Its own module: the rule is about the other stages.
        ("etl.transform", "from k_b.etl.transform import read_raw_files", False),
    ],
)
def test_the_rule_of_the_stages_refuses_every_way_to_another_stage(
    stage, code, is_refused
):
    imported = parse_imported_modules(code, package="k_b.etl")

    assert bool(list_imports_of_another_stage(imported, stage)) is is_refused


# etl and post run below the APIs: kb digest reaches the AI API by HTTP, never by its code
# (#209); its client is post/ai_api_client.py.
def list_imports_of_the_apis(imported: set[str]) -> set[str]:
    return {name for name in imported if reaches(name, {"data_api", "ai_api"})}


def test_etl_imports_neither_the_data_api_nor_the_ai_api():
    for path in list_python_files("etl"):
        imported = list_imported_modules(path, find_package(path))
        assert list_imports_of_the_apis(imported) == set(), path


def test_post_imports_neither_the_data_api_nor_the_ai_api():
    for path in list_python_files("post"):
        imported = list_imported_modules(path, find_package(path))
        assert list_imports_of_the_apis(imported) == set(), path


@pytest.mark.parametrize(
    ("code", "is_refused"),
    [
        ("from k_b.ai_api.schemas.digest_schema import DigestsSchema", True),
        ("from k_b import data_api", True),
        ("from ..ai_api.connectors import llm_client", True),
        ("from k_b.core.outbound import open_http_client", False),
    ],
)
def test_the_rule_of_etl_refuses_every_way_to_the_apis(code, is_refused):
    imported = parse_imported_modules(code, package="k_b.etl")

    assert bool(list_imports_of_the_apis(imported)) is is_refused


# etl runs below the post-processing: post reads the pipeline, the pipeline never reads post.
def list_imports_of_the_post_processing(imported: set[str]) -> set[str]:
    return {name for name in imported if reaches(name, {"post"})}


def test_etl_imports_nothing_of_the_post_processing():
    for path in list_python_files("etl"):
        imported = list_imported_modules(path, find_package(path))
        assert list_imports_of_the_post_processing(imported) == set(), path


@pytest.mark.parametrize(
    ("code", "is_refused"),
    [
        ("from k_b.post.ai_api_client import build_ai_api_client", True),
        ("from k_b import post", True),
        ("from k_b.post import digest_sheets", True),
        ("from ..post.digest_sheets import write_digest_sheet", True),
        ("from k_b.etl.tops import Top", False),
    ],
)
def test_the_rule_of_etl_refuses_every_way_to_the_post_processing(code, is_refused):
    imported = parse_imported_modules(code, package="k_b.etl")

    assert bool(list_imports_of_the_post_processing(imported)) is is_refused


def test_no_module_of_the_sources_imports_the_composition():
    for path in list_python_files(ETL_SOURCES_PACKAGE):
        imported = list_imported_modules(path, find_package(path))
        assert {
            name for name in imported if reaches(name, COMPOSITION_MODULES)
        } == set(), path
