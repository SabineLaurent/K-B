from datetime import UTC, datetime

import pytest

from k_b.etl.raw_store import (
    COLLECTION_STATE_FILENAME,
    InvalidCollectionStateError,
    find_stream,
    load_last_collection_dates,
    save_last_collection_dates,
    write_new_raw_file,
)


def test_write_new_raw_file_refuses_to_overwrite(tmp_path):
    raw_file_path = tmp_path / "automated_watch" / "fake" / "2026-09-30T100000Z.json"
    write_new_raw_file(raw_file_path, b"first")

    with pytest.raises(FileExistsError):
        write_new_raw_file(raw_file_path, b"second")

    assert raw_file_path.read_bytes() == b"first"


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
