import json
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from k_b.sources import zotero
from k_b.sources.zotero import (
    ZoteroChangedDuringCopyError,
    ZoteroCopyInconsistentError,
    ZoteroQueryFailedError,
    ZoteroSource,
)

LIBRARY_SCRIPT = Path(__file__).parent.parent / "fixtures" / "zotero_extract.sql"

PAPER_WITH_HIGHLIGHTS = {
    "key": "AAAAAAA1",
    "item_type": "preprint",
    "title": "Prompt injection through tool results",
    "date": "2026-09-28 2026-09-28",
    "date_added": "2026-10-01 08:15:00",
    "url": "http://arxiv.org/abs/2609.00001",
    "archive_id": "arXiv:2609.00001",
    "authors": [
        {"first_name": "Ada", "last_name": "Example"},
        {"first_name": "Blaise", "last_name": "Sample"},
    ],
    "tags": [
        {"name": "Computer Science - Cryptography and Security", "type": 1},
        {"name": "to read", "type": 0},
    ],
    "pdfs": [
        {
            "key": "PDFAAAA1",
            "path": "storage:Example and Sample - 2026 - Prompt injection.pdf",
        }
    ],
    "highlights": [
        {
            "key": "ANNOTAA2",
            "pdf_key": "PDFAAAA1",
            "text": "A highlighted sentence on the first page.",
            "comment": "A comment on it.",
            "page_label": "1",
            "date_added": "2026-10-05 08:42:30",
        },
        {
            "key": "ANNOTAA1",
            "pdf_key": "PDFAAAA1",
            "text": "A highlighted sentence on the third page.",
            "comment": None,
            "page_label": "3",
            "date_added": "2026-10-05 08:50:00",
        },
    ],
}
PAPER_WITHOUT_ANYTHING_ATTACHED = {
    "key": "BBBBBBB2",
    "item_type": "preprint",
    "title": "A paper saved without its PDF",
    "date": "2026-09-30 2026-09-30",
    "date_added": "2026-10-03 17:40:12",
    "url": "http://arxiv.org/abs/2609.00002",
    "archive_id": "arXiv:2609.00002",
    "authors": [],
    "tags": [],
    "pdfs": [],
    "highlights": [],
}


@pytest.fixture(autouse=True)
def temporary_root(tmp_path, monkeypatch):
    """Where the source makes its temporary copy: a folder each test can look into."""
    root = tmp_path / "temporary"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


@pytest.fixture
def zotero_dir(tmp_path):
    """A Zotero data directory with the fabricated library, in WAL mode, closed cleanly."""
    directory = tmp_path / "Zotero"
    directory.mkdir()
    run_on_library(directory, LIBRARY_SCRIPT.read_text())
    return directory


def run_on_library(zotero_dir, script):
    connection = sqlite3.connect(zotero_dir / "zotero.sqlite")
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(script)
    finally:
        connection.close()


def extract(zotero_dir, last_collected_at=None):
    raw_extract = ZoteroSource(zotero_dir).fetch(last_collected_at)
    return json.loads(raw_extract)


def read_files(folder):
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}


def test_a_paper_is_extracted_with_its_authors_tags_pdf_and_highlights_in_order(
    zotero_dir,
):
    assert extract(zotero_dir)[0] == PAPER_WITH_HIGHLIGHTS


def test_a_paper_with_nothing_attached_is_extracted_with_empty_lists(zotero_dir):
    assert extract(zotero_dir)[1] == PAPER_WITHOUT_ANYTHING_ATTACHED


def test_only_the_documents_of_the_user_library_out_of_the_trash_are_extracted(
    zotero_dir,
):
    """Left out: the web page in the trash and the paper of a group library; and with them
    the underline, the note, the editor, the abstract, the highlight and the PDF in the trash,
    the linked PDF and its absolute path, the highlight of a web page snapshot."""
    assert extract(zotero_dir) == [
        PAPER_WITH_HIGHLIGHTS,
        PAPER_WITHOUT_ANYTHING_ATTACHED,
    ]


def test_the_extract_is_utf8_json_and_the_same_bytes_for_the_same_library(zotero_dir):
    run_on_library(
        zotero_dir, "UPDATE itemDataValues SET value = 'Résumé' WHERE valueID = 6"
    )
    source = ZoteroSource(zotero_dir)

    first_extract = source.fetch(None)

    assert "Résumé".encode() in first_extract
    assert source.fetch(None) == first_extract


def test_what_zotero_has_only_written_to_its_write_ahead_log_is_extracted(zotero_dir):
    # Zotero running: its connection stays open, and its last writes are only in the -wal.
    writer = sqlite3.connect(zotero_dir / "zotero.sqlite")
    try:
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            "UPDATE itemDataValues SET value = 'A title changed in the log'"
            " WHERE valueID = 6"
        )
        writer.commit()
        assert (zotero_dir / "zotero.sqlite-wal").stat().st_size > 0

        documents = extract(zotero_dir)
    finally:
        writer.close()

    assert documents[1]["title"] == "A title changed in the log"


def test_a_library_without_a_write_ahead_log_file_is_extracted(zotero_dir):
    (zotero_dir / "zotero.sqlite-wal").unlink(missing_ok=True)
    (zotero_dir / "zotero.sqlite-shm").unlink(missing_ok=True)

    assert len(extract(zotero_dir)) == 2


def test_the_original_is_left_byte_for_byte_and_nothing_is_created_next_to_it(
    zotero_dir,
):
    files_before = read_files(zotero_dir)

    extract(zotero_dir)

    assert read_files(zotero_dir) == files_before


def test_the_temporary_copy_is_deleted_after_an_extraction(zotero_dir, temporary_root):
    extract(zotero_dir)

    assert list(temporary_root.iterdir()) == []


def test_the_temporary_copy_is_deleted_after_a_failure(zotero_dir, temporary_root):
    run_on_library(zotero_dir, "DROP TABLE itemAnnotations")

    with pytest.raises(ZoteroQueryFailedError):
        extract(zotero_dir)

    assert list(temporary_root.iterdir()) == []


def test_the_copy_is_made_in_a_folder_named_after_k_b_and_opened_read_only(
    zotero_dir, temporary_root, monkeypatch
):
    opened = []
    connect = sqlite3.connect

    def record_connection(database, **options):
        opened.append((database, options))
        return connect(database, **options)

    monkeypatch.setattr(zotero.sqlite3, "connect", record_connection)

    extract(zotero_dir)

    [(database, options)] = opened
    assert database.startswith((temporary_root / "kb-zotero-").as_uri())
    assert database.endswith("/zotero.sqlite?mode=ro")
    assert options == {"uri": True}


def test_a_copy_whose_integrity_check_reports_a_problem_is_refused(zotero_dir):
    # An index declared on another column than the one it was built on: SQLite opens the
    # base, and integrity_check reports the rows missing from the index.
    run_on_library(
        zotero_dir,
        "CREATE INDEX items_key ON items (key);"
        "PRAGMA writable_schema = ON;"
        "UPDATE sqlite_schema SET sql = 'CREATE INDEX items_key ON items (dateAdded)'"
        " WHERE name = 'items_key';",
    )

    with pytest.raises(ZoteroCopyInconsistentError, match="missing from index"):
        extract(zotero_dir)


def test_a_copy_that_integrity_check_cannot_read_is_refused(zotero_dir):
    (zotero_dir / "zotero.sqlite-wal").unlink(missing_ok=True)
    database_path = zotero_dir / "zotero.sqlite"
    database_path.write_bytes(
        database_path.read_bytes()[: database_path.stat().st_size // 2]
    )

    with pytest.raises(
        ZoteroCopyInconsistentError,
        match="integrity_check raised DatabaseError: 'database disk image is malformed'",
    ):
        extract(zotero_dir)


def change_during_the_copy(monkeypatch, copied_file_name, change):
    """Run change right after the file of that name was copied."""
    copyfile = shutil.copyfile

    def copy_then_change(source, destination):
        copyfile(source, destination)
        if Path(source).name == copied_file_name:
            change()

    monkeypatch.setattr(zotero.shutil, "copyfile", copy_then_change)


def test_a_main_file_written_during_the_copy_is_refused(zotero_dir, monkeypatch):
    database_path = zotero_dir / "zotero.sqlite"
    (zotero_dir / "zotero.sqlite-wal").write_bytes(b"")
    change_during_the_copy(
        monkeypatch,
        "zotero.sqlite-wal",
        lambda: os.utime(database_path, ns=(1, 1)),
    )

    with pytest.raises(ZoteroChangedDuringCopyError):
        extract(zotero_dir)


def test_a_write_ahead_log_written_during_the_copy_is_refused(zotero_dir, monkeypatch):
    wal_path = zotero_dir / "zotero.sqlite-wal"
    wal_path.write_bytes(b"")
    change_during_the_copy(
        monkeypatch, "zotero.sqlite-wal", lambda: wal_path.write_bytes(b"more")
    )

    with pytest.raises(ZoteroChangedDuringCopyError):
        extract(zotero_dir)


def test_a_write_ahead_log_that_appears_during_the_copy_is_refused(
    zotero_dir, monkeypatch
):
    wal_path = zotero_dir / "zotero.sqlite-wal"
    wal_path.unlink(missing_ok=True)
    change_during_the_copy(
        monkeypatch, "zotero.sqlite", lambda: wal_path.write_bytes(b"")
    )

    with pytest.raises(ZoteroChangedDuringCopyError):
        extract(zotero_dir)


def test_a_library_without_a_table_the_query_reads_fails_naming_the_table(zotero_dir):
    run_on_library(zotero_dir, "DROP TABLE itemAnnotations")

    with pytest.raises(ZoteroQueryFailedError, match="no such table: itemAnnotations"):
        extract(zotero_dir)


def test_a_library_without_a_column_the_query_reads_fails_naming_the_column(
    zotero_dir,
):
    run_on_library(zotero_dir, "ALTER TABLE itemAnnotations DROP COLUMN pageLabel")

    with pytest.raises(
        ZoteroQueryFailedError, match="no such column: itemAnnotations.pageLabel"
    ):
        extract(zotero_dir)


def test_a_value_sqlite_cannot_put_in_json_fails_with_the_name_sqlite_gives_the_error(
    zotero_dir,
):
    run_on_library(
        zotero_dir, "UPDATE itemAnnotations SET text = x'00ff' WHERE itemID = 4"
    )

    with pytest.raises(ZoteroQueryFailedError) as failure:
        extract(zotero_dir)

    assert str(failure.value) == "OperationalError (SQLITE_ERROR)"


@pytest.mark.parametrize(
    ("error", "description"),
    [
        (
            # What a SQLite older than 3.44 answers to ORDER BY in an aggregate.
            sqlite3.OperationalError('near "ORDER": syntax error'),
            'near "ORDER": syntax error',
        ),
        (
            sqlite3.DatabaseError("database disk image is malformed"),
            "DatabaseError",
        ),
        (
            sqlite3.OperationalError(
                "Could not decode to UTF-8 column 'title' with text 'A private title'"
            ),
            "OperationalError",
        ),
    ],
)
def test_a_query_error_is_described_without_what_sqlite_quotes_of_the_library(
    error, description
):
    assert zotero.describe_query_error(error) == description


def test_a_text_that_is_not_utf8_fails_without_its_content_in_the_error(
    zotero_dir,
):
    # A text that is not UTF-8: sqlite3 quotes it in its message, which the log must not get.
    run_on_library(
        zotero_dir,
        "UPDATE itemDataValues SET value = CAST(x'5365637265742074697472653a20ff' AS TEXT)"
        " WHERE valueID = 6",
    )

    with pytest.raises(ZoteroQueryFailedError) as failure:
        extract(zotero_dir)

    assert str(failure.value) == "OperationalError"
    assert failure.value.__cause__ is None
    assert failure.value.__suppress_context__


def test_a_folder_without_the_zotero_database_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract(tmp_path)


def test_a_library_not_modified_since_the_last_collection_is_not_copied(
    zotero_dir, monkeypatch
):
    def refuse_to_copy(source, destination):
        raise AssertionError(f"copied {source}")

    monkeypatch.setattr(zotero.shutil, "copyfile", refuse_to_copy)
    last_collected_at = datetime.now(UTC) + timedelta(minutes=1)

    assert ZoteroSource(zotero_dir).fetch(last_collected_at) is None


def test_a_library_modified_since_the_last_collection_is_extracted(zotero_dir):
    last_collected_at = datetime.now(UTC) - timedelta(minutes=1)

    assert len(extract(zotero_dir, last_collected_at)) == 2


def test_a_library_whose_only_recent_change_is_in_its_write_ahead_log_is_extracted(
    zotero_dir,
):
    last_collected_at = datetime.now(UTC) + timedelta(minutes=1)
    after_it = int((last_collected_at + timedelta(minutes=1)).timestamp() * 1e9)
    wal_path = zotero_dir / "zotero.sqlite-wal"
    wal_path.write_bytes(b"")
    os.utime(wal_path, ns=(after_it, after_it))

    assert len(extract(zotero_dir, last_collected_at)) == 2


def test_the_log_gives_two_counts_and_no_author_title_or_highlight(zotero_dir, caplog):
    with caplog.at_level(logging.INFO, logger="k_b.sources.zotero"):
        extract(zotero_dir)

    assert caplog.messages == ["zotero: 2 documents, 2 highlights extracted"]


def test_zotero_is_stored_in_the_library_the_user_selected():
    source = ZoteroSource(Path("anywhere"))

    assert (source.acquisition_dir_name, source.name, source.extension) == (
        "selected_library",
        "zotero",
        "json",
    )
