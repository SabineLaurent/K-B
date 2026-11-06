"""The errors of PostgreSQL in what kb writes: an entry refused in the import journal, an error that
stops the import in the log, each by its class, its SQLSTATE and its names, never by a message of
PostgreSQL, which may quote the value refused (a title, an author, the text of a clip)."""

import psycopg
import pytest
from etl.test_transform import copy_fixture

from k_b import cli
from k_b.commands.exit_codes import ExitCode
from k_b.database import writing
from k_b.database.location import DATABASE_URL_VARIABLE

pytestmark = pytest.mark.postgresql

# Two values PostgreSQL quotes in its message: a number beyond 64 bits read as text (22003, an
# entry refused), and a text that is no number (22P02, an error that stops the import).
OUT_OF_RANGE_MARKER = "987654321098765432109876543210"
INVALID_NUMBER_MARKER = "marker-of-the-test"


def prepare_import(monkeypatch, tmp_path, postgresql_base, statement, marker):
    """A base and a CISA KEV catalog, whose writer runs the statement with the marker first."""
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, postgresql_base.value)
    cli.main(["create-db"])
    copy_fixture(tmp_path / "raw", "cisa_kev_extract.csv", "cisa_kev", "csv")
    write_vulnerability = writing.WRITER_BY_KIND["vulnerability"]

    def write_with_the_marker(connection, item, raw_data_id):
        connection.execute(statement, (marker,))
        return write_vulnerability(connection, item, raw_data_id)

    monkeypatch.setitem(writing.WRITER_BY_KIND, "vulnerability", write_with_the_marker)


def test_an_entry_refused_by_postgresql_reaches_the_journal_without_the_value_refused(
    monkeypatch, tmp_path, capsys, postgresql_base
):
    prepare_import(
        monkeypatch,
        tmp_path,
        postgresql_base,
        "SELECT CAST(? AS bigint)",
        OUT_OF_RANGE_MARKER,
    )

    assert cli.main(["import"]) == ExitCode.SUCCEEDED

    [journal_path] = tmp_path.glob("journals/import-journal-*.jsonl")
    journal = journal_path.read_text("utf-8")
    assert "NumericValueOutOfRange 22003" in journal
    assert OUT_OF_RANGE_MARKER not in journal
    assert OUT_OF_RANGE_MARKER not in capsys.readouterr().err
    assert OUT_OF_RANGE_MARKER not in (tmp_path / "logs" / "kb.log").read_text()


def test_an_error_of_postgresql_that_stops_the_import_reaches_the_log_without_its_value(
    monkeypatch, tmp_path, capsys, postgresql_base
):
    prepare_import(
        monkeypatch,
        tmp_path,
        postgresql_base,
        "SELECT CAST(? AS bigint)",
        INVALID_NUMBER_MARKER,
    )

    assert cli.main(["import"]) == ExitCode.FAILED

    error_output = capsys.readouterr().err
    assert "ERROR k_b.cli: InvalidTextRepresentation 22P02" in error_output
    assert INVALID_NUMBER_MARKER not in error_output
    assert INVALID_NUMBER_MARKER not in (tmp_path / "logs" / "kb.log").read_text()


def test_the_message_of_postgresql_quotes_the_markers_the_tests_look_for(
    postgresql_base,
):
    # Without it, the two tests above would pass on a message that never quoted the value.
    connection = psycopg.connect(postgresql_base.value)
    try:
        for marker, error_class in (
            (OUT_OF_RANGE_MARKER, psycopg.errors.NumericValueOutOfRange),
            (INVALID_NUMBER_MARKER, psycopg.errors.InvalidTextRepresentation),
        ):
            with pytest.raises(error_class) as raised:
                connection.execute("SELECT CAST(%s AS bigint)", (marker,))
            assert marker in raised.value.diag.message_primary
            connection.rollback()
    finally:
        connection.close()
