from datetime import UTC, datetime, timedelta

from k_b.collect import collect_all_sources
from k_b.raw_store import load_last_collection_dates

FIRST_RUN_AT = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
SECOND_RUN_AT = FIRST_RUN_AT + timedelta(hours=1)


class WorkingSource:
    extension = "json"

    def __init__(self, name="working"):
        self.name = name
        self.received_last_collected_at = []

    def fetch(self, last_collected_at):
        self.received_last_collected_at.append(last_collected_at)
        return b'{"items": []}'


class BrokenSource:
    name = "broken"
    extension = "json"

    def fetch(self, last_collected_at):
        raise ConnectionError("source is down")


def test_a_broken_source_does_not_stop_the_others(tmp_path):
    errors_by_source = collect_all_sources(
        [BrokenSource(), WorkingSource()], tmp_path, FIRST_RUN_AT
    )

    assert isinstance(errors_by_source["broken"], ConnectionError)
    assert errors_by_source["working"] is None
    raw_file_path = tmp_path / "automation" / "working" / "2026-09-30T100000Z.json"
    assert raw_file_path.read_bytes() == b'{"items": []}'
    assert not (tmp_path / "automation" / "broken").exists()


def test_only_successful_sources_advance_their_last_collection_date(tmp_path):
    collect_all_sources([BrokenSource(), WorkingSource()], tmp_path, FIRST_RUN_AT)

    assert load_last_collection_dates(tmp_path) == {"working": FIRST_RUN_AT}


def test_a_source_receives_its_last_successful_collection_date(tmp_path):
    working_source = WorkingSource()

    collect_all_sources([working_source], tmp_path, FIRST_RUN_AT)
    collect_all_sources([working_source], tmp_path, SECOND_RUN_AT)

    assert working_source.received_last_collected_at == [None, FIRST_RUN_AT]


def test_a_second_run_at_the_same_instant_fails_without_overwriting(tmp_path):
    collect_all_sources([WorkingSource()], tmp_path, FIRST_RUN_AT)

    errors_by_source = collect_all_sources([WorkingSource()], tmp_path, FIRST_RUN_AT)

    assert isinstance(errors_by_source["working"], FileExistsError)


def test_a_source_name_that_is_not_a_safe_path_segment_is_refused(tmp_path):
    raw_dir = tmp_path / "raw"

    errors_by_source = collect_all_sources([WorkingSource(name="../escape")], raw_dir, FIRST_RUN_AT)

    assert isinstance(errors_by_source["../escape"], ValueError)
    assert not (raw_dir / "escape").exists()
    assert not (raw_dir / "automation").exists()


class UnchangedSource:
    name = "unchanged"
    extension = "csv"

    def fetch(self, last_collected_at):
        return None


def test_a_source_with_nothing_new_writes_no_raw_file_but_succeeds(tmp_path):
    errors_by_source = collect_all_sources([UnchangedSource()], tmp_path, FIRST_RUN_AT)

    assert errors_by_source == {"unchanged": None}
    assert not (tmp_path / "automation").exists()
    assert load_last_collection_dates(tmp_path) == {"unchanged": FIRST_RUN_AT}
