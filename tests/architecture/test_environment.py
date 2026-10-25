"""The environment is read in one place, commands/environment.py: the commands and the readers get it
as a parameter (.claude/rules/poc.md, rule 2)."""

import ast

import pytest
from module_imports import PACKAGE_DIR

# The only module that reads the environment.
ENVIRONMENT_MODULE = "commands/environment.py"
# For now, the GitHub API client reads its token itself: passing it to the GitHub sources waits for
# one way to create every source that needs the environment (ADR of 2026-10-25).
TOLERATED_FOR_NOW = {"etl/sources/github/api.py"}
OS_ENVIRONMENT_NAMES = {
    "environ",
    "getenv",
    "putenv",
    "unsetenv",
    "environb",
    "getenvb",
}


def find_environment_readings(code: str) -> list[int]:
    """The lines where the code reads the environment through os: os.environ, os.getenv…, or one of
    them imported from os."""
    lines = []
    for node in ast.walk(ast.parse(code)):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in OS_ENVIRONMENT_NAMES
        ):
            lines.append(node.lineno)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "os"
            and any(alias.name in OS_ENVIRONMENT_NAMES for alias in node.names)
        ):
            lines.append(node.lineno)
    return lines


def test_only_commands_environment_reads_the_environment():
    readings = {
        path.relative_to(PACKAGE_DIR).as_posix(): find_environment_readings(
            path.read_text(encoding="utf-8")
        )
        for path in PACKAGE_DIR.rglob("*.py")
    }

    assert {path for path, lines in readings.items() if lines} == {
        ENVIRONMENT_MODULE
    } | TOLERATED_FOR_NOW


@pytest.mark.parametrize(
    ("code", "is_reading"),
    [
        ("import os\nos.environ.get('KB_DATA_DIR')", True),
        ("import os\nos.getenv('KB_DATA_DIR')", True),
        ("import os\nvalue = os.environ['KB_DATA_DIR']", True),
        ("from os import environ", True),
        ("from os import getenv as read", True),
        ("def run(environ):\n    return environ.get('KB_DATA_DIR')", False),
        ("import os\nos.path.join('a', 'b')", False),
        ("# os.environ in a comment", False),
    ],
)
def test_the_rule_finds_every_way_to_read_the_environment_and_only_them(
    code, is_reading
):
    assert bool(find_environment_readings(code)) is is_reading
