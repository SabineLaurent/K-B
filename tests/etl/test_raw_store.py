import json
from datetime import UTC, datetime

import pytest

from k_b.core.quoting import quote_value
from k_b.etl.raw_store import (
    COLLECTION_STATE_FILENAME,
    InvalidCollectionStateError,
    RawCollection,
    RawStore,
    find_stream,
    load_last_collection_dates,
    make_source_folder_key,
    save_last_collection_dates,
    write_new_raw_file,
)


def test_write_new_raw_file_refuses_to_overwrite(tmp_path):
    raw_file_path = tmp_path / "automated_watch" / "fake" / "2026-09-30T100000Z.json"
    write_new_raw_file(raw_file_path, b"first")

    with pytest.raises(FileExistsError):
        write_new_raw_file(raw_file_path, b"second")

    assert raw_file_path.read_bytes() == b"first"


def test_last_collection_dates_are_empty_before_the_first_collection(tmp_path):
    assert load_last_collection_dates(tmp_path) == {}


def test_last_collection_dates_round_trip_as_utc_aware_datetimes(tmp_path):
    collected_at = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
    save_last_collection_dates(tmp_path, {"fake": collected_at})

    last_collection_dates = load_last_collection_dates(tmp_path)

    assert last_collection_dates == {"fake": collected_at}
    assert last_collection_dates["fake"].tzinfo is not None


@pytest.mark.parametrize(
    "state_file_content",
    [
        '{"fake": "2026-09-30T10:00:00"}',  # naive date
        '{"fake": "not a date"}',
        '{"fake": 42}',
        '["fake"]',
        '{"fake": ',  # truncated JSON
    ],
)
def test_invalid_collection_state_is_refused(tmp_path, state_file_content):
    (tmp_path / COLLECTION_STATE_FILENAME).write_text(
        state_file_content, encoding="utf-8"
    )

    with pytest.raises(InvalidCollectionStateError):
        load_last_collection_dates(tmp_path)


def test_a_collection_state_that_is_not_utf8_is_refused(tmp_path):
    (tmp_path / COLLECTION_STATE_FILENAME).write_bytes(
        '{"caf\u00e9": 1}'.encode("latin-1")
    )

    with pytest.raises(InvalidCollectionStateError):
        load_last_collection_dates(tmp_path)


@pytest.mark.parametrize(
    ("raw_file_path", "stream"),
    [
        ("automated_watch/cisa_kev/2026-10-05T093000Z.csv", "cisa_kev"),
        ("automated_watch/tldr_ai/2026-10-07T084509Z/2026-10-07.html", "tldr_ai"),
    ],
)
def test_the_stream_is_the_folder_of_the_source(raw_file_path, stream):
    assert find_stream(raw_file_path) == stream


def test_a_path_without_a_source_folder_is_refused():
    with pytest.raises(ValueError, match="cisa_kev.csv"):
        find_stream("automated_watch/cisa_kev.csv")


def test_a_long_source_name_and_date_of_the_state_are_quoted_cut_in_the_refusal(
    tmp_path,
):
    long_name = "source\n" + "n" * 50_000
    long_date = "date\n" + "d" * 50_000
    (tmp_path / "collection_state.json").write_text(
        json.dumps({long_name: long_date}), encoding="utf-8"
    )

    with pytest.raises(InvalidCollectionStateError) as raised:
        load_last_collection_dates(tmp_path)

    message = str(raised.value)
    assert (
        f"date of {quote_value(long_name)} is invalid: {quote_value(long_date)}"
        in message
    )
    assert "\n" not in message
    assert len(message) < 1_000


def test_a_key_is_deleted_under_the_data_directory_once(tmp_path):
    raw_file = (
        tmp_path / "raw" / "automated_watch" / "cisa_kev" / "2026-10-05T093000Z.csv"
    )
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"catalog")
    store = RawStore(tmp_path)

    assert store.has_file("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")
    assert store.delete("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")
    assert not raw_file.exists()
    assert not store.has_file("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")
    assert not store.delete("raw/automated_watch/cisa_kev/2026-10-05T093000Z.csv")


@pytest.mark.parametrize(
    "key", ["", "/etc/passwd", "raw/../k-b.sqlite", "../outside", "raw\\..\\k-b.sqlite"]
)
def test_a_key_that_is_not_relative_to_the_data_directory_is_refused(tmp_path, key):
    store = RawStore(tmp_path / "data")

    for method in (
        store.delete,
        store.has_file,
        store.read_latest,
        store.list_file_keys,
        store.read,
    ):
        with pytest.raises(
            ValueError, match="not a key relative to the data directory"
        ):
            method(key)


def test_the_latest_raw_file_of_a_folder_is_read_hidden_files_left_out(tmp_path):
    folder = tmp_path / "raw" / "selected_library" / "zotero"
    folder.mkdir(parents=True)
    (folder / "2026-10-05T093000Z.json").write_bytes(b"older")
    (folder / "2026-10-06T093000Z.json").write_bytes(b"latest")
    # A rest of an interrupted write, as write_file_atomically names it.
    (folder / ".2026-10-07T093000Z.json.abc.tmp").write_bytes(b"half")

    assert RawStore(tmp_path).read_latest("raw/selected_library/zotero") == b"latest"


def test_a_folder_without_raw_file_has_no_latest(tmp_path):
    (tmp_path / "raw" / "selected_library" / "zotero").mkdir(parents=True)
    store = RawStore(tmp_path)

    assert store.read_latest("raw/selected_library/zotero") is None
    assert store.read_latest("raw/selected_library/absent") is None


def test_the_keys_of_a_folder_are_listed_in_name_order_hidden_files_left_out(tmp_path):
    folder = tmp_path / "raw" / "automated_watch" / "github_most_starred"
    folder.mkdir(parents=True)
    (folder / "2026-10-06T093000Z.json").write_bytes(b"latest")
    (folder / "2026-10-05T093000Z.json").write_bytes(b"older")
    # A rest of an interrupted write, and the pages of a collection, in a subfolder.
    (folder / ".2026-10-07T093000Z.json.abc.tmp").write_bytes(b"half")
    (folder / "2026-10-07T093000Z").mkdir()
    store = RawStore(tmp_path)

    keys = store.list_file_keys("raw/automated_watch/github_most_starred")

    assert keys == [
        "raw/automated_watch/github_most_starred/2026-10-05T093000Z.json",
        "raw/automated_watch/github_most_starred/2026-10-06T093000Z.json",
    ]
    assert [store.read(key) for key in keys] == [b"older", b"latest"]


def test_a_folder_that_does_not_exist_has_no_key(tmp_path):
    assert RawStore(tmp_path).list_file_keys("raw/automated_watch/absent") == []


def test_the_folder_key_of_a_source_is_under_raw_and_its_acquisition_folder():
    assert make_source_folder_key("selected_library", "zotero") == (
        "raw/selected_library/zotero"
    )


def test_the_source_folders_are_listed_under_both_acquisition_folders_links_left_out(
    tmp_path,
):
    for folder in (
        "raw/automated_watch/arxiv_cscr_x_csai",
        "raw/automated_watch/.hidden",
        "raw/selected_library/zotero",
    ):
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / "raw/automated_watch/notes.txt").write_bytes(b"")
    (tmp_path / "outside").mkdir()
    (tmp_path / "raw/automated_watch/tldr_ai").symlink_to(tmp_path / "outside")

    assert RawStore(tmp_path).list_source_folder_keys() == [
        "raw/automated_watch/arxiv_cscr_x_csai",
        "raw/selected_library/zotero",
    ]


def test_the_collections_of_a_folder_are_its_files_and_folders_by_their_name(tmp_path):
    folder = tmp_path / "raw/automated_watch/tldr_ai"
    (folder / "2026-10-05T093000Z").mkdir(parents=True)
    (folder / "2026-10-06T093000Z.html").write_bytes(b"")
    (folder / ".2026-10-07T093000Z.html.a1b2c3.tmp").write_bytes(b"")
    (folder / "2026-10-08T093000Z.html").symlink_to(folder / "2026-10-06T093000Z.html")

    assert RawStore(tmp_path).list_collections("raw/automated_watch/tldr_ai") == [
        RawCollection(
            "raw/automated_watch/tldr_ai/2026-10-05T093000Z", "2026-10-05T093000Z"
        ),
        RawCollection(
            "raw/automated_watch/tldr_ai/2026-10-06T093000Z.html", "2026-10-06T093000Z"
        ),
    ]


def test_a_collection_is_deleted_once_then_found_gone(tmp_path):
    page = tmp_path / "raw/automated_watch/tldr_ai/2026-10-05T093000Z/2026-10-01.html"
    page.parent.mkdir(parents=True)
    page.write_bytes(b"")
    (page.parent / ".DS_Store").write_bytes(b"")
    store = RawStore(tmp_path)
    key = "raw/automated_watch/tldr_ai/2026-10-05T093000Z"

    assert store.delete_collection(key) == "deleted"
    assert not page.parent.exists()
    assert store.delete_collection(key) == "already_gone"


@pytest.mark.parametrize("inside", ["folder", "link"])
def test_a_collection_holding_a_folder_or_a_link_is_kept(tmp_path, inside):
    collection = tmp_path / "raw/automated_watch/tldr_ai/2026-10-05T093000Z"
    collection.mkdir(parents=True)
    page = collection / "2026-10-01.html"
    page.write_bytes(b"")
    if inside == "folder":
        (collection / "inside").mkdir()
    else:
        (collection / "link.html").symlink_to(tmp_path)

    store = RawStore(tmp_path)

    assert (
        store.delete_collection("raw/automated_watch/tldr_ai/2026-10-05T093000Z")
        == "kept"
    )
    assert page.exists()


def test_the_store_tells_whether_it_has_a_folder(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "file").write_bytes(b"")
    store = RawStore(tmp_path)

    assert (
        store.has_folder("raw"),
        store.has_folder("file"),
        store.has_folder("absent"),
    ) == (
        True,
        False,
        False,
    )


def test_a_collection_that_is_a_link_is_kept_and_its_target_too(tmp_path):
    target = tmp_path / "outside.xml"
    target.write_bytes(b"")
    link = tmp_path / "raw/automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)

    deletion = RawStore(tmp_path).delete_collection(
        "raw/automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"
    )

    assert deletion == "kept"
    assert link.is_symlink()
    assert target.exists()


def test_an_error_other_than_a_collection_gone_is_raised(tmp_path, monkeypatch):
    page = tmp_path / "raw/automated_watch/tldr_ai/2026-10-05T093000Z/2026-10-01.html"
    page.parent.mkdir(parents=True)
    page.write_bytes(b"")

    def refuse(store, key):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(RawStore, "delete", refuse)

    with pytest.raises(PermissionError):
        RawStore(tmp_path).delete_collection(
            "raw/automated_watch/tldr_ai/2026-10-05T093000Z"
        )
