"""The purge of the logs and of the journals: 6 months after the day in their name
(docs/registre-traitements.md, step 11)."""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from k_b.purge.run_records import delete_expired_records

# Six months before it: 2026-06-01.
IMPORTED_AT = datetime(2026, 12, 1, 9, 30, tzinfo=UTC)
LOG_NAMES = ("kb.log.{day}", "kb-serve-data.log.{day}", "kb-serve-ai.log.{day}")
JOURNAL_NAME = "import-journal-{day}T093000Z.jsonl"


def write_file(data_dir, folder, name):
    path = data_dir / folder / name
    path.parent.mkdir(exist_ok=True)
    path.write_text("a line\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("folder", "name"),
    [*(("logs", name) for name in LOG_NAMES), ("journals", JOURNAL_NAME)],
)
def test_a_log_or_a_journal_leaves_after_6_months_and_stays_at_6_months(
    tmp_path, folder, name
):
    older = write_file(tmp_path, folder, name.format(day="2026-05-31"))
    at_the_bound = write_file(tmp_path, folder, name.format(day="2026-06-01"))
    younger = write_file(tmp_path, folder, name.format(day="2026-06-02"))

    assert delete_expired_records(tmp_path, IMPORTED_AT) == 1
    assert (older.exists(), at_the_bound.exists(), younger.exists()) == (
        False,
        True,
        True,
    )


@pytest.mark.parametrize(
    ("folder", "name"),
    [
        # The current log of each run.
        ("logs", "kb.log"),
        ("logs", "kb-serve-data.log"),
        ("logs", "kb-serve-ai.log"),
        # A name without a readable day.
        ("logs", "notes.txt"),
        ("logs", "kb.log.old"),
        ("logs", "kb.log.2020-13-45"),
        ("journals", "import-journal-2020-01-01.jsonl"),
        ("journals", "import-journal-2020-13-45T093000Z.jsonl"),
        ("journals", ".import-journal-2020-01-01T093000Z.jsonl.a1b2c3.tmp"),
        # A dated log that kb does not write, as one the user left there.
        ("logs", "incident.log.2020-01-01"),
        ("logs", "kb_log.2020-01-01"),
        # A name of the other folder, or the name of before.
        ("journals", "kb.log.2020-01-01"),
        ("logs", "import-journal-2020-01-01T093000Z.jsonl"),
        ("journals", "import-log-2020-01-01T093000Z.jsonl"),
    ],
)
def test_any_other_name_is_never_deleted(tmp_path, folder, name):
    path = write_file(tmp_path, folder, name)

    assert delete_expired_records(tmp_path, IMPORTED_AT) == 0
    assert path.exists()


def test_a_folder_and_a_link_are_never_deleted_nor_followed(tmp_path):
    target = tmp_path / "outside.txt"
    target.write_text("kept\n", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    (logs_dir / "kb.log.2020-01-01").mkdir(parents=True)
    link = logs_dir / "kb.log.2020-01-02"
    link.symlink_to(target)

    assert delete_expired_records(tmp_path, IMPORTED_AT) == 0
    assert (logs_dir / "kb.log.2020-01-01").is_dir()
    assert link.is_symlink()
    assert target.exists()


def test_a_link_in_place_of_a_folder_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "kb.log.2020-01-01"
    target.write_text("kept\n", encoding="utf-8")
    (tmp_path / "logs").symlink_to(outside)

    assert delete_expired_records(tmp_path, IMPORTED_AT) == 0
    assert target.exists()


def test_nothing_outside_the_two_folders_is_read(tmp_path):
    """An import log written before journals/ existed stays where it is, for the user to remove."""
    path = tmp_path / "import-log-2020-01-01T093000Z.jsonl"
    path.write_text("an import log of before\n", encoding="utf-8")

    assert delete_expired_records(tmp_path, IMPORTED_AT) == 0
    assert path.exists()


def test_the_bound_is_computed_in_utc_whatever_the_time_zone_given(tmp_path):
    """2026-12-01T00:30 in Paris is 2026-11-30 in UTC: the bound is 2026-05-30, not 2026-06-01."""
    path = write_file(tmp_path, "logs", "kb.log.2026-05-31")

    delete_expired_records(
        tmp_path, datetime(2026, 12, 1, 0, 30, tzinfo=ZoneInfo("Europe/Paris"))
    )

    assert path.exists()


def test_a_file_deleted_meanwhile_by_another_import_is_no_error(tmp_path, monkeypatch):
    path = write_file(tmp_path, "logs", "kb.log.2020-01-01")
    unlink = type(path).unlink

    def deleted_first_by_another_import(self):
        unlink(self)
        unlink(self)

    monkeypatch.setattr(type(path), "unlink", deleted_first_by_another_import)

    assert delete_expired_records(tmp_path, IMPORTED_AT) == 0


def test_an_error_other_than_a_file_gone_is_raised(tmp_path, monkeypatch):
    path = write_file(tmp_path, "logs", "kb.log.2020-01-01")

    def refuse(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(type(path), "unlink", refuse)

    with pytest.raises(PermissionError):
        delete_expired_records(tmp_path, IMPORTED_AT)


def test_without_the_folders_nothing_is_done(tmp_path):
    assert delete_expired_records(tmp_path, IMPORTED_AT) == 0


def test_the_log_gives_numbers_never_a_name(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    write_file(tmp_path, "logs", "kb.log.2020-01-01")
    write_file(tmp_path, "journals", JOURNAL_NAME.format(day="2020-01-02"))

    delete_expired_records(tmp_path, IMPORTED_AT)

    assert (
        "logs and journals purge: 2 files older than 6 months deleted"
        in caplog.messages
    )
    assert "2020-01" not in caplog.text
