"""uv run pytest, the command of the CI, leaves out the end-to-end tests; -m e2e runs them, one
per source, and stops them on a variable they must not get. A test recorded property is in the HTML
report, which the user alone can read."""

import html
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from k_b.commands.environment import DATA_DIR_VARIABLE, LOG_TO_FILE_VARIABLE
from k_b.etl.collected_sources import ZOTERO_DIR_VARIABLE
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


# A value the end-to-end tests must never print, in a variable they must never get.
VALUE_BEYOND = "value-beyond-the-end-to-end-tests"


def test_the_end_to_end_tests_stop_on_a_variable_beyond_theirs_without_its_value():
    """-k zotero without KB_ZOTERO_DIR: even with the guard broken, the test is skipped and no
    real source is called."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in ("PYTEST_ADDOPTS", ZOTERO_DIR_VARIABLE)
    }
    environment["KB_LLM_API_KEY"] = VALUE_BEYOND
    # Set or removed by the test before any kb: never a reason to stop.
    environment[DATA_DIR_VARIABLE] = VALUE_BEYOND
    environment[LOG_TO_FILE_VARIABLE] = VALUE_BEYOND

    result = subprocess.run(  # noqa: S603 — runs this interpreter on pytest, fixed arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-m",
            "e2e",
            "-k",
            "zotero",
            str(E2E_DIR),
        ],
        capture_output=True,
        text=True,
        cwd=TESTS_DIR.parent,
        env=environment,
    )

    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    assert "1 selected" in result.stdout
    assert "KB_LLM_API_KEY" in result.stdout
    assert DATA_DIR_VARIABLE not in result.stdout
    assert LOG_TO_FILE_VARIABLE not in result.stdout
    assert " skipped" not in result.stdout
    assert " passed" not in result.stdout
    assert VALUE_BEYOND not in result.stdout + result.stderr


def write_marker_test(directory):
    """A test that records a property, run with a copy of the conftest of the suite."""
    shutil.copy(TESTS_DIR / "conftest.py", directory / "conftest.py")
    (directory / "test_marker.py").write_text(
        "def test_marker(record_property):\n"
        f"    record_property('marker', {MARKER!r})\n"
    )


# A value with a tag: the report shows it escaped, never as HTML.
MARKER = "<b>marker</b>"


def produce_report(directory, report_path):
    subprocess.run(  # noqa: S603 — runs this interpreter on pytest, fixed arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            f"--html={report_path}",
            "--self-contained-html",
            str(directory / "test_marker.py"),
        ],
        capture_output=True,
        text=True,
        cwd=directory,
        check=True,
        env={
            name: value
            for name, value in os.environ.items()
            if name != "PYTEST_ADDOPTS"
        },
    )


def read_report_data(report_path):
    """The data of the report, which its page renders: an attribute holding JSON."""
    blob = re.search(r'data-jsonblob="([^"]*)"', report_path.read_text())
    assert blob is not None
    return html.unescape(blob.group(1))


def test_a_recorded_property_is_in_the_report_escaped(tmp_path):
    write_marker_test(tmp_path)
    report_path = tmp_path / "reports" / "report.html"

    produce_report(tmp_path, report_path)

    report_data = read_report_data(report_path)
    assert f"marker={html.escape(MARKER)}" in report_data
    assert MARKER not in report_data


def test_the_report_and_its_new_folder_are_readable_by_the_user_alone(tmp_path):
    write_marker_test(tmp_path)
    report_path = tmp_path / "reports" / "report.html"

    produce_report(tmp_path, report_path)

    assert stat.S_IMODE(report_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


def test_a_report_written_before_is_made_readable_by_the_user_alone(tmp_path):
    write_marker_test(tmp_path)
    report_path = tmp_path / "report.html"
    report_path.write_text("")
    report_path.chmod(0o644)

    produce_report(tmp_path, report_path)

    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
