"""The data directory of the tests of the load: the recorded raw files of four sources and an
empty base; a test file that needs another one defines its own."""

import pytest
from test_transform import copy_fixture

from k_b.database.creation import create_database


@pytest.fixture
def data_dir(tmp_path):
    raw_dir = tmp_path / "raw"
    copy_fixture(raw_dir, "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml")
    copy_fixture(raw_dir, "cisa_kev_extract.csv", "cisa_kev", "csv")
    copy_fixture(
        raw_dir,
        "github_releases_extract.json",
        "github_releases_anthropics_claude_code",
        "json",
    )
    copy_fixture(
        raw_dir, "github_advisories_extract.json", "github_advisories_pip", "json"
    )
    create_database(tmp_path / "k-b.sqlite")
    return tmp_path
