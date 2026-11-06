"""uv run pytest leaves out the tests on PostgreSQL, the PostgreSQL half of a test of the reading
included, so that the job without PostgreSQL never needs its server; -m postgresql collects them
alone, every one of them, for the job on PostgreSQL."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
# A test of the reading, run on each engine by the fixture engine (tests/conftest.py).
READING_TESTS = TESTS_DIR / "database" / "test_reading.py"
# A module marked postgresql as a whole.
COMPARISON_TESTS = TESTS_DIR / "database" / "test_reading_on_both_engines.py"
NO_TESTS_COLLECTED = pytest.ExitCode.NO_TESTS_COLLECTED


def collect(target, *options):
    """The ids pytest collects in target with the options given, its output and its exit code."""
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
            str(target),
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
    ids = re.findall(r"^\S+::\S+$", result.stdout, re.MULTILINE)
    return ids, result.stdout, result.returncode


def engine_of(test_id):
    """The engine a collected test runs on, by its id."""
    [engine] = re.findall(r"\b(sqlite|postgresql)\b", test_id.partition("[")[2])
    return engine


def test_without_m_a_test_of_the_reading_runs_on_sqlite_only():
    ids, output, exit_code = collect(READING_TESTS)

    assert exit_code == pytest.ExitCode.OK
    assert ids
    assert {engine_of(test_id) for test_id in ids} == {"sqlite"}
    assert f"{len(ids)} deselected" in output


def test_m_postgresql_collects_the_postgresql_half_of_each_test_of_the_reading():
    sqlite_ids, _, _ = collect(READING_TESTS)

    ids, _, exit_code = collect(READING_TESTS, "-m", "postgresql")

    assert exit_code == pytest.ExitCode.OK
    assert {engine_of(test_id) for test_id in ids} == {"postgresql"}
    assert sorted(test_id.replace("postgresql", "sqlite") for test_id in ids) == sorted(
        sqlite_ids
    )


def test_a_module_marked_postgresql_is_left_out_without_m_and_collected_with_it():
    ids, output, exit_code = collect(COMPARISON_TESTS)
    marked_ids, _, _ = collect(COMPARISON_TESTS, "-m", "postgresql")

    assert ids == []
    assert exit_code == NO_TESTS_COLLECTED
    assert marked_ids
    assert f"{len(marked_ids)} deselected" in output
