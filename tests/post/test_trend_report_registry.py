"""The register of the trend reports: absent, read, refused, and written again with one entry more."""

import json

import pytest

from k_b.post import trend_report_registry
from k_b.post.trend_report_registry import (
    TREND_REPORTS_FILENAME,
    InvalidTrendRegistryError,
    TrendReportEntry,
    append_trend_report,
    load_trend_reports,
)

REQUEST_ID = "1b4e28ba-2fa1-4d2e-9b5c-6c8e1f0a7d3e"


def entry_as_json(**changes):
    return {
        "first_window": "2026-10-24",
        "last_window": "2026-10-27",
        "file": "veille/tendances/2026-10-28.md",
        "written_at": "2026-10-28T09:30:00Z",
        "request_id": REQUEST_ID,
        "model": None,
        "choice_made": False,
    } | changes


def make_entry(**changes):
    return TrendReportEntry.model_validate_json(json.dumps(entry_as_json(**changes)))


FIRST = make_entry()
SECOND = make_entry(
    first_window="2026-10-28",
    last_window="2026-10-31",
    file="veille/tendances/2026-11-01.md",
    written_at="2026-11-01T10:00:00Z",
)


def write_register(data_dir, content):
    (data_dir / TREND_REPORTS_FILENAME).write_bytes(content)


def test_an_absent_register_holds_no_report(tmp_path):
    assert load_trend_reports(tmp_path) == []


def test_the_entries_are_read_in_the_order_they_were_written(tmp_path):
    append_trend_report(tmp_path, [], FIRST)
    append_trend_report(tmp_path, [FIRST], SECOND)

    assert load_trend_reports(tmp_path) == [FIRST, SECOND]


def test_the_register_is_json_a_person_can_read(tmp_path):
    append_trend_report(tmp_path, [], FIRST)

    content = (tmp_path / TREND_REPORTS_FILENAME).read_text("utf-8")
    assert json.loads(content) == [entry_as_json()]
    assert content.endswith("]\n")


def test_the_register_is_written_by_write_file_atomically(tmp_path, monkeypatch):
    written = []
    monkeypatch.setattr(
        trend_report_registry,
        "write_file_atomically",
        lambda path, content: written.append((path, content)),
    )

    append_trend_report(tmp_path, [FIRST], SECOND)

    [(path, content)] = written
    assert path == tmp_path / TREND_REPORTS_FILENAME
    assert len(json.loads(content)) == 2


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"not json", "input (json_invalid)"),
        (b"{}", "input (list_type)"),
        (json.dumps([entry_as_json(extra=1)]).encode(), "0.extra (extra_forbidden)"),
        (
            json.dumps([entry_as_json(first_window="2026-10-24T00:00:00Z")]).encode(),
            "0.first_window (value_error)",
        ),
        (
            json.dumps([entry_as_json(written_at="2026-10-28 09:30")]).encode(),
            "0.written_at (timezone_aware)",
        ),
        (
            json.dumps([entry_as_json(request_id="../other")]).encode(),
            "0.request_id (value_error)",
        ),
        (
            json.dumps([entry_as_json(choice_made="false")]).encode(),
            "0.choice_made (bool_type)",
        ),
        (
            json.dumps(
                [entry_as_json(first_window="2026-10-28", last_window="2026-10-27")]
            ).encode(),
            "0 (value_error)",
        ),
        (
            json.dumps(
                [entry_as_json(first_window="2026-10-13", last_window="2026-10-28")]
            ).encode(),
            "0 (value_error)",
        ),
    ],
)
def test_a_register_out_of_its_schema_is_refused_by_its_place(
    tmp_path, content, detail
):
    write_register(tmp_path, content)

    with pytest.raises(InvalidTrendRegistryError) as refused:
        load_trend_reports(tmp_path)

    assert str(refused.value) == f"{TREND_REPORTS_FILENAME} invalid: {detail}"
    assert str(tmp_path) not in str(refused.value)


def test_an_entry_of_fifteen_windows_is_read(tmp_path):
    write_register(
        tmp_path,
        json.dumps(
            [entry_as_json(first_window="2026-10-14", last_window="2026-10-28")]
        ).encode(),
    )

    [entry] = load_trend_reports(tmp_path)

    assert (entry.last_window - entry.first_window).days + 1 == 15


def test_a_register_that_cannot_be_read_is_refused_without_its_path(tmp_path):
    (tmp_path / TREND_REPORTS_FILENAME).mkdir()

    with pytest.raises(InvalidTrendRegistryError) as refused:
        load_trend_reports(tmp_path)

    assert str(refused.value) == (
        f"{TREND_REPORTS_FILENAME} not read: IsADirectoryError (Is a directory)"
    )
