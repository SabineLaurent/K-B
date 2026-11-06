"""The publication of veille: each sheet the container watch does not hold is sent to it, at its
root, without ever replacing a blob; hidden entries and links are left aside."""

import logging
from datetime import UTC, datetime

import pytest
from jobs.storage_fakes import FakeBlob, FakeContainer, open_fake_container_client

from k_b.jobs.watch_publication import WatchFolderRefusedError, publish_watch

SENT_ON = datetime(2026, 11, 5, tzinfo=UTC)
SHEETS = {
    "tops/github-most-starred/2026-11-06.md": b"# top",
    "securite/2026-11-05.md": b"# digest",
    "tendances/2026-11-02.md": b"# trends",
}


def write_sheets(watch_dir, sheets):
    for name, content in sheets.items():
        path = watch_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def publish(container, watch_dir):
    with open_fake_container_client(container) as container_client:
        return publish_watch(container_client, watch_dir)


@pytest.fixture
def watch_dir(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return vault_dir / "veille"


def test_the_sheets_absent_from_the_container_are_sent_to_its_root(watch_dir):
    write_sheets(watch_dir, SHEETS)
    container = FakeContainer("watch")

    result = publish(container, watch_dir)

    assert {name: blob.content for name, blob in container.blobs.items()} == SHEETS
    assert (result.found, result.sent, result.already_there) == (3, 3, 0)
    assert not result.has_failed


def test_every_sheet_is_sent_without_replacing_a_blob(watch_dir):
    write_sheets(watch_dir, SHEETS)
    container = FakeContainer("watch")

    publish(container, watch_dir)

    assert [
        request.headers.get("If-None-Match") for request in container.uploads()
    ] == ["*"] * 3


def test_a_sheet_already_in_the_container_is_not_sent_again(watch_dir):
    write_sheets(watch_dir, SHEETS)
    container = FakeContainer(
        "watch",
        {"securite/2026-11-05.md": FakeBlob(b"# digest sent before", SENT_ON)},
    )

    result = publish(container, watch_dir)

    assert len(container.uploads()) == 2
    assert container.blobs["securite/2026-11-05.md"].content == b"# digest sent before"
    assert (result.sent, result.already_there) == (2, 1)


class ContainerListedEmpty(FakeContainer):
    """A container whose blobs were created after its listing."""

    def answer_listing(self):
        blobs, self.blobs = self.blobs, {}
        try:
            return super().answer_listing()
        finally:
            self.blobs = blobs


def test_a_sheet_sent_by_another_run_since_the_listing_counts_as_already_there(
    watch_dir,
):
    write_sheets(watch_dir, {"securite/2026-11-05.md": b"# digest"})
    container = ContainerListedEmpty(
        "watch", {"securite/2026-11-05.md": FakeBlob(b"# digest", SENT_ON)}
    )

    result = publish(container, watch_dir)

    assert (result.sent, result.already_there) == (0, 1)
    assert not result.has_failed


def test_hidden_entries_are_left_aside(watch_dir):
    write_sheets(
        watch_dir,
        {
            "tops/github-most-starred/2026-11-06.md": b"# top",
            # The temporary file write_file_atomically leaves when the process is killed.
            "tops/github-most-starred/.2026-11-07.md.k3j9x2qa.tmp": b"# half",
            ".obsidian/workspace.json": b"{}",
        },
    )
    container = FakeContainer("watch")

    result = publish(container, watch_dir)

    assert list(container.blobs) == ["tops/github-most-starred/2026-11-06.md"]
    assert result.left_aside == 2


def test_links_are_neither_followed_nor_sent(watch_dir, tmp_path):
    write_sheets(watch_dir, {"securite/2026-11-05.md": b"# digest"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "2026-11-05.md").write_bytes(b"# outside")
    (watch_dir / "linked.md").symlink_to(outside / "2026-11-05.md")
    (watch_dir / "linked-folder").symlink_to(outside)
    container = FakeContainer("watch")

    result = publish(container, watch_dir)

    assert list(container.blobs) == ["securite/2026-11-05.md"]
    assert result.left_aside == 2


def test_a_watch_folder_that_is_a_link_is_refused(watch_dir, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    write_sheets(elsewhere, {"securite/2026-11-05.md": b"# digest"})
    watch_dir.symlink_to(elsewhere)
    container = FakeContainer("watch")

    with pytest.raises(WatchFolderRefusedError, match="watch_folder_link"):
        publish(container, watch_dir)

    assert container.requests == []


def test_no_watch_folder_sends_nothing_and_does_not_fail(watch_dir):
    container = FakeContainer("watch")

    result = publish(container, watch_dir)

    assert (result.found, result.sent) == (0, 0)
    assert not result.has_failed
    assert container.requests == []


class ContainerRefusingSecondUpload(FakeContainer):
    def answer_put(self, blob_name, headers, body):
        if self.uploads()[1:]:
            return 403, {"x-ms-error-code": "AuthorizationPermissionMismatch"}, b""
        return super().answer_put(blob_name, headers, body)


def test_a_storage_error_stops_the_publication_and_keeps_what_was_sent(watch_dir):
    write_sheets(watch_dir, SHEETS)
    container = ContainerRefusingSecondUpload("watch")

    result = publish(container, watch_dir)

    assert result.storage_error.state == "exchange_storage_forbidden"
    assert result.sent == 1
    assert len(container.uploads()) == 2
    assert result.has_failed


def test_the_end_line_gives_the_counts(watch_dir, caplog):
    write_sheets(watch_dir, SHEETS | {"tendances/.2026-11-09.md.abcdefgh.tmp": b"#"})
    container = FakeContainer(
        "watch", {"tendances/2026-11-02.md": FakeBlob(b"# trends", SENT_ON)}
    )

    with caplog.at_level(logging.INFO):
        publish(container, watch_dir)

    assert (
        "watch publication: 3 sheets found: 2 sent, 1 already in watch, 1 left aside,"
        " 0 not read"
    ) in caplog.text
