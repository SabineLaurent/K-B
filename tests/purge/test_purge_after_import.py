"""The purges after an import: run only on a base that exists."""

from datetime import UTC, datetime

import pytest

from k_b.database.connection import MissingDatabaseError
from k_b.purge.after_import import purge_after_import


def test_without_a_base_the_purges_fail_and_create_none(tmp_path):
    (tmp_path / "raw").mkdir()

    with pytest.raises(MissingDatabaseError):
        purge_after_import(tmp_path, datetime(2027, 4, 5, tzinfo=UTC), (), ())

    assert not (tmp_path / "k-b.sqlite").exists()
