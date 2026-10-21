"""uv run pytest, the command of the CI, leaves out the end-to-end tests; -m e2e runs them, one
per source."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from k_b.etl.source_kinds import SOURCE_KINDS

TESTS_DIR = Path(__file__).parent
E2E_DIR = TESTS_DIR / "e2e"
# The exit code of pytest when it collects no test: every one was left out.
NO_TESTS_COLLECTED = pytest.ExitCode.NO_TESTS_COLLECTED


def collect_e2e_dir(*options):
    """The ids pytest collects in tests/e2e/ with the options given, its output and its exit
    code."""
    result = subprocess.run(  # noqa: S603 — runs this interpreter on pytest, fixed arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *options,
            str(E2E_DIR),
        ],
        capture_output=True,
        text=True,
        cwd=TESTS_DIR.parent,
        # The options of the terminal would change what is collected, not the code.
        env={
            name: value
            for name, value in os.environ.items()
            if name != "PYTEST_ADDOPTS"
        },
    )
    ids = re.findall(r"::\w+\[(\w+)\]$", result.stdout, re.MULTILINE)
    return ids, result.stdout, result.returncode


def check_every_end_to_end_test_left_out(*options):
    ids, output, exit_code = collect_e2e_dir(*options)

    assert ids == []
    assert exit_code == NO_TESTS_COLLECTED
    assert f"{len(SOURCE_KINDS)} deselected" in output


def test_pytest_without_m_leaves_out_every_end_to_end_test():
    check_every_end_to_end_test_left_out()


@pytest.mark.parametrize(
    "expression", ["not nightly_e2e", "not nightly-e2e", "not e2e.slow"]
)
def test_pytest_m_of_a_marker_that_holds_e2e_leaves_out_every_end_to_end_test(
    expression,
):
    check_every_end_to_end_test_left_out("-m", expression)


def test_pytest_m_e2e_collects_one_end_to_end_test_per_source():
    ids, _, _ = collect_e2e_dir("-m", "e2e")

    assert ids == [kind.folder_prefix for kind in SOURCE_KINDS]
