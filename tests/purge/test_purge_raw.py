"""The purge of the raw: every collection older than six months, the state catalogs apart
(docs/registre-traitements.md, step 3)."""

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.etl.raw_store import RawStore
from k_b.purge.raw import delete_expired_raw

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"
# Six months after it, the bound is 2026-10-05T09:30:01Z: OLD is a second before it.
IMPORTED_AT = datetime(2027, 4, 5, 9, 30, 1, tzinfo=UTC)
OLD = "2026-10-05T093000Z"
AT_THE_BOUND = "2026-10-05T093001Z"
YOUNG = "2027-03-01T093000Z"
STATE_CATALOG_FOLDER_KEYS = (
    "raw/selected_library/zotero",
    "raw/automated_watch/cisa_kev",
)


def write_fixture(data_dir, key, fixture):
    """A raw file at key, the recorded raw of a source."""
    path = data_dir / key
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES_DIR / fixture, path)
    return path


def purge(data_dir):
    return delete_expired_raw(
        RawStore(data_dir), IMPORTED_AT, STATE_CATALOG_FOLDER_KEYS
    )


def test_a_collection_older_than_six_months_is_deleted_a_younger_one_kept(tmp_path):
    folder = "raw/automated_watch/arxiv_cscr_x_csai"
    old = write_fixture(tmp_path, f"{folder}/{OLD}.xml", "arxiv_extract.xml")
    at_the_bound = write_fixture(
        tmp_path, f"{folder}/{AT_THE_BOUND}.xml", "arxiv_extract.xml"
    )
    young = write_fixture(tmp_path, f"{folder}/{YOUNG}.xml", "arxiv_extract.xml")

    assert purge(tmp_path) == 1
    assert (old.exists(), at_the_bound.exists(), young.exists()) == (False, True, True)


def test_a_folder_of_pages_leaves_whole_with_its_hidden_files(tmp_path):
    collection = tmp_path / f"raw/automated_watch/tldr_ai/{OLD}"
    write_fixture(
        tmp_path,
        f"raw/automated_watch/tldr_ai/{OLD}/2026-10-01.html",
        "tldr_ai_extract.html",
    )
    (collection / ".DS_Store").write_bytes(b"")
    (collection / ".2026-10-02.html.a1b2c3.tmp").write_bytes(b"")

    assert purge(tmp_path) == 1
    assert not collection.exists()
    assert (tmp_path / "raw/automated_watch/tldr_ai").is_dir()


def test_the_state_catalogs_keep_their_raw_whatever_its_age(tmp_path):
    catalog = write_fixture(
        tmp_path, f"raw/automated_watch/cisa_kev/{OLD}.csv", "cisa_kev_extract.csv"
    )
    extract = write_fixture(
        tmp_path,
        f"raw/selected_library/zotero/{OLD}.json",
        "github_releases_extract.json",
    )

    assert purge(tmp_path) == 0
    assert (catalog.exists(), extract.exists()) == (True, True)


def test_the_tops_and_the_copies_of_the_clips_follow_the_six_months(tmp_path):
    ranking = write_fixture(
        tmp_path,
        f"raw/automated_watch/github_most_starred/{OLD}.json",
        "github_most_starred_extract.json",
    )
    clip_copy = write_fixture(
        tmp_path,
        f"raw/selected_library/clipping/{OLD}/0123456789abcdef.md",
        "tldr_ai_extract.html",
    )

    assert purge(tmp_path) == 2
    assert (ranking.exists(), clip_copy.parent.exists()) == (False, False)


@pytest.mark.parametrize(
    "name",
    [
        "notes.txt",
        # Read by the import, which strptime accepts, but not the name kb gives: kept.
        "2026-4-5T093000Z.xml",
        f"{OLD}.old.xml",
    ],
)
def test_a_file_whose_name_is_not_a_collection_time_is_never_deleted(tmp_path, name):
    path = write_fixture(
        tmp_path, f"raw/automated_watch/arxiv_cscr_x_csai/{name}", "arxiv_extract.xml"
    )

    assert purge(tmp_path) == 0
    assert path.exists()


def test_a_folder_whose_whole_name_is_not_a_collection_time_is_never_deleted(tmp_path):
    page = write_fixture(
        tmp_path,
        f"raw/automated_watch/tldr_ai/{OLD}.old/2026-10-01.html",
        "tldr_ai_extract.html",
    )

    assert purge(tmp_path) == 0
    assert page.exists()


def test_a_collection_holding_a_folder_is_kept_whole(tmp_path):
    page = write_fixture(
        tmp_path,
        f"raw/automated_watch/tldr_ai/{OLD}/2026-10-01.html",
        "tldr_ai_extract.html",
    )
    (page.parent / "inside").mkdir()

    assert purge(tmp_path) == 0
    assert page.exists()


def test_a_link_is_never_followed(tmp_path):
    outside = tmp_path / "outside"
    target_file = write_fixture(tmp_path, "outside/kept.xml", "arxiv_extract.xml")
    target_folder = outside / OLD
    target_page = write_fixture(
        tmp_path, f"outside/{OLD}/2026-10-01.html", "tldr_ai_extract.html"
    )
    arxiv = tmp_path / "raw/automated_watch/arxiv_cscr_x_csai"
    arxiv.mkdir(parents=True)
    # A collection that is a link, a collection that holds one, a source folder that is one.
    (arxiv / f"{OLD}.xml").symlink_to(target_file)
    tldr_collection = tmp_path / f"raw/automated_watch/tldr_ai/{OLD}"
    tldr_collection.mkdir(parents=True)
    (tldr_collection / "2026-10-01.html").symlink_to(target_page)
    (tmp_path / "raw/automated_watch/tldr_dev").symlink_to(outside)

    assert purge(tmp_path) == 0
    assert target_file.exists()
    assert target_page.exists()
    assert target_folder.is_dir()
    assert (tldr_collection / "2026-10-01.html").is_symlink()


def test_a_collection_deleted_meanwhile_by_another_import_is_no_error(
    tmp_path, monkeypatch
):
    collection = tmp_path / f"raw/automated_watch/tldr_ai/{OLD}"
    write_fixture(
        tmp_path,
        f"raw/automated_watch/tldr_ai/{OLD}/2026-10-01.html",
        "tldr_ai_extract.html",
    )
    list_collections = RawStore.list_collections

    def listed_then_deleted_by_another_import(store, folder_key):
        collections = list_collections(store, folder_key)
        shutil.rmtree(collection, ignore_errors=True)
        return collections

    monkeypatch.setattr(
        RawStore, "list_collections", listed_then_deleted_by_another_import
    )

    assert purge(tmp_path) == 0


def test_a_purge_stopped_midway_is_finished_by_the_next_one(tmp_path, monkeypatch):
    collection = tmp_path / f"raw/automated_watch/tldr_ai/{OLD}"
    for page in ("2026-10-01.html", "2026-10-02.html"):
        write_fixture(
            tmp_path,
            f"raw/automated_watch/tldr_ai/{OLD}/{page}",
            "tldr_ai_extract.html",
        )
    delete = RawStore.delete

    def stopped_after_the_first_page(store, key):
        delete(store, key)
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(RawStore, "delete", stopped_after_the_first_page)
        with pytest.raises(KeyboardInterrupt):
            purge(tmp_path)
    assert len(list(collection.iterdir())) == 1

    assert purge(tmp_path) == 1
    assert not collection.exists()


def test_without_a_raw_folder_nothing_is_done(tmp_path):
    assert purge(tmp_path) == 0


def test_the_log_gives_numbers_never_a_name(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    write_fixture(
        tmp_path,
        f"raw/automated_watch/arxiv_cscr_x_csai/{OLD}.xml",
        "arxiv_extract.xml",
    )
    kept = write_fixture(
        tmp_path,
        f"raw/automated_watch/tldr_ai/{OLD}/2026-10-01.html",
        "tldr_ai_extract.html",
    )
    (kept.parent / "inside").mkdir()

    purge(tmp_path)

    assert (
        "raw purge: 1 collections older than 6 months deleted, 1 kept"
        " (a folder or a link inside)" in caplog.messages
    )
    assert OLD not in caplog.text
    assert "arxiv" not in caplog.text
