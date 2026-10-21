"""uv run pytest, the command of the CI, leaves out the end-to-end tests; -m e2e runs them, one
per source."""

import re
import subprocess
import sys
from pathlib import Path

from k_b.etl.source_kinds import SOURCE_KINDS

TESTS_DIR = Path(__file__).parent
E2E_DIR = TESTS_DIR / "e2e"


def collect_e2e_dir(*options):
    """The ids pytest collects in tests/e2e/ with the options given, and its summary line."""
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
    )
    ids = re.findall(r"::\w+\[(\w+)\]$", result.stdout, re.MULTILINE)
    return ids, result.stdout


def test_pytest_without_m_leaves_out_every_end_to_end_test():
    ids, output = collect_e2e_dir()

    assert ids == []
    assert f"{len(SOURCE_KINDS)} deselected" in output


def test_pytest_m_e2e_collects_one_end_to_end_test_per_source():
    ids, _ = collect_e2e_dir("-m", "e2e")

    assert ids == [kind.folder_prefix for kind in SOURCE_KINDS]
