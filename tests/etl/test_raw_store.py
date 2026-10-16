import errno
import json
import os
import stat
import tempfile
from datetime import UTC, datetime

import pytest

from k_b.core.quoting import quote_value
from k_b.etl.raw_store import (
    COLLECTION_STATE_FILENAME,
    InvalidCollectionStateError,
    find_stream,
    load_last_collection_dates,
    save_last_collection_dates,
    write_file_atomically,
    write_new_raw_file,
)


def test_write_new_raw_file_refuses_to_overwrite(tmp_path):
    raw_file_path = tmp_path / "automated_watch" / "fake" / "2026-09-30T100000Z.json"
    write_new_raw_file(raw_file_path, b"first")

    with pytest.raises(FileExistsError):
        write_new_raw_file(raw_file_path, b"second")

    assert raw_file_path.read_bytes() == b"first"


class FailingTemporaryFile:
    """A real temporary file whose write or close fails as on a full disk."""

    def __init__(self, temporary_file, failing_step):
        self.temporary_file = temporary_file
        self.failing_step = failing_step
        self.name = temporary_file.name

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.temporary_file.close()

    def write(self, content):
        if self.failing_step == "write":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.temporary_file.write(content)

    def flush(self):
        self.temporary_file.flush()

    def fileno(self):
        return self.temporary_file.fileno()

    def close(self):
        self.temporary_file.close()
        if self.failing_step == "close":
            raise OSError(errno.ENOSPC, "No space left on device")


def interrupt_the_rename(source, target):
    raise KeyboardInterrupt


@pytest.mark.parametrize(
    ("failing_step", "expected_error"),
    [("write", OSError), ("close", OSError), ("rename", KeyboardInterrupt)],
)
def test_a_failed_write_leaves_no_temporary_file_and_raises_its_error(
    tmp_path, monkeypatch, failing_step, expected_error
):
    target = tmp_path / COLLECTION_STATE_FILENAME
    target.write_bytes(b"previous")
    real_named_temporary_file = tempfile.NamedTemporaryFile
    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: FailingTemporaryFile(
            real_named_temporary_file(**kwargs), failing_step
        ),
    )
    if failing_step == "rename":
        monkeypatch.setattr(os, "replace", interrupt_the_rename)

    with pytest.raises(expected_error):
        write_file_atomically(target, b"next")

    assert list(tmp_path.iterdir()) == [target]
    assert target.read_bytes() == b"previous"


def test_the_temporary_file_is_synced_before_the_rename_then_its_folder(
    tmp_path, monkeypatch
):
    events = []
    real_fsync = os.fsync
    real_replace = os.replace

    def record_fsync(file_descriptor):
        events.append(("fsync", os.fstat(file_descriptor).st_ino))
        real_fsync(file_descriptor)

    def record_replace(source, target):
        events.append(("replace", None))
        real_replace(source, target)

    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(os, "replace", record_replace)
    target = tmp_path / COLLECTION_STATE_FILENAME

    write_file_atomically(target, b"{}")

    assert events == [
        ("fsync", target.stat().st_ino),
        ("replace", None),
        ("fsync", tmp_path.stat().st_ino),
    ]


def fail_the_fsync_of_a_folder(error_number):
    real_fsync = os.fsync

    def fsync(file_descriptor):
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError(error_number, os.strerror(error_number))
        real_fsync(file_descriptor)

    return fsync


def test_a_folder_that_refuses_fsync_does_not_fail_the_write(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "fsync", fail_the_fsync_of_a_folder(errno.EINVAL))
    target = tmp_path / COLLECTION_STATE_FILENAME

    write_file_atomically(target, b"{}")

    assert target.read_bytes() == b"{}"


def test_a_failed_fsync_of_the_folder_is_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "fsync", fail_the_fsync_of_a_folder(errno.EIO))

    with pytest.raises(OSError) as raised:
        write_file_atomically(tmp_path / COLLECTION_STATE_FILENAME, b"{}")

    assert raised.value.errno == errno.EIO


def test_last_collection_dates_are_empty_before_the_first_collection(tmp_path):
    assert load_last_collection_dates(tmp_path) == {}


def test_last_collection_dates_round_trip_as_utc_aware_datetimes(tmp_path):
    collected_at = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
    save_last_collection_dates(tmp_path, {"fake": collected_at})

    last_collection_dates = load_last_collection_dates(tmp_path)

    assert last_collection_dates == {"fake": collected_at}
    assert last_collection_dates["fake"].tzinfo is not None


@pytest.mark.parametrize(
    "state_file_content",
    [
        '{"fake": "2026-09-30T10:00:00"}',  # naive date
        '{"fake": "not a date"}',
        '{"fake": 42}',
        '["fake"]',
        '{"fake": ',  # truncated JSON
    ],
)
def test_invalid_collection_state_is_refused(tmp_path, state_file_content):
    (tmp_path / COLLECTION_STATE_FILENAME).write_text(
        state_file_content, encoding="utf-8"
    )

    with pytest.raises(InvalidCollectionStateError):
        load_last_collection_dates(tmp_path)


def test_a_collection_state_that_is_not_utf8_is_refused(tmp_path):
    (tmp_path / COLLECTION_STATE_FILENAME).write_bytes(
        '{"caf\u00e9": 1}'.encode("latin-1")
    )

    with pytest.raises(InvalidCollectionStateError):
        load_last_collection_dates(tmp_path)


@pytest.mark.parametrize(
    ("raw_file_path", "stream"),
    [
        ("automated_watch/cisa_kev/2026-10-05T093000Z.csv", "cisa_kev"),
        ("automated_watch/tldr_ai/2026-10-07T084509Z/2026-10-07.html", "tldr_ai"),
    ],
)
def test_the_stream_is_the_folder_of_the_source(raw_file_path, stream):
    assert find_stream(raw_file_path) == stream


def test_a_path_without_a_source_folder_is_refused():
    with pytest.raises(ValueError, match="cisa_kev.csv"):
        find_stream("automated_watch/cisa_kev.csv")


def test_a_long_source_name_and_date_of_the_state_are_quoted_cut_in_the_refusal(
    tmp_path,
):
    long_name = "source\n" + "n" * 50_000
    long_date = "date\n" + "d" * 50_000
    (tmp_path / "collection_state.json").write_text(
        json.dumps({long_name: long_date}), encoding="utf-8"
    )

    with pytest.raises(InvalidCollectionStateError) as raised:
        load_last_collection_dates(tmp_path)

    message = str(raised.value)
    assert (
        f"date of {quote_value(long_name)} is invalid: {quote_value(long_date)}"
        in message
    )
    assert "\n" not in message
    assert len(message) < 1_000
