"""The transfers of the jobs: the mirror of the clips, then its wait, and the publication of veille,
each by the identity of the job, with its exit code."""

import logging
from datetime import UTC, datetime
from functools import partial

import pytest
from exchange.storage_fakes import (
    TEST_ACCOUNT_URL,
    TEST_CLIENT_ID,
    FakeBlob,
    FakeContainer,
    FakeTransport,
    answer_identity_refusal,
    answer_token,
    remove_online_variables,
    set_identity_endpoint,
)

from k_b.commands import job_transfers
from k_b.commands.exit_codes import ExitCode
from k_b.core.config import CLIP_CHANGE_MARGIN, CLIP_MIRROR_CLOCK_SLACK
from k_b.exchange.storage import (
    ExchangeStorageSettings,
    build_managed_identity_credential,
    open_container_client,
)

SETTINGS = ExchangeStorageSettings(TEST_ACCOUNT_URL, TEST_CLIENT_ID)
SENT_ON = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture
def vault_dir(monkeypatch, tmp_path):
    remove_online_variables(monkeypatch)
    set_identity_endpoint(monkeypatch)
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return vault_dir


def simulate(monkeypatch, containers, answer_identity=answer_token):
    """The identity endpoint and the containers of the exchange storage, by name; the waits are
    recorded, never slept."""
    waits = []
    monkeypatch.setattr(
        job_transfers,
        "build_managed_identity_credential",
        partial(
            build_managed_identity_credential, transport=FakeTransport(answer_identity)
        ),
    )

    def open_fake(account_url, container_name, credential):
        return open_container_client(
            account_url,
            container_name,
            credential,
            FakeTransport(containers[container_name].handle),
        )

    monkeypatch.setattr(job_transfers, "open_container_client", open_fake)
    monkeypatch.setattr(job_transfers, "sleep", waits.append)
    return waits


def test_the_clips_are_mirrored_then_kb_collect_waits_for_them_to_settle(
    monkeypatch, vault_dir
):
    clippings = FakeContainer("clippings", {"Un clip.md": FakeBlob(b"# clip", SENT_ON)})
    waits = simulate(monkeypatch, {"clippings": clippings})

    exit_code = job_transfers.mirror_the_clips(SETTINGS, vault_dir)

    assert exit_code == ExitCode.SUCCEEDED
    assert (vault_dir / "Clippings" / "Un clip.md").read_bytes() == b"# clip"
    assert waits == [(CLIP_CHANGE_MARGIN + CLIP_MIRROR_CLOCK_SLACK).total_seconds()]
    assert waits == [65.0]


def test_no_wait_when_no_clip_was_copied(monkeypatch, vault_dir):
    waits = simulate(monkeypatch, {"clippings": FakeContainer("clippings")})

    assert job_transfers.mirror_the_clips(SETTINGS, vault_dir) == ExitCode.SUCCEEDED
    assert waits == []


def test_a_refused_clip_beside_a_copied_one_exits_with_4(monkeypatch, vault_dir):
    clippings = FakeContainer(
        "clippings",
        {
            "Un clip.md": FakeBlob(b"# clip", SENT_ON),
            "Un clip ?.md": FakeBlob(b"# clip", SENT_ON),
        },
    )
    simulate(monkeypatch, {"clippings": clippings})

    assert (
        job_transfers.mirror_the_clips(SETTINGS, vault_dir) == ExitCode.PARTIAL_FAILURE
    )


def test_an_identity_refused_fails_the_mirror_with_1(monkeypatch, vault_dir, caplog):
    clippings = FakeContainer("clippings", {"Un clip.md": FakeBlob(b"# clip", SENT_ON)})
    simulate(monkeypatch, {"clippings": clippings}, answer_identity_refusal)

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = job_transfers.mirror_the_clips(SETTINGS, vault_dir)

    assert exit_code == ExitCode.FAILED
    assert clippings.requests == []
    assert "clip mirror: not run: exchange_storage_no_token" in caplog.text


def test_a_clippings_folder_that_is_a_link_fails_the_mirror_with_1(
    monkeypatch, vault_dir, tmp_path, caplog
):
    (tmp_path / "elsewhere").mkdir()
    (vault_dir / "Clippings").symlink_to(tmp_path / "elsewhere")
    clippings = FakeContainer("clippings", {"Un clip.md": FakeBlob(b"# clip", SENT_ON)})
    simulate(monkeypatch, {"clippings": clippings})

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = job_transfers.mirror_the_clips(SETTINGS, vault_dir)

    assert exit_code == ExitCode.FAILED
    assert "clip mirror: not run: clippings_folder_link" in caplog.text


def test_the_sheets_of_veille_are_published_to_watch(monkeypatch, vault_dir):
    (vault_dir / "veille" / "securite").mkdir(parents=True)
    (vault_dir / "veille" / "securite" / "2026-11-05.md").write_bytes(b"# digest")
    watch = FakeContainer("watch")
    simulate(monkeypatch, {"watch": watch})

    exit_code = job_transfers.publish_the_watch(SETTINGS, vault_dir)

    assert exit_code == ExitCode.SUCCEEDED
    assert watch.blobs["securite/2026-11-05.md"].content == b"# digest"


def test_a_publication_stopped_after_a_sheet_sent_exits_with_4(monkeypatch, vault_dir):
    (vault_dir / "veille" / "securite").mkdir(parents=True)
    for day in ("2026-11-05", "2026-11-06"):
        (vault_dir / "veille" / "securite" / f"{day}.md").write_bytes(b"# digest")

    class RefusingSecondUpload(FakeContainer):
        def answer_put(self, blob_name, headers, body):
            if self.uploads()[1:]:
                return 403, {"x-ms-error-code": "AuthorizationPermissionMismatch"}, b""
            return super().answer_put(blob_name, headers, body)

    simulate(monkeypatch, {"watch": RefusingSecondUpload("watch")})

    assert (
        job_transfers.publish_the_watch(SETTINGS, vault_dir) == ExitCode.PARTIAL_FAILURE
    )


def test_a_publication_refused_before_any_sheet_exits_with_1(monkeypatch, vault_dir):
    (vault_dir / "veille" / "securite").mkdir(parents=True)
    (vault_dir / "veille" / "securite" / "2026-11-05.md").write_bytes(b"# digest")
    watch = FakeContainer("watch")

    def refuse(request):
        return 403, {"x-ms-error-code": "AuthorizationPermissionMismatch"}, b""

    watch.handle = refuse
    simulate(monkeypatch, {"watch": watch})

    assert job_transfers.publish_the_watch(SETTINGS, vault_dir) == ExitCode.FAILED
