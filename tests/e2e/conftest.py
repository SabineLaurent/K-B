"""The guard of every end-to-end test (tests/e2e/): stop before any kb, or any export, if the
environment holds a variable of kb that the end-to-end tests do not need. Here, not in a test
module, so that it covers the test of the real sources and the test of the export of the metrics
(#162)."""

import os
import re
from pathlib import Path

import pytest

from k_b.commands.environment import DATA_DIR_VARIABLE
from k_b.core.api_keys import API_KEY_VARIABLE_PREFIX
from k_b.etl.collected_sources import COLLECT_ONLY_VARIABLE

# The variables of kb, and the ones of the end-to-end tests alone, by their names.
REPOSITORY_DIR = Path(__file__).parents[2]
ENV_EXAMPLE_PATH = REPOSITORY_DIR / ".env.example"
E2E_ENV_EXAMPLE_PATH = REPOSITORY_DIR / ".env.e2e_test.example"
# A line NAME=value of an environment file, set or commented out: .env.example comments out
# some keys (KB_DATA_API_KEY_AI_DIGEST).
VARIABLE_LINE = re.compile(r"^#?[ \t]*([A-Z][A-Z0-9_]*)=", re.MULTILINE)
# A line NAME=value that is set: a name commented out in .env.e2e_test.example is not theirs.
SET_VARIABLE_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)
# Set by the test before any kb: the value of the terminal never reaches kb. The settings
# tests/conftest.py removes are gone before the guard reads the environment.
VARIABLES_SET_BY_THE_TEST = frozenset({DATA_DIR_VARIABLE, COLLECT_ONLY_VARIABLE})


def read_variable_names(path, variable_line):
    """The names of the lines of path that variable_line matches; a missing file fails the
    test."""
    return set(variable_line.findall(path.read_text()))


def find_names_beyond_the_end_to_end_tests(env_example_path, e2e_env_example_path):
    """The variables of kb, set or commented out, but the ones set in the example of the
    end-to-end tests and the ones the test sets."""
    return (
        read_variable_names(env_example_path, VARIABLE_LINE)
        - read_variable_names(e2e_env_example_path, SET_VARIABLE_LINE)
        - VARIABLES_SET_BY_THE_TEST
    )


@pytest.fixture(autouse=True)
def no_variable_beyond_the_end_to_end_tests():
    """Stop every test before any kb if the environment holds a variable of kb that the
    end-to-end tests do not need: a .env exported in the terminal would give each kb its keys.
    The key of any client of the data API too, named in .env.example or not: kb serve reads
    them by their prefix. Names only: no value is read."""
    names_beyond = find_names_beyond_the_end_to_end_tests(
        ENV_EXAMPLE_PATH, E2E_ENV_EXAMPLE_PATH
    )
    present = sorted(
        name
        for name in os.environ
        if name in names_beyond or name.startswith(API_KEY_VARIABLE_PREFIX)
    )
    if present:
        pytest.exit(
            f"variables beyond the end-to-end tests in the environment: {', '.join(present)};"
            f" run from a terminal without .env exported ({E2E_ENV_EXAMPLE_PATH.name} lists"
            " theirs)",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )
