import logging
import os
from datetime import UTC, datetime, timedelta

import pytest

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
        [BrokenSource(), WorkingSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert isinstance(errors_by_source["broken"], ConnectionError)
    assert errors_by_source["working"] is None
    raw_file_path = (
        tmp_path / "raw" / "automated_watch" / "working" / "2026-09-30T100000Z.json"
    )
    assert raw_file_path.read_bytes() == b'{"items": []}'
    assert not (tmp_path / "raw" / "automated_watch" / "broken").exists()


def test_only_successful_sources_advance_their_last_collection_date(tmp_path):
    collect_all_sources(
        [BrokenSource(), WorkingSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    )

    assert load_last_collection_dates(tmp_path) == {"working": FIRST_RUN_AT}


def test_a_source_receives_its_last_successful_collection_date(tmp_path):
    working_source = WorkingSource()

    collect_all_sources([working_source], tmp_path / "raw", tmp_path, FIRST_RUN_AT)
    collect_all_sources([working_source], tmp_path / "raw", tmp_path, SECOND_RUN_AT)

    assert working_source.received_last_collected_at == [None, FIRST_RUN_AT]


def test_a_second_run_at_the_same_instant_fails_without_overwriting(tmp_path):
    collect_all_sources([WorkingSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT)

    errors_by_source = collect_all_sources(
        [WorkingSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert isinstance(errors_by_source["working"], FileExistsError)


def test_a_source_name_that_is_not_a_safe_path_segment_is_refused(tmp_path):
    raw_dir = tmp_path / "raw"

    errors_by_source = collect_all_sources(
        [WorkingSource(name="../escape")], raw_dir, tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert isinstance(errors_by_source["../escape"], ValueError)
    assert not (raw_dir / "escape").exists()
    assert not (raw_dir / "automated_watch").exists()


class UnchangedSource:
    name = "unchanged"
    extension = "csv"

    def fetch(self, last_collected_at):
        return None


def test_a_source_with_nothing_new_writes_no_raw_file_but_succeeds(tmp_path):
    errors_by_source = collect_all_sources(
        [UnchangedSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert errors_by_source == {"unchanged": None}
    assert not (tmp_path / "raw" / "automated_watch").exists()
    assert load_last_collection_dates(tmp_path) == {"unchanged": FIRST_RUN_AT}


class ScrapedSource:
    """Returns several pages, as a scraped source reading one page per day does."""

    extension = "html"

    def __init__(self, pages):
        self.name = "scraped"
        self.pages = pages

    def fetch(self, last_collected_at):
        return self.pages


def test_each_page_of_a_source_is_written_as_received_in_a_folder_per_collection(
    tmp_path,
):
    pages = {
        "2026-09-29": b"<html>monday</html>",
        "2026-09-30": b"<html>tuesday</html>",
    }

    errors_by_source = collect_all_sources(
        [ScrapedSource(pages)], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert errors_by_source == {"scraped": None}
    collection_dir = (
        tmp_path / "raw" / "automated_watch" / "scraped" / "2026-09-30T100000Z"
    )
    assert (collection_dir / "2026-09-29.html").read_bytes() == b"<html>monday</html>"
    assert (collection_dir / "2026-09-30.html").read_bytes() == b"<html>tuesday</html>"


def test_a_page_name_that_is_not_a_safe_path_segment_is_refused_before_any_write(
    tmp_path,
):
    pages = {"2026-09-29": b"<html>monday</html>", "../escape": b"<html>evil</html>"}

    errors_by_source = collect_all_sources(
        [ScrapedSource(pages)], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert isinstance(errors_by_source["scraped"], ValueError)
    assert not (tmp_path / "raw" / "automated_watch").exists()
    escaped_page = tmp_path / "raw" / "automated_watch" / "scraped" / "escape.html"
    assert not escaped_page.exists()


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root writes a file whatever its permissions"
)
def test_a_state_that_cannot_be_written_is_returned_and_logged_with_its_path(
    tmp_path, caplog
):
    (tmp_path / "raw" / "automated_watch").mkdir(parents=True)
    tmp_path.chmod(0o500)

    try:
        with caplog.at_level(logging.ERROR, logger="k_b.collect"):
            outcome = collect_all_sources(
                [WorkingSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT
            )
    finally:
        tmp_path.chmod(0o700)

    assert isinstance(outcome.state_error, PermissionError)
    assert outcome.errors_by_source == {"working": None}
    assert list((tmp_path / "raw" / "automated_watch" / "working").iterdir())
    assert not (tmp_path / "collection_state.json").exists()
    [record] = caplog.records
    assert str(tmp_path / "collection_state.json") in record.getMessage()
    assert record.exc_info is not None


def test_a_state_written_without_error_is_reported_as_such(tmp_path):
    outcome = collect_all_sources(
        [WorkingSource()], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    )

    assert outcome.state_error is None
