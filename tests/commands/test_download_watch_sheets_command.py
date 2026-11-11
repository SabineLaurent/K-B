"""kb download-watch-sheets, run on the Mac by make download-watch-sheets: each sheet of the container
watch that veille lacks is copied there; a sheet there is never downloaded nor replaced, and a blob
that is not a sheet never reaches the vault, the sheets beside it copied all the same."""

import gzip
import logging
from datetime import UTC, datetime

import pytest
from azure.core.credentials import AccessToken
from azure.identity import CredentialUnavailableError
from jobs.storage_fakes import (
    TEST_ACCOUNT_URL,
    TEST_TOKEN,
    FakeBlob,
    FakeContainer,
    FakeTransport,
    answer_error,
    remove_online_variables,
)

from k_b import cli
from k_b.commands import download_watch_sheets_command
from k_b.commands.download_watch_sheets_command import WATCH_SHEET_FOLDERS
from k_b.commands.sigterm import COMMANDS_STOPPED_BY_SIGTERM
from k_b.core.config import DIGEST_SUBJECTS
from k_b.etl.source_kinds import TOPS
from k_b.exchange.storage import open_container_client
from k_b.post import digest_sheets, top_sheets, trend_report_sheets

ExitCode = cli.ExitCode
COMMAND = "download-watch-sheets"
PUBLISHED_ON = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
MODELS_SHEET = "models/2026-11-10.md"
TRENDS_SHEET = "tendances/2026-11-10.md"
TOP_SHEET = "tops/most_starred/2026-11-10.md"
# A name that climbs out of veille, and the file it would write there.
CLIMBING_NAME = "models/../../escaped.md"


class FakeCliCredential:
    """The credential of az login, without az: the token of the tests, or the error az gives when
    no account is logged in."""

    def __init__(self, error=None):
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        pass

    def get_token(self, *scopes, **kwargs):
        if self.error is not None:
            raise self.error
        return AccessToken(TEST_TOKEN, 4102444800)


@pytest.fixture
def vault_dir(monkeypatch, data_and_vault_dirs):
    """The settings of the Mac: the account of the exchange storage and the vault."""
    remove_online_variables(monkeypatch)
    monkeypatch.setenv("KB_EXCHANGE_BLOB_URL", TEST_ACCOUNT_URL)
    return data_and_vault_dirs[1]


def simulate(monkeypatch, handle, credential=None):
    """The account of az login and the container watch, answered by handle."""
    monkeypatch.setattr(
        download_watch_sheets_command,
        "build_cli_credential",
        lambda: credential or FakeCliCredential(),
    )

    def open_fake(account_url, container_name, credential):
        assert (account_url, container_name) == (TEST_ACCOUNT_URL, "watch")
        return open_container_client(
            account_url, container_name, credential, FakeTransport(handle)
        )

    monkeypatch.setattr(
        download_watch_sheets_command, "open_container_client", open_fake
    )


def make_watch(monkeypatch, blobs):
    container = FakeContainer(
        "watch",
        {name: FakeBlob(content, PUBLISHED_ON) for name, content in blobs.items()},
    )
    simulate(monkeypatch, container.handle)
    return container


def download():
    return cli.main([COMMAND])


def test_the_folders_of_watch_are_those_the_writers_of_veille_write_in(tmp_path):
    veille_dir = tmp_path / "veille"
    written_in = (
        [
            digest_sheets.find_sheets_dir(tmp_path, subject.name)
            for subject in DIGEST_SUBJECTS
        ]
        + [top_sheets.find_sheets_dir(tmp_path, top) for top in TOPS]
        + [trend_report_sheets.find_sheets_dir(tmp_path)]
    )

    assert {
        folder.relative_to(veille_dir).as_posix() for folder in written_in
    } == WATCH_SHEET_FOLDERS


def test_each_sheet_of_watch_is_copied_to_veille(monkeypatch, vault_dir, capsys):
    make_watch(
        monkeypatch,
        {MODELS_SHEET: b"# models", TRENDS_SHEET: b"# trends", TOP_SHEET: b"# top"},
    )

    exit_code = download()

    assert exit_code == ExitCode.SUCCEEDED
    assert (vault_dir / "veille" / MODELS_SHEET).read_bytes() == b"# models"
    assert (vault_dir / "veille" / TRENDS_SHEET).read_bytes() == b"# trends"
    assert (vault_dir / "veille" / TOP_SHEET).read_bytes() == b"# top"
    assert "3 blobs listed: 3 copied, 0 already there" in capsys.readouterr().out


def test_a_second_download_asks_no_blob_and_copies_nothing(
    monkeypatch, vault_dir, capsys
):
    container = make_watch(
        monkeypatch, {MODELS_SHEET: b"# models", TRENDS_SHEET: b"# trends"}
    )
    download()
    downloaded_before = container.downloaded_names()

    exit_code = download()

    assert exit_code == ExitCode.SUCCEEDED
    assert container.downloaded_names() == downloaded_before
    assert "2 blobs listed: 0 copied, 2 already there" in capsys.readouterr().out


def test_a_sheet_changed_on_the_mac_is_neither_downloaded_nor_replaced(
    monkeypatch, vault_dir
):
    container = make_watch(monkeypatch, {MODELS_SHEET: b"# models"})
    sheet_path = vault_dir / "veille" / MODELS_SHEET
    sheet_path.parent.mkdir(parents=True)
    sheet_path.write_bytes(b"# models, with my notes")

    exit_code = download()

    assert exit_code == ExitCode.SUCCEEDED
    assert sheet_path.read_bytes() == b"# models, with my notes"
    assert container.downloaded_names() == []


def test_a_trapped_name_is_refused_by_its_place_and_the_sheets_beside_it_are_copied(
    monkeypatch, vault_dir, tmp_path, caplog
):
    container = make_watch(
        monkeypatch, {MODELS_SHEET: b"# models", CLIMBING_NAME: b"# escaped"}
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.PARTIAL_FAILURE
    assert (vault_dir / "veille" / MODELS_SHEET).read_bytes() == b"# models"
    assert list(tmp_path.rglob("escaped.md")) == []
    assert CLIMBING_NAME not in container.downloaded_names()
    assert "blob 1 of 2 refused: sheet_name_refused" in caplog.text
    assert "escaped" not in caplog.text


def test_a_watch_of_trapped_names_only_fails_with_1(monkeypatch, vault_dir, tmp_path):
    make_watch(monkeypatch, {CLIMBING_NAME: b"# escaped"})

    assert download() == ExitCode.FAILED
    assert list(tmp_path.rglob("escaped.md")) == []


def test_a_sheet_of_a_folder_unknown_is_left_aside_and_kb_exits_with_0(
    monkeypatch, vault_dir, capsys
):
    make_watch(monkeypatch, {"a_subject_retired/2026-11-10.md": b"# retired"})

    assert download() == ExitCode.SUCCEEDED
    assert not (vault_dir / "veille").exists()
    assert "1 left aside (sheet_folder_unknown: 1)" in capsys.readouterr().out


def test_veille_as_a_symbolic_link_is_refused_and_nothing_is_written_through_it(
    monkeypatch, vault_dir, tmp_path, caplog
):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille").symlink_to(elsewhere)
    make_watch(monkeypatch, {MODELS_SHEET: b"# models"})

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.FAILED
    assert list(elsewhere.iterdir()) == []
    assert "vault_link_refused: veille is a symbolic link" in caplog.text


def test_a_folder_of_veille_as_a_symbolic_link_is_refused_the_others_copied(
    monkeypatch, vault_dir, tmp_path
):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille").mkdir()
    (vault_dir / "veille" / "models").symlink_to(elsewhere)
    make_watch(monkeypatch, {MODELS_SHEET: b"# models", TRENDS_SHEET: b"# trends"})

    assert download() == ExitCode.PARTIAL_FAILURE
    assert list(elsewhere.iterdir()) == []
    assert (vault_dir / "veille" / TRENDS_SHEET).read_bytes() == b"# trends"


def test_a_file_in_place_of_a_folder_of_veille_fails_its_sheets_by_their_errno(
    monkeypatch, vault_dir, caplog
):
    (vault_dir / "veille").mkdir()
    (vault_dir / "veille" / "models").write_bytes(b"not a folder")
    make_watch(monkeypatch, {MODELS_SHEET: b"# models"})

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.FAILED
    assert (vault_dir / "veille" / "models").read_bytes() == b"not a folder"
    assert "blob 1 of 1 not written: ENOTDIR" in caplog.text
    assert str(vault_dir) not in caplog.text


def test_a_temporary_file_left_fails_its_sheet_by_its_path_in_the_vault(
    monkeypatch, vault_dir, caplog
):
    temporary_path = vault_dir / "veille" / "models" / ".2026-11-10.md.tmp"
    temporary_path.parent.mkdir(parents=True)
    temporary_path.write_bytes(b"# half")
    make_watch(monkeypatch, {MODELS_SHEET: b"# models", TRENDS_SHEET: b"# trends"})

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.PARTIAL_FAILURE
    assert not (vault_dir / "veille" / MODELS_SHEET).exists()
    assert (vault_dir / "veille" / TRENDS_SHEET).read_bytes() == b"# trends"
    assert (
        "temporary_file_found: veille/models/.2026-11-10.md.tmp is there" in caplog.text
    )


@pytest.mark.parametrize(
    "content",
    [b"# models" + bytes([0]), gzip.compress(b"# models")],
    ids=["nul", "gzip"],
)
def test_a_sheet_whose_text_kb_never_writes_is_refused(
    monkeypatch, vault_dir, caplog, content
):
    make_watch(monkeypatch, {MODELS_SHEET: content})

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.FAILED
    assert not (vault_dir / "veille" / MODELS_SHEET).exists()
    assert "blob 1 of 1 refused: sheet_text_" in caplog.text


def test_a_blob_changed_since_the_listing_is_left_to_the_next_run(
    monkeypatch, vault_dir, capsys
):
    container = make_watch(monkeypatch, {MODELS_SHEET: b"# models"})
    container.status_of_next_get[MODELS_SHEET] = 412

    assert download() == ExitCode.SUCCEEDED
    assert not (vault_dir / "veille" / MODELS_SHEET).exists()
    assert "1 left to the next run" in capsys.readouterr().out


def test_without_an_account_logged_in_nothing_is_listed_and_kb_exits_with_1(
    monkeypatch, vault_dir, caplog
):
    container = FakeContainer("watch")
    simulate(
        monkeypatch,
        container.handle,
        FakeCliCredential(CredentialUnavailableError("Please run 'az login'")),
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.FAILED
    assert container.requests == []
    assert "watch download: not run: exchange_storage_no_token" in caplog.text


def test_a_listing_refused_by_the_storage_fails_with_its_status_and_code(
    monkeypatch, vault_dir, caplog
):
    simulate(
        monkeypatch,
        answer_error(403, "AuthorizationPermissionMismatch", "Not permitted."),
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = download()

    assert exit_code == ExitCode.FAILED
    assert (
        "exchange_storage_forbidden, HTTP 403, AuthorizationPermissionMismatch"
        in caplog.text
    )


def test_without_the_account_of_the_storage_nothing_is_run(monkeypatch, vault_dir):
    container = make_watch(monkeypatch, {MODELS_SHEET: b"# models"})
    monkeypatch.delenv("KB_EXCHANGE_BLOB_URL")

    assert download() == ExitCode.NOT_STARTED
    assert container.requests == []


def test_a_vault_that_does_not_exist_is_refused_and_not_created(
    monkeypatch, vault_dir, tmp_path
):
    container = make_watch(monkeypatch, {MODELS_SHEET: b"# models"})
    monkeypatch.setenv("KB_VAULT_DIR", str(tmp_path / "a vault misspelt"))

    assert download() == ExitCode.NOT_STARTED
    assert not (tmp_path / "a vault misspelt").exists()
    assert container.requests == []


def test_the_download_stops_on_sigterm():
    assert COMMAND in COMMANDS_STOPPED_BY_SIGTERM
