import logging
import os
from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError

import pytest

from k_b.etl.extract import collect_all_sources
from k_b.etl.raw_store import load_last_collection_dates, save_last_collection_dates
from k_b.etl.sources import tldr

FIRST_RUN_AT = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
SECOND_RUN_AT = FIRST_RUN_AT + timedelta(hours=1)


class WorkingSource:
    extension = "json"
    acquisition_dir_name = "automated_watch"

    def __init__(self, name="working"):
        self.name = name
        self.received_last_collected_at = []

    def fetch(self, last_collected_at):
        self.received_last_collected_at.append(last_collected_at)
        return b'{"items": []}'


class BrokenSource:
    name = "broken"
    extension = "json"
    acquisition_dir_name = "automated_watch"

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


class LibrarySource(WorkingSource):
    """A source of what the user selected, as Zotero is."""

    acquisition_dir_name = "selected_library"


def test_a_source_of_the_selected_library_is_stored_in_its_own_folder_of_raw(tmp_path):
    errors_by_source = collect_all_sources(
        [LibrarySource(name="library")], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert errors_by_source == {"library": None}
    raw_file_path = (
        tmp_path / "raw" / "selected_library" / "library" / "2026-09-30T100000Z.json"
    )
    assert raw_file_path.read_bytes() == b'{"items": []}'
    assert not (tmp_path / "raw" / "automated_watch").exists()


def test_a_raw_folder_that_is_not_a_safe_path_segment_is_refused(tmp_path):
    source = WorkingSource()
    source.acquisition_dir_name = "../escape"

    errors_by_source = collect_all_sources(
        [source], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert isinstance(errors_by_source["working"], ValueError)
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "raw").exists()


def test_a_raw_folder_that_is_not_one_of_the_two_folders_of_raw_is_refused(tmp_path):
    source = WorkingSource()
    source.acquisition_dir_name = "automated_watchs"

    errors_by_source = collect_all_sources(
        [source], tmp_path / "raw", tmp_path, FIRST_RUN_AT
    ).errors_by_source

    assert isinstance(errors_by_source["working"], ValueError)
    assert "automated_watchs" in str(errors_by_source["working"])
    assert not (tmp_path / "raw").exists()


class UnchangedSource:
    name = "unchanged"
    extension = "csv"
    acquisition_dir_name = "automated_watch"

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
    acquisition_dir_name = "automated_watch"

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
        with caplog.at_level(logging.ERROR, logger="k_b.etl.extract"):
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


def test_a_failed_tldr_page_is_logged_once_with_its_day_and_url(
    tmp_path, monkeypatch, caplog
):
    def failing_download(url, trusted_url_prefix, max_bytes):
        raise HTTPError(url, 500, "Internal Server Error", {}, None)

    monkeypatch.setattr(tldr, "download", failing_download)
    monkeypatch.setattr(tldr, "current_day", lambda: date(2026, 10, 4))
    # One day to collect: 2026-10-04.
    save_last_collection_dates(
        tmp_path, {"tldr_ai": datetime(2026, 10, 4, 6, 0, tzinfo=UTC)}
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        outcome = collect_all_sources(
            [tldr.TldrSource("ai")], tmp_path / "raw", tmp_path, SECOND_RUN_AT
        )

    assert isinstance(outcome.errors_by_source["tldr_ai"], HTTPError)
    [error_record] = [
        record for record in caplog.records if record.levelno >= logging.ERROR
    ]
    assert error_record.name == "k_b.etl.extract"
    assert error_record.getMessage() == (
        "collection failed for source 'tldr_ai': HTTPError "
        "'HTTP Error 500: Internal Server Error'; "
        "'tldr_ai 2026-10-04, from https://tldr.tech/ai/2026-10-04'"
    )


def test_the_error_and_the_notes_of_a_failed_source_are_quoted_escaped(
    tmp_path, caplog
):
    class FailingSource(WorkingSource):
        def fetch(self, last_collected_at):
            error = ValueError("a value\nERROR forged")
            error.add_note("a note\nERROR forged")
            raise error

    with caplog.at_level(logging.ERROR, logger="k_b.etl.extract"):
        collect_all_sources(
            [FailingSource("failing")], tmp_path / "raw", tmp_path, FIRST_RUN_AT
        )

    [record] = caplog.records
    assert record.getMessage() == (
        "collection failed for source 'failing': ValueError "
        "'a value\\nERROR forged'; 'a note\\nERROR forged'"
    )
