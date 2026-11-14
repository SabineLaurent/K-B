"""The mirror of the clips: a clip of the container that the share does not hold, or holds older, is
copied to the Clippings folder of the vault, dated as its blob; a name is never logged."""

import errno
import gzip
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from exchange.storage_fakes import (
    SPOTTED_BLOB_NAME,
    FakeBlob,
    FakeContainer,
    open_fake_container_client,
)

from k_b.core.atomic_write import write_file_atomically
from k_b.core.config import CLIP_CHANGE_MARGIN
from k_b.etl.sources import clipping
from k_b.jobs import clip_mirror
from k_b.jobs.clip_mirror import (
    ClippingsFolderRefusedError,
    ClipRules,
    find_clip_name_refusal,
    find_left_aside_reason,
    mirror_clips,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "clipping" / "article_with_author.md"
RULES = ClipRules(extension=".md", max_bytes=1_000_000)
SENT_ON = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = SENT_ON + timedelta(days=1)
CLIP_NAME = "Un clip de la veille.md"
# The title of the spotted blob, without its extension: what a refused name would cite of it.
SPOTTED_TITLE = SPOTTED_BLOB_NAME.removesuffix(".md")


def to_ns(moment):
    return int(moment.timestamp()) * 1_000_000_000


def mirror(container, clippings_dir, rules=RULES):
    with open_fake_container_client(container) as container_client:
        return mirror_clips(container_client, clippings_dir, rules)


@pytest.fixture
def clippings_dir(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return vault_dir / "Clippings"


def test_a_new_clip_is_copied_with_the_date_of_its_blob(clippings_dir):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})

    result = mirror(container, clippings_dir)

    clip_path = clippings_dir / CLIP_NAME
    assert clip_path.read_bytes() == b"# clip"
    assert clip_path.stat().st_mtime_ns == to_ns(SENT_ON)
    assert (result.listed, result.copied, result.unchanged) == (1, 1, 0)
    assert not result.has_failed


def test_a_clip_unchanged_is_not_copied_again(clippings_dir):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})
    mirror(container, clippings_dir)
    status_before = (clippings_dir / CLIP_NAME).stat()

    result = mirror(container, clippings_dir)

    assert container.downloaded_names() == [CLIP_NAME]
    assert (result.copied, result.unchanged) == (0, 1)
    status_after = (clippings_dir / CLIP_NAME).stat()
    assert (status_after.st_ino, status_after.st_ctime_ns) == (
        status_before.st_ino,
        status_before.st_ctime_ns,
    )


def test_a_clip_newer_in_the_container_than_its_file_is_copied_again(clippings_dir):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# v1", SENT_ON)})
    mirror(container, clippings_dir)
    container.blobs[CLIP_NAME] = FakeBlob(b"# v2", LATER)

    result = mirror(container, clippings_dir)

    assert (clippings_dir / CLIP_NAME).read_bytes() == b"# v2"
    assert (clippings_dir / CLIP_NAME).stat().st_mtime_ns == to_ns(LATER)
    assert result.copied == 1


def test_a_clip_sent_again_within_the_same_second_is_copied_by_its_size(
    clippings_dir,
):
    # last_modified is to the second (RFC 1123): the size tells a second version of that second.
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# v1", SENT_ON)})
    mirror(container, clippings_dir)
    container.blobs[CLIP_NAME] = FakeBlob(b"# v1, edited", SENT_ON)

    result = mirror(container, clippings_dir)

    assert (clippings_dir / CLIP_NAME).read_bytes() == b"# v1, edited"
    assert result.copied == 1


# Of the size of the blob, or of another: ifSourceNewer keeps a newer file whatever its size.
@pytest.mark.parametrize("on_the_share", [b"# here", b"# edited on the share"])
def test_a_file_newer_than_its_blob_is_left_as_it_is(clippings_dir, on_the_share):
    clippings_dir.mkdir()
    (clippings_dir / CLIP_NAME).write_bytes(on_the_share)
    os.utime(clippings_dir / CLIP_NAME, ns=(to_ns(LATER), to_ns(LATER)))
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})

    result = mirror(container, clippings_dir)

    assert container.downloaded_names() == []
    assert (clippings_dir / CLIP_NAME).read_bytes() == on_the_share
    assert result.unchanged == 1


def test_the_mirror_deletes_nothing(clippings_dir):
    clippings_dir.mkdir()
    (clippings_dir / "Un clip retiré du conteneur.md").write_bytes(b"# kept")

    mirror(FakeContainer("clippings"), clippings_dir)

    assert (clippings_dir / "Un clip retiré du conteneur.md").read_bytes() == b"# kept"


def test_each_clip_is_written_by_write_file_atomically(monkeypatch, clippings_dir):
    written = []

    def keep_and_write(path, content):
        written.append(path)
        write_file_atomically(path, content)

    monkeypatch.setattr(clip_mirror, "write_file_atomically", keep_and_write)
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})

    mirror(container, clippings_dir)

    assert written == [clippings_dir / CLIP_NAME]


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("sous-dossier/Un clip.md", "blob_in_a_folder"),
        ("../Un clip.md", "blob_in_a_folder"),
        ("a/../b.md", "blob_in_a_folder"),
        (".Un clip caché.md", "blob_name_hidden"),
        (".DS_Store", "blob_name_hidden"),
        (".", "blob_name_hidden"),
        ("..", "blob_name_hidden"),
        ("..md", "blob_name_hidden"),
        ("..\\Un clip.md", "blob_name_hidden"),
        ("Une image.png", "blob_not_markdown"),
        ("Un clip.md.txt", "blob_not_markdown"),
        ("Un clip.MD", "blob_not_markdown"),
        ("", "blob_not_markdown"),
    ],
)
def test_a_name_that_is_not_a_clip_of_the_first_level_is_left_aside(name, reason):
    assert find_left_aside_reason(name, ".md") == reason


@pytest.mark.parametrize(
    "name",
    [
        "Un clip.md",
        "Les options... et la suite.md",
        "a... b.md",
        # U+2024 ONE DOT LEADER stays itself: the name is never normalized.
        "a" + chr(0x2024) + chr(0x2024) + "b.md",
        # U+200D joins the emojis (a format character, not a control).
        "Un clip " + chr(0x1F469) + chr(0x200D) + chr(0x1F4BB) + ".md",
        "a" * 238 + ".md",
    ],
)
def test_a_clip_name_the_share_can_hold_is_neither_left_aside_nor_refused(name):
    assert find_left_aside_reason(name, ".md") is None
    assert find_clip_name_refusal(name) is None


@pytest.mark.parametrize(
    ("name", "refusal"),
    [
        ("Un\\clip.md", "clip_name_with_backslash"),
        ("a\\..\\b.md", "clip_name_with_backslash"),
        ("Un" + chr(0x07) + "clip.md", "clip_name_with_control_character"),
        ("Un" + chr(0x0A) + "clip.md", "clip_name_with_control_character"),
        ("Un" + chr(0x7F) + "clip.md", "clip_name_with_control_character"),
        ("Un" + chr(0x85) + "clip.md", "clip_name_with_control_character"),
        ("Un" + chr(0xE000) + "clip.md", "clip_name_with_unsupported_character"),
        ("Un" + chr(0xD800) + "clip.md", "clip_name_with_unsupported_character"),
        ('Un "clip".md', "clip_name_refused_by_azure_files"),
        ("Un clip : le titre.md", "clip_name_refused_by_azure_files"),
        ("Un|clip.md", "clip_name_refused_by_azure_files"),
        ("Un<clip>.md", "clip_name_refused_by_azure_files"),
        ("Un*clip.md", "clip_name_refused_by_azure_files"),
        ("Un clip ?.md", "clip_name_refused_by_azure_files"),
        # 242 bytes: the temporary file of write_file_atomically would pass 255.
        ("a" * 239 + ".md", "clip_name_too_long"),
        # 123 characters, 243 bytes in UTF-8: counted in bytes.
        ("é" * 120 + ".md", "clip_name_too_long"),
    ],
)
def test_a_clip_name_the_share_cannot_hold_is_refused(name, refusal):
    assert find_left_aside_reason(name, ".md") is None
    assert find_clip_name_refusal(name) == refusal


def test_a_blob_left_aside_is_not_downloaded_nor_a_failure(clippings_dir):
    container = FakeContainer(
        "clippings",
        {
            ".DS_Store": FakeBlob(b"\x00", SENT_ON),
            "sous-dossier/Un clip.md": FakeBlob(b"# clip", SENT_ON),
            "Une image.png": FakeBlob(b"\x89PNG", SENT_ON),
        },
    )

    result = mirror(container, clippings_dir)

    assert container.downloaded_names() == []
    assert dict(result.left_aside) == {
        "blob_name_hidden": 1,
        "blob_in_a_folder": 1,
        "blob_not_markdown": 1,
    }
    assert not result.has_failed
    assert not clippings_dir.exists()


def test_a_refused_clip_fails_by_its_position_and_its_measure_never_its_name(
    clippings_dir, caplog
):
    refused_name = SPOTTED_TITLE + " ?.md"
    container = FakeContainer(
        "clippings",
        {
            "A first clip.md": FakeBlob(b"# clip", SENT_ON),
            refused_name: FakeBlob(b"# clip", SENT_ON),
        },
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        result = mirror(container, clippings_dir)

    assert dict(result.refused) == {"clip_name_refused_by_azure_files": 1}
    assert result.has_failed
    assert result.copied == 1
    assert container.downloaded_names() == ["A first clip.md"]
    assert "blob 2 of 2 refused: clip_name_refused_by_azure_files" in caplog.text
    assert "7Q3ZK" not in caplog.text


def test_a_name_too_long_is_refused_with_its_length_and_the_maximum(
    clippings_dir, caplog
):
    container = FakeContainer("clippings", {"a" * 250 + ".md": FakeBlob(b"#", SENT_ON)})

    with caplog.at_level(logging.INFO, logger="k_b"):
        mirror(container, clippings_dir)

    assert "clip_name_too_long, 253 bytes, maximum 241" in caplog.text


def test_a_clip_larger_than_the_maximum_is_refused_without_being_downloaded(
    clippings_dir, caplog
):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"x" * 11, SENT_ON)})

    with caplog.at_level(logging.INFO, logger="k_b"):
        result = mirror(container, clippings_dir, ClipRules(".md", max_bytes=10))

    assert dict(result.refused) == {"clip_too_large": 1}
    assert container.downloaded_names() == []
    assert "blob 1 of 1 refused: clip_too_large, 11 bytes, maximum 10" in caplog.text


def test_a_compressed_blob_is_copied_as_stored_never_decompressed(clippings_dir):
    # A blob sent with Content-Encoding: gzip; decompressed, it would pass any bound.
    stored = gzip.compress(b"x" * 100_000)
    container = FakeContainer(
        "clippings", {CLIP_NAME: FakeBlob(stored, SENT_ON, content_encoding="gzip")}
    )

    result = mirror(container, clippings_dir, ClipRules(".md", max_bytes=1_000))

    assert (clippings_dir / CLIP_NAME).read_bytes() == stored
    assert result.copied == 1


def test_the_version_listed_is_the_one_downloaded(clippings_dir):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})

    mirror(container, clippings_dir)

    download = next(
        r for r in container.requests if r.method == "GET" and "comp=list" not in r.url
    )
    assert download.headers["If-Match"] == container.blobs[CLIP_NAME].etag


@pytest.mark.parametrize("status", [404, 412])
def test_a_blob_removed_or_changed_since_the_listing_is_left_to_the_next_run(
    clippings_dir, status
):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})
    container.status_of_next_get[CLIP_NAME] = status

    result = mirror(container, clippings_dir)

    assert result.left_to_next_run == 1
    assert not result.has_failed
    assert not (clippings_dir / CLIP_NAME).exists()


def test_a_container_removed_since_the_listing_stops_the_mirror(clippings_dir):
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})
    container.status_of_next_get[CLIP_NAME] = (404, "ContainerNotFound")

    result = mirror(container, clippings_dir)

    assert result.storage_error is not None
    assert result.storage_error.state == "exchange_storage_not_found"
    assert result.left_to_next_run == 0
    assert result.has_failed


def test_a_storage_error_stops_the_mirror(clippings_dir):
    container = FakeContainer(
        "clippings",
        {
            "A first clip.md": FakeBlob(b"# clip", SENT_ON),
            "A second clip.md": FakeBlob(b"# clip", SENT_ON),
        },
    )
    container.status_of_next_get["A first clip.md"] = 403

    result = mirror(container, clippings_dir)

    assert result.storage_error is not None
    assert result.storage_error.state == "exchange_storage_forbidden"
    assert container.downloaded_names() == ["A first clip.md"]
    assert result.has_failed


def test_a_refused_listing_stops_the_mirror_with_nothing_done(clippings_dir):
    container = FakeContainer("clippings")

    def refuse(request):
        return 403, {"x-ms-error-code": "AuthorizationPermissionMismatch"}, b""

    container.handle = refuse

    result = mirror(container, clippings_dir)

    assert result.storage_error.state == "exchange_storage_forbidden"
    assert (result.listed, result.copied) == (0, 0)


@pytest.mark.parametrize("entry", ["link", "folder"])
def test_a_local_entry_that_is_not_a_file_is_refused_and_left_as_it_is(
    clippings_dir, tmp_path, entry
):
    clippings_dir.mkdir()
    target = tmp_path / "outside.md"
    target.write_bytes(b"# outside")
    if entry == "link":
        (clippings_dir / CLIP_NAME).symlink_to(target)
    else:
        (clippings_dir / CLIP_NAME).mkdir()
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", LATER)})

    result = mirror(container, clippings_dir)

    assert dict(result.refused) == {"local_entry_not_a_file": 1}
    assert container.downloaded_names() == []
    assert target.read_bytes() == b"# outside"


def test_a_clippings_folder_that_is_a_link_is_refused(clippings_dir, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    clippings_dir.symlink_to(elsewhere)
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})

    with pytest.raises(ClippingsFolderRefusedError, match="clippings_folder_link"):
        mirror(container, clippings_dir)

    assert list(elsewhere.iterdir()) == []


def test_a_local_error_is_counted_by_its_errno_never_its_path(
    monkeypatch, clippings_dir, caplog
):
    def refuse_the_name(path, content):
        raise OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG), str(path))

    monkeypatch.setattr(clip_mirror, "write_file_atomically", refuse_the_name)
    container = FakeContainer(
        "clippings",
        {
            SPOTTED_BLOB_NAME: FakeBlob(b"# clip", SENT_ON),
            "Z another clip.md": FakeBlob(b"# clip", SENT_ON),
        },
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        result = mirror(container, clippings_dir)

    assert dict(result.failed) == {"ENAMETOOLONG": 2}
    assert result.has_failed
    assert "blob 1 of 2 not written: ENAMETOOLONG" in caplog.text
    assert "7Q3ZK" not in caplog.text


def test_a_date_that_cannot_be_set_is_a_failure_and_the_clip_is_copied(
    monkeypatch, clippings_dir, caplog
):
    def refuse_the_date(*arguments, **keywords):
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))

    monkeypatch.setattr(clip_mirror.os, "utime", refuse_the_date)
    container = FakeContainer("clippings", {CLIP_NAME: FakeBlob(b"# clip", SENT_ON)})

    with caplog.at_level(logging.INFO, logger="k_b"):
        result = mirror(container, clippings_dir)

    assert dict(result.failed) == {"EPERM": 1}
    # Written: kb collect must wait for it, as for any clip copied.
    assert result.copied == 1
    assert (clippings_dir / CLIP_NAME).read_bytes() == b"# clip"
    assert "blob 1 of 1 not dated: EPERM" in caplog.text


def test_the_clip_copied_is_seen_changed_by_the_collection_that_follows(
    monkeypatch, clippings_dir
):
    # Dated 2020 by its blob, long before the last collection: only its ctime, set by the copy,
    # tells the collection it changed (etl/sources/clipping.py, read_changed_at_ns).
    container = FakeContainer(
        "clippings", {CLIP_NAME: FakeBlob(FIXTURE.read_bytes(), SENT_ON)}
    )
    mirror(container, clippings_dir)
    monkeypatch.setattr(
        clipping, "current_time", lambda: datetime.now(UTC) + CLIP_CHANGE_MARGIN * 2
    )

    clips = clipping.ClippingSource(clippings_dir.parent).fetch(
        datetime.now(UTC) - timedelta(days=1)
    )

    assert clips is not None
    assert list(clips.values()) == [FIXTURE.read_bytes()]


def test_the_end_line_counts_each_outcome_without_a_name(clippings_dir, caplog):
    container = FakeContainer(
        "clippings",
        {
            CLIP_NAME: FakeBlob(b"# clip", SENT_ON),
            ".DS_Store": FakeBlob(b"\x00", SENT_ON),
            SPOTTED_TITLE + " ?.md": FakeBlob(b"# clip", SENT_ON),
        },
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        mirror(container, clippings_dir)

    assert (
        "clip mirror: 3 blobs listed: 1 copied, 0 unchanged, 0 left to the next run,"
        " 1 left aside (blob_name_hidden: 1), 1 refused"
        " (clip_name_refused_by_azure_files: 1), 0 failed"
    ) in caplog.text
