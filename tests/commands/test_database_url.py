"""kb create-db and kb import read KB_DATABASE_URL: a value refused stops them before they start,
and a URL libpq cannot read never reaches the log, its password with it."""

import pytest

from k_b import cli
from k_b.commands.exit_codes import ExitCode
from k_b.database.location import DATABASE_URL_VARIABLE

PASSWORD = "S3cret-of-the-test"  # noqa: S105 — a marker the test looks for, no secret
# libpq stops at the [ of an IPv6 host never closed, and its error quotes the whole URL.
MALFORMED_URL = f"postgresql://kb:{PASSWORD}@[::1/kb"


@pytest.mark.parametrize("command", ["create-db", "import"])
def test_an_empty_kb_database_url_stops_the_command_before_it_starts(
    monkeypatch, tmp_path, capsys, command
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, "")

    assert cli.main([command]) == ExitCode.NOT_STARTED
    assert f"{DATABASE_URL_VARIABLE} is neither" in capsys.readouterr().err
    assert not (tmp_path / "k-b.sqlite").exists()


@pytest.mark.parametrize("command", ["create-db", "import"])
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


@pytest.mark.parametrize("command", ["create-db", "import"])
def test_a_url_libpq_cannot_read_fails_without_its_password_in_the_log(
    monkeypatch, tmp_path, capsys, command
):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DATABASE_URL_VARIABLE, MALFORMED_URL)

    assert cli.main([command]) == ExitCode.FAILED
    assert PASSWORD not in capsys.readouterr().err
    assert PASSWORD not in (tmp_path / "logs" / "kb.log").read_text()
