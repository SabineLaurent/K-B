from datetime import UTC, datetime

import pytest

from k_b.raw_store import (
    COLLECTION_STATE_FILENAME,
    InvalidCollectionStateError,
    load_last_collection_dates,
    save_last_collection_dates,
    write_new_raw_file,
)


def test_write_new_raw_file_refuses_to_overwrite(tmp_path):
    raw_file_path = tmp_path / "automation" / "fake" / "2026-09-30T100000Z.json"
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
    (tmp_path / COLLECTION_STATE_FILENAME).write_text(state_file_content, encoding="utf-8")

    with pytest.raises(InvalidCollectionStateError):
        load_last_collection_dates(tmp_path)
