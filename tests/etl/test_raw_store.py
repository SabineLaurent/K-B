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
    RawStore,
    find_stream,
    load_last_collection_dates,
    make_source_folder_key,
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
    """A real temporary file whose write, flush or close fails as on a full disk. As in
    io.BufferedWriter, a failed flush leaves the data in the buffer: the close fails again."""

    def __init__(self, temporary_file, failing_step, error):
        self.temporary_file = temporary_file
        self.failing_step = failing_step
        self.error = error
        self.name = temporary_file.name
        self.is_closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def write(self, content):
        if self.failing_step == "write":
            raise self.error
        return self.temporary_file.write(content)

    def flush(self):
        if self.failing_step == "flush":
            raise self.error
        self.temporary_file.flush()

    def fileno(self):
        return self.temporary_file.fileno()

    def close(self):
        if self.is_closed:
            return
        self.is_closed = True
        self.temporary_file.close()
        if self.failing_step == "close":
            raise self.error
        if self.failing_step == "flush":
            raise OSError(errno.ENOSPC, "No space left on device")


def disk_full():
    return OSError(errno.ENOSPC, "No space left on device")


@pytest.mark.parametrize(
    ("failing_step", "error"),
    [
        ("write", disk_full()),
        ("flush", disk_full()),
        ("flush", KeyboardInterrupt()),
        ("close", disk_full()),
        ("rename", KeyboardInterrupt()),
    ],
    ids=["write", "flush", "ctrl-c-at-flush", "close", "ctrl-c-at-rename"],
)
def test_a_failed_write_leaves_no_temporary_file_and_raises_its_own_error(
    tmp_path, monkeypatch, failing_step, error
):
    target = tmp_path / COLLECTION_STATE_FILENAME
    target.write_bytes(b"previous")
    real_named_temporary_file = tempfile.NamedTemporaryFile
    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: FailingTemporaryFile(
            real_named_temporary_file(**kwargs), failing_step, error
        ),
    )
    if failing_step == "rename":

        def interrupt_the_rename(source, target):
            raise error

        monkeypatch.setattr(os, "replace", interrupt_the_rename)

    with pytest.raises(type(error)) as raised:
        write_file_atomically(target, b"next")

    assert raised.value is error
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


def test_each_folder_created_for_the_write_is_synced_in_its_parent(
    tmp_path, monkeypatch
):
    synced_inodes = []
    real_fsync = os.fsync

    def record_fsync(file_descriptor):
        synced_inodes.append(os.fstat(file_descriptor).st_ino)
        real_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)
    source_dir = tmp_path / "automated_watch" / "tldr_ai"
    source_dir.mkdir(parents=True)
    collection_dir = source_dir / "2026-10-07T084509Z"
    target = collection_dir / "2026-10-07.html"

    write_file_atomically(target, b"page")

    assert synced_inodes == [
        target.stat().st_ino,
        collection_dir.stat().st_ino,
        source_dir.stat().st_ino,
    ]


def fail_the_fsync_of_a_folder(error_number):
    real_fsync = os.fsync

    def fsync(file_descriptor):
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError(error_number, os.strerror(error_number))
        real_fsync(file_descriptor)

    return fsync


@pytest.mark.parametrize(
    "error_number", [errno.EBADF, errno.EINVAL], ids=["EBADF", "EINVAL"]
)
def test_a_folder_that_refuses_fsync_does_not_fail_the_write(
    tmp_path, monkeypatch, error_number
):
    monkeypatch.setattr(os, "fsync", fail_the_fsync_of_a_folder(error_number))
    target = tmp_path / "new_folder" / COLLECTION_STATE_FILENAME

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


def test_a_key_is_deleted_under_the_data_directory_once(tmp_path):
    raw_file = (
        tmp_path / "raw" / "automated_watch" / "cisa_kev" / "2026-10-05T093000Z.csv"
    )
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"catalog")
    store = RawStore(tmp_path)

    assert store.has_file("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")
    assert store.delete("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")
    assert not raw_file.exists()
    assert not store.has_file("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")
    assert not store.delete("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")


@pytest.mark.parametrize(
    "key", ["", "/etc/passwd", "raw/../k-b.sqlite", "../outside", "raw\\..\\k-b.sqlite"]
)
def test_a_key_that_is_not_relative_to_the_data_directory_is_refused(tmp_path, key):
    store = RawStore(tmp_path / "data")

    for method in (
        store.delete,
        store.has_file,
        store.read_latest,
        store.list_file_keys,
        store.read,
    ):
        with pytest.raises(
            ValueError, match="not a key relative to the data directory"
        ):
            method(key)


def test_the_latest_raw_file_of_a_folder_is_read_hidden_files_left_out(tmp_path):
    folder = tmp_path / "raw" / "selected_library" / "zotero"
    folder.mkdir(parents=True)
    (folder / "2026-10-05T093000Z.json").write_bytes(b"older")
    (folder / "2026-10-06T093000Z.json").write_bytes(b"latest")
    # A rest of an interrupted write, as write_file_atomically names it.
    (folder / ".2026-10-07T093000Z.json.abc.tmp").write_bytes(b"half")

    assert RawStore(tmp_path).read_latest("raw/selected_library/zotero") == b"latest"


def test_a_folder_without_raw_file_has_no_latest(tmp_path):
    (tmp_path / "raw" / "selected_library" / "zotero").mkdir(parents=True)
    store = RawStore(tmp_path)

    assert store.read_latest("raw/selected_library/zotero") is None
    assert store.read_latest("raw/selected_library/absent") is None


def test_the_keys_of_a_folder_are_listed_in_name_order_hidden_files_left_out(tmp_path):
    folder = tmp_path / "raw" / "automated_watch" / "github_most_starred"
    folder.mkdir(parents=True)
    (folder / "2026-10-06T093000Z.json").write_bytes(b"latest")
    (folder / "2026-10-05T093000Z.json").write_bytes(b"older")
    # A rest of an interrupted write, and the pages of a collection, in a subfolder.
    (folder / ".2026-10-07T093000Z.json.abc.tmp").write_bytes(b"half")
    (folder / "2026-10-07T093000Z").mkdir()
    store = RawStore(tmp_path)

    keys = store.list_file_keys("raw/automated_watch/github_most_starred")

    assert keys == [
        "raw/automated_watch/github_most_starred/2026-10-05T093000Z.json",
        "raw/automated_watch/github_most_starred/2026-10-06T093000Z.json",
    ]
    assert [store.read(key) for key in keys] == [b"older", b"latest"]


def test_a_folder_that_does_not_exist_has_no_key(tmp_path):
    assert RawStore(tmp_path).list_file_keys("raw/automated_watch/absent") == []


def test_the_folder_key_of_a_source_is_under_raw_and_its_acquisition_folder():
    assert make_source_folder_key("selected_library", "zotero") == (
        "raw/selected_library/zotero"
    )
