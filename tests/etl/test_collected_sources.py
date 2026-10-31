"""The vault of KB_VAULT_DIR, read once, with the reason it is refused."""

import pytest

from k_b.etl.collected_sources import read_vault_dir_or_refusal

WRITTEN = "the trend report is written in the vault"


@pytest.mark.parametrize("environ", [{}, {"KB_VAULT_DIR": ""}])
def test_a_vault_not_set_is_refused_with_what_goes_there(environ):
    assert read_vault_dir_or_refusal(environ, WRITTEN) == (
        f"KB_VAULT_DIR not set; {WRITTEN}"
    )


def test_a_vault_that_does_not_exist_is_refused_without_its_path(tmp_path):
    refusal = read_vault_dir_or_refusal(
        {"KB_VAULT_DIR": str(tmp_path / "typo")}, WRITTEN
    )

    assert refusal == "KB_VAULT_DIR is not an existing directory; no folder is created"


def test_an_existing_vault_is_given_back(tmp_path):
    assert read_vault_dir_or_refusal({"KB_VAULT_DIR": str(tmp_path)}, WRITTEN) == (
        tmp_path
    )
