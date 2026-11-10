"""kb import: the raw items written into the base and the import journal; no purge."""

import re
import shutil
import sqlite3
from datetime import UTC, datetime

from commands.cli_helpers import LOG_LINE_DATE
from etl.test_transform import FIXTURES_DIR

from k_b import cli
from k_b.commands import (
    import_command,
)
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl import pipeline


def test_import_writes_the_raw_items_into_the_database(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    capsys.readouterr()

    exit_code = cli.main(["import"])

    assert exit_code == 0
    output = capsys.readouterr()
    (journal_path,) = tmp_path.glob("journals/import-journal-*.jsonl")
    assert re.fullmatch(
        r"import-journal-\d{4}-\d{2}-\d{2}T\d{6}Z\.jsonl", journal_path.name
    )
    assert output.out == (
        "\nimport: 0 raw read, 0 written, 0 trend rows, 0 left out, 0 rejected, 0 withdrawn\n\n"
    )
    for line in (
        "import started",
        r"import finished in \d+ s",
        re.escape(f"import journal kept: '{journal_path.name}'"),
    ):
        assert re.search(
            rf"^{LOG_LINE_DATE} INFO k_b\.cli: {line}$", output.err, re.MULTILINE
        )


def test_import_writes_the_raw_rankings_of_gh_archive_into_the_trend_table(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    source_dir = tmp_path / "raw" / "automated_watch" / "gh_archive"
    source_dir.mkdir(parents=True)
    shutil.copyfile(
        FIXTURES_DIR / "gh_archive_extract.json", source_dir / "2026-10-11T153130Z.json"
    )

    exit_code = cli.main(["import"])

    assert exit_code == 0
    assert capsys.readouterr().out.endswith(
        "\nimport: 1 raw read, 0 written, 5 trend rows, 0 left out, 0 rejected, 0 withdrawn\n\n"
    )
    connection = sqlite3.connect(tmp_path / "k-b.sqlite")
    assert connection.execute("SELECT count(*) FROM trend").fetchone() == (5,)
    connection.close()


def write_state_catalogs(data_dir):
    """Two extracts of Zotero and two catalogs of CISA KEV, not imported yet."""
    paths = []
    for collection in ("2026-10-05T093000Z", "2026-10-06T093000Z"):
        extract_path = (
            data_dir / "raw" / "selected_library" / "zotero" / f"{collection}.json"
        )
        extract_path.parent.mkdir(parents=True, exist_ok=True)
        extract_path.write_bytes(b"[]\n")
        catalog_dir = data_dir / "raw" / "automated_watch" / "cisa_kev"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = catalog_dir / f"{collection}.csv"
        shutil.copyfile(FIXTURES_DIR / "cisa_kev_extract.csv", catalog_path)
        paths += [extract_path, catalog_path]
    return paths


def test_import_deletes_no_raw_file_and_runs_no_purge(monkeypatch, tmp_path, capsys):
    """The superseded catalogs stay until kb purge runs."""
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    paths = write_state_catalogs(tmp_path)
    capsys.readouterr()

    assert cli.main(["import"]) == 0

    assert all(path.exists() for path in paths)
    assert "purge" not in capsys.readouterr().err


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 12, 15, 49, 3, 250000, tzinfo=UTC)


def test_import_refuses_to_rewrite_the_log_of_its_second_and_exits_2(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])
    monkeypatch.setattr(import_command, "datetime", FrozenDatetime)
    journal_path = tmp_path / "journals" / "import-journal-2026-10-12T154903Z.jsonl"
    journal_path.parent.mkdir(exist_ok=True)
    journal_path.write_text("earlier import\n")

    exit_code = cli.main(["import"])

    assert exit_code == 2
    assert str(journal_path) in capsys.readouterr().err
    assert journal_path.read_text() == "earlier import\n"


def test_import_refuses_a_missing_database_and_does_not_create_it(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))

    exit_code = cli.main(["import"])

    assert exit_code == 2
    assert "kb create-db" in capsys.readouterr().err
    assert not (tmp_path / "k-b.sqlite").exists()


def test_import_reports_a_failed_import_and_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    def fail_to_import(
        reading,
        trend_reading,
        database_path,
        journal_path,
        imported_at,
        tracked_repositories,
    ):
        raise sqlite3.IntegrityError("CHECK constraint failed: publication")

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "ERROR k_b.cli: IntegrityError: CHECK constraint failed: publication"
        in capsys.readouterr().err
    )


def test_import_reports_a_source_missing_from_the_database_and_exits_1(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    def fail_to_import(
        reading,
        trend_reading,
        database_path,
        journal_path,
        imported_at,
        tracked_repositories,
    ):
        raise UnknownSourceError("source_code not in the source table: cisa_kev")

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "ERROR k_b.cli: UnknownSourceError: source_code not in the source table: cisa_kev"
        in capsys.readouterr().err
    )


def test_import_reports_a_kind_without_table_and_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cli.main(["create-db"])

    def fail_to_import(
        reading,
        trend_reading,
        database_path,
        journal_path,
        imported_at,
        tracked_repositories,
    ):
        raise KindWithoutTableError(
            "kind without a table in the base: newsletter_article"
        )

    monkeypatch.setattr(pipeline, "import_items", fail_to_import)

    exit_code = cli.main(["import"])

    assert exit_code == 1
    assert (
        "ERROR k_b.cli: KindWithoutTableError: kind without a table in the base: newsletter_article"
        in capsys.readouterr().err
    )
