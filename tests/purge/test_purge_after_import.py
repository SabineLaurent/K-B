"""The purges after an import: run only on a base that exists."""

from datetime import UTC, datetime

import pytest

from k_b.database.creation import create_database
from k_b.database.location import MissingDatabaseError
from k_b.etl.pipeline import import_raw_files
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.purge.after_import import purge_after_import


def test_without_a_base_the_purges_fail_and_create_none(tmp_path):
    (tmp_path / "raw").mkdir()

    with pytest.raises(MissingDatabaseError):
        purge_after_import(
            tmp_path, tmp_path / "k-b.sqlite", datetime(2027, 4, 5, tzinfo=UTC), (), ()
        )

    assert not (tmp_path / "k-b.sqlite").exists()


def test_the_logs_and_the_journals_are_purged_after_an_import(tmp_path):
    """The journal an import really writes is recognized by the purge, 6 months later."""
    create_database(tmp_path / "k-b.sqlite")
    older_log = tmp_path / "logs" / "kb.log.2026-01-01"
    older_log.parent.mkdir()
    older_log.write_text("a line\n", encoding="utf-8")
    imported_at = datetime(2026, 10, 12, 15, 49, 3, tzinfo=UTC)
    outcome = import_raw_files(
        tmp_path, tmp_path / "k-b.sqlite", SOURCE_KINDS, (), imported_at
    )
    assert outcome.journal_path.parent == tmp_path / "journals"
    assert outcome.journal_path.exists()

    purge_after_import(
        tmp_path, tmp_path / "k-b.sqlite", datetime(2027, 4, 13, tzinfo=UTC), (), ()
    )

    assert not older_log.exists()
    assert not outcome.journal_path.exists()
