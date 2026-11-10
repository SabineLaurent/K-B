"""kb purge: the purges, on their own, dated by the start of the command."""

import re
import sqlite3
from datetime import UTC, datetime

from commands.cli_helpers import LOG_LINE_DATE, make_clock
from commands.test_import_command import write_state_catalogs
from etl.test_transform import copy_fixture

from k_b import cli
from k_b.commands import purge_command
from k_b.etl.raw_store import RawStore
from k_b.purge import all_purges

# Three years and a week after the collection of the recorded raw files (2026-10-05).
THREE_YEARS_LATER = datetime(2029, 10, 12, tzinfo=UTC)


def count_rows(data_dir, query):
    connection = sqlite3.connect(data_dir / "k-b.sqlite")
    try:
        return connection.execute(query).fetchone()[0]
    finally:
        connection.close()


def test_purge_alone_deletes_what_is_past_its_durations_without_an_import_that_day(
    monkeypatch, tmp_path, capsys
):
    """Imported in 2026, a raw file of arXiv is purged three years later by kb purge alone: the
    base, the raw, the registry, then the logs and the journals, in turn."""
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    raw_path = copy_fixture(
        tmp_path / "raw", "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml"
    )
    assert cli.main(["import"]) == 0
    assert count_rows(tmp_path, "SELECT count(*) FROM item") > 0
    older_log = tmp_path / "logs" / "kb.log.2020-01-01"
    older_log.write_text("a line\n", encoding="utf-8")
    monkeypatch.setattr(purge_command, "datetime", make_clock(THREE_YEARS_LATER))
    capsys.readouterr()

    assert cli.main(["purge"]) == 0

    output = capsys.readouterr()
    assert count_rows(tmp_path, "SELECT count(*) FROM item") == 0
    assert count_rows(tmp_path, "SELECT count(*) FROM raw_data") == 0
    assert not raw_path.exists()
    assert not older_log.exists()
    assert list(tmp_path.glob("journals/import-journal-*.jsonl")) == []
    for line in (
        "purge started",
        r"base purge: [1-9]\d* items, 0 trend rows, .*",
        (
            "raw purge: 1 collections older than 6 months deleted, 0 of them never imported,"
            r" 0 kept \(a folder or a link inside\)"
        ),
        "registry purge: 1 rows deleted",
        "logs and journals purge: 2 files older than 6 months deleted",
        r"purge finished in \d+ s",
    ):
        assert re.search(
            rf"^{LOG_LINE_DATE} INFO k_b[.a-z_]*: {line}$", output.err, re.MULTILINE
        )


def test_purge_keeps_only_the_last_extract_and_catalog_imported(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    older_extract, older_catalog, last_extract, last_catalog = write_state_catalogs(
        tmp_path
    )
    assert cli.main(["import"]) == 0
    capsys.readouterr()

    exit_code = cli.main(["purge"])

    assert exit_code == 0
    assert "raw purge: 2 superseded files deleted" in capsys.readouterr().err
    assert (older_extract.exists(), older_catalog.exists()) == (False, False)
    assert (last_extract.exists(), last_catalog.exists()) == (True, True)


def test_purge_refuses_a_missing_database_does_not_create_it_and_exits_2(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    (tmp_path / "raw").mkdir()

    exit_code = cli.main(["purge"])

    assert exit_code == 2
    assert "; create it with kb create-db" in capsys.readouterr().err
    assert not (tmp_path / "k-b.sqlite").exists()


def test_a_failed_purge_without_a_reason_names_its_type_only(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    write_state_catalogs(tmp_path)
    assert cli.main(["import"]) == 0

    def fail_to_delete(store, key):
        raise OSError("raised by code, without an errno")

    monkeypatch.setattr(RawStore, "delete", fail_to_delete)

    assert cli.main(["purge"]) == 1
    error_output = capsys.readouterr().err
    assert "purge failed: OSError; run kb purge again" in error_output
    assert "None" not in error_output


def test_a_failed_purge_exits_1_names_no_raw_file_and_the_next_purge_purges(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    older_extract, older_catalog, _, _ = write_state_catalogs(tmp_path)
    assert cli.main(["import"]) == 0
    capsys.readouterr()

    def fail_to_delete(store, key):
        raise PermissionError(13, "Permission denied", str(tmp_path / key))

    with monkeypatch.context() as patch:
        patch.setattr(RawStore, "delete", fail_to_delete)
        assert cli.main(["purge"]) == 1

    error_output = capsys.readouterr().err
    assert (
        "purge failed: PermissionError (Permission denied); run kb purge again"
        in error_output
    )
    assert "2026-10-05T093000Z" not in error_output
    assert older_extract.exists()
    assert count_rows(tmp_path, "SELECT count(*) FROM raw_data") == 4

    assert cli.main(["purge"]) == 0
    assert (older_extract.exists(), older_catalog.exists()) == (False, False)


def test_a_failed_purge_of_the_base_stops_the_purges_after_it(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    raw_path = copy_fixture(
        tmp_path / "raw", "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml"
    )
    assert cli.main(["import"]) == 0
    monkeypatch.setattr(purge_command, "datetime", make_clock(THREE_YEARS_LATER))

    def fail_to_purge(*arguments):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(all_purges, "purge_expired_rows", fail_to_purge)

    assert cli.main(["purge"]) == 1
    assert (
        "purge failed: OperationalError; run kb purge again" in capsys.readouterr().err
    )
    assert raw_path.exists()
    assert count_rows(tmp_path, "SELECT count(*) FROM item") > 0
