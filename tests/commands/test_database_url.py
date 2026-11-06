"""kb create-db, kb migrate-database and kb import read KB_DATABASE_URL: a value refused stops them
before they start, and a URL libpq cannot read never reaches the log, its password with it."""

import pytest

from k_b import cli
from k_b.commands.exit_codes import ExitCode
from k_b.database.location import DATABASE_URL_VARIABLE

PASSWORD = "S3cret-of-the-test"  # noqa: S105 — a marker the test looks for, no secret
# libpq stops at the [ of an IPv6 host never closed, and its error quotes the whole URL.
MALFORMED_URL = f"postgresql://kb:{PASSWORD}@[::1/kb"


@pytest.mark.parametrize("command", ["create-db", "migrate-database", "import"])
def test_an_empty_kb_database_url_stops_the_command_before_it_starts(
    monkeypatch, tmp_path, capsys, command
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, "")

    assert cli.main([command]) == ExitCode.NOT_STARTED
    assert f"{DATABASE_URL_VARIABLE} is neither" in capsys.readouterr().err
    assert not (tmp_path / "k-b.sqlite").exists()


@pytest.mark.parametrize("command", ["create-db", "migrate-database", "import"])
def test_a_variable_libpq_reads_stops_the_command_before_it_starts(
    monkeypatch, tmp_path, capsys, command
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, "postgresql://kb@127.0.0.1:1/kb")
    monkeypatch.setenv("PGPASSWORD", PASSWORD)

    assert cli.main([command]) == ExitCode.NOT_STARTED
    log = capsys.readouterr().err
    assert "PGPASSWORD set" in log
    assert PASSWORD not in log


@pytest.mark.parametrize(
    "password",
    [f"Ab3/{PASSWORD}/Q=", f"Ab3{chr(0xFF0F)}{PASSWORD}"],
    ids=["slash", "fullwidth slash"],
)
def test_kb_create_db_never_shows_a_part_of_a_password_the_url_does_not_encode(
    monkeypatch, tmp_path, capsys, password
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        DATABASE_URL_VARIABLE, f"postgresql://kb:{password}@127.0.0.1:1/kb"
    )

    cli.main(["create-db"])

    output = capsys.readouterr()
    assert PASSWORD not in output.out
    assert PASSWORD not in output.err
    assert PASSWORD not in (tmp_path / "logs" / "kb.log").read_text()


@pytest.mark.parametrize("command", ["create-db", "migrate-database", "import"])
def test_a_url_libpq_cannot_read_is_refused_without_its_password_in_the_log(
    monkeypatch, tmp_path, capsys, command
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, MALFORMED_URL)

    assert cli.main([command]) == ExitCode.NOT_STARTED
    error_output = capsys.readouterr().err
    assert "ERROR k_b.cli: KB_DATABASE_URL is not a URL libpq reads" in error_output
    assert "Traceback" not in error_output
    assert PASSWORD not in error_output
    assert PASSWORD not in (tmp_path / "logs" / "kb.log").read_text()
