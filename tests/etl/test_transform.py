import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.etl.raw_files import RawFile, RawReading, Rejection
from k_b.etl.raw_store import RawStore, write_file_atomically
from k_b.etl.source_contract import EntryReading, SourceKind, SourceReader
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources.zotero import ZoteroSource
from k_b.etl.transform import read_raw_items
from k_b.items import Item

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
COLLECTION_NAME = "2026-10-05T093000Z"
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)


def read_lines(raw: bytes) -> EntryReading[str]:
    return EntryReading(raw.decode().splitlines(), [])


def convert_line(line: str, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code="tldr",
        source_item_id=line,
        kind="newsletter_article",
        title=line,
        url=f"https://example.com/{line}",
        published_at=collected_at,
        summary=line,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
        edition="ai",
        rank=1,
    )


# A fake kind whose raw collections are folders of pages, each line of a page an entry.
FAKE_PAGE_KINDS = [
    SourceKind("fake", (), SourceReader("tldr", read_lines, convert_line))
]


def items_of(reading: RawReading) -> list[Item]:
    """The items of every file read, in reading order."""
    return [item for raw_file in reading.files for item in raw_file.items]


def write_pages(raw_dir: Path, collection_name: str, pages: dict[str, bytes]) -> Path:
    pages_dir = raw_dir / "automated_watch" / "fake" / collection_name
    pages_dir.mkdir(parents=True)
    for page_name, page in pages.items():
        (pages_dir / page_name).write_bytes(page)
    return pages_dir


def copy_fixture(raw_dir: Path, fixture: str, source: str, extension: str) -> Path:
    source_dir = raw_dir / "automated_watch" / source
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / f"{COLLECTION_NAME}.{extension}"
    shutil.copyfile(FIXTURES_DIR / fixture, path)
    return path


def test_every_source_with_a_reader_gives_its_items(tmp_path):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml")
    copy_fixture(tmp_path, "cisa_kev_extract.csv", "cisa_kev", "csv")

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    count_by_raw_file = {}
    for item in items_of(reading):
        count_by_raw_file[item.raw_file_path] = (
            count_by_raw_file.get(item.raw_file_path, 0) + 1
        )
    assert count_by_raw_file == {
        f"automated_watch/arxiv_cscr_x_csai/{COLLECTION_NAME}.xml": 3,
        f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv": 4,
    }
    assert {item.collected_at for item in items_of(reading)} == {COLLECTED_AT}
    assert reading.rejections == []


def test_an_unreadable_file_is_rejected_and_the_others_are_read(tmp_path, caplog):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml")
    broken = tmp_path / "automated_watch" / "cisa_kev" / f"{COLLECTION_NAME}.csv"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"<html>not a catalog</html>")

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert len(items_of(reading)) == 3
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv"
    assert rejection.reason.startswith("ValueError: catalog without the columns")
    assert f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv" in caplog.text


def test_a_file_name_that_is_not_a_collection_time_is_rejected(tmp_path):
    source_dir = tmp_path / "automated_watch" / "arxiv_cscr_x_csai"
    source_dir.mkdir(parents=True)
    shutil.copyfile(FIXTURES_DIR / "arxiv_extract.xml", source_dir / "latest.xml")

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert items_of(reading) == []
    assert [rejection.raw_file_path for rejection in reading.rejections] == [
        "automated_watch/arxiv_cscr_x_csai/latest.xml"
    ]


def test_a_folder_of_no_source_kind_is_skipped_and_logged(tmp_path, caplog):
    copy_fixture(tmp_path, "arxiv_extract.xml", "unknown", "xml")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert items_of(reading) == []
    assert reading.rejections == []
    assert "folder without a source kind, skipped: 'unknown'" in caplog.text


def test_the_name_of_a_folder_of_no_source_kind_is_logged_escaped_and_truncated(
    tmp_path, caplog
):
    folder_name = "line\nINFO forged" + "x" * 200
    (tmp_path / "automated_watch" / folder_name).mkdir(parents=True)

    with caplog.at_level(logging.INFO):
        read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    [message] = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("folder without a source kind")
    ]
    assert (
        message == "folder without a source kind, skipped: " + repr(folder_name)[:100]
    )
    assert "\n" not in message


def test_the_raw_files_of_a_folder_no_longer_tracked_are_read(tmp_path):
    copy_fixture(tmp_path, "cisa_kev_extract.csv", "cisa_kev_old", "csv")

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert {item.raw_file_path.split("/")[1] for item in items_of(reading)} == {
        "cisa_kev_old"
    }
    assert reading.rejections == []


@pytest.mark.parametrize("folder_name", ["github_most_starred", "github_most_forked"])
def test_a_github_ranking_is_skipped_and_logged(tmp_path, caplog, folder_name):
    copy_fixture(tmp_path, f"{folder_name}_extract.json", folder_name, "json")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert items_of(reading) == []
    assert reading.rejections == []
    assert (
        f"source without a reader of items, skipped by the item reader: '{folder_name}'"
    ) in caplog.text


@pytest.mark.parametrize(
    "fixture_name, folder_name, kind",
    [
        (
            "github_releases_extract.json",
            "github_releases_anthropics_claude_code",
            "release",
        ),
        ("github_advisories_extract.json", "github_advisories_pip", "advisory"),
    ],
)
def test_the_github_releases_and_advisories_are_read(
    tmp_path, fixture_name, folder_name, kind
):
    copy_fixture(tmp_path, fixture_name, folder_name, "json")

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert [item.kind for item in items_of(reading)] == [kind] * 3
    assert reading.rejections == []


def test_files_are_read_in_collection_order(tmp_path):
    for collection_name in ("2026-10-06T093000Z", "2026-10-05T093000Z"):
        source_dir = tmp_path / "automated_watch" / "arxiv_cscr_x_csai"
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            FIXTURES_DIR / "arxiv_extract.xml", source_dir / f"{collection_name}.xml"
        )

    collection_times = [
        item.collected_at
        for item in items_of(read_raw_items(tmp_path, SOURCE_KINDS, frozenset()))
    ]

    assert collection_times == sorted(collection_times)


def test_an_empty_raw_folder_gives_nothing(tmp_path):
    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert items_of(reading) == []
    assert reading.rejections == []


def test_an_entry_refused_as_an_item_is_rejected_and_the_others_of_its_file_are_read(
    tmp_path, caplog
):
    catalog = (FIXTURES_DIR / "cisa_kev_extract.csv").read_text()
    catalog = catalog.replace(
        '"Citrix NetScaler Improper Input Validation Vulnerability"', '""'
    )
    source_dir = tmp_path / "automated_watch" / "cisa_kev"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.csv").write_text(catalog)

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert [item.source_item_id for item in items_of(reading)] == [
        "CVE-2026-86950",
        "CVE-2026-88772",
        "CVE-2020-29583",
    ]
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv"
    assert rejection.reason.startswith("read entry 2: ValidationError")
    assert "read entry 2" in caplog.text


def test_a_title_too_long_is_rejected_and_logged_and_the_other_papers_are_read(
    tmp_path, caplog
):
    feed = (FIXTURES_DIR / "arxiv_extract.xml").read_text()
    title = (
        "Resource-Optimized and Energy-Aware Agentic AI Framework Anchored on"
        " Blockchain for Secure Software Supply Chains"
    )
    assert feed.count(f"<title>{title}</title>") == 1
    too_long_title = title + " and" * 100
    feed = feed.replace(f"<title>{title}</title>", f"<title>{too_long_title}</title>")
    source_dir = tmp_path / "automated_watch" / "arxiv_cscr_x_csai"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.xml").write_text(feed)

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert len(items_of(reading)) == 2
    assert "2609.31282" not in [item.source_item_id for item in items_of(reading)]
    observed = f"title too long: {len(too_long_title)} characters, maximum 500"
    (rejection,) = reading.rejections
    assert rejection.raw_file_path == (
        f"automated_watch/arxiv_cscr_x_csai/{COLLECTION_NAME}.xml"
    )
    assert rejection.reason.startswith("read entry 0: ValidationError")
    assert observed in rejection.reason
    assert observed in caplog.text
    # Refused by a check of the whole item: pydantic quotes every field it received (#212).
    assert "input_value" not in rejection.reason
    assert "input_value" not in caplog.text


def test_hidden_files_are_ignored(tmp_path):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv_cscr_x_csai", "xml")
    (tmp_path / "automated_watch" / "arxiv_cscr_x_csai" / ".DS_Store").write_bytes(
        b"\x00\x00\x00\x01Bud1"
    )

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert len(items_of(reading)) == 3
    assert reading.rejections == []


def test_a_folder_of_pages_is_read_page_by_page(tmp_path):
    # Written out of name order: the pages are read in name order.
    write_pages(
        tmp_path,
        COLLECTION_NAME,
        {"2026-10-05.html": b"c\nd", "2026-10-04.html": b"a\nb"},
    )

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert [
        (item.source_item_id, item.raw_file_path, item.collected_at)
        for item in items_of(reading)
    ] == [
        ("a", f"automated_watch/fake/{COLLECTION_NAME}/2026-10-04.html", COLLECTED_AT),
        ("b", f"automated_watch/fake/{COLLECTION_NAME}/2026-10-04.html", COLLECTED_AT),
        ("c", f"automated_watch/fake/{COLLECTION_NAME}/2026-10-05.html", COLLECTED_AT),
        ("d", f"automated_watch/fake/{COLLECTION_NAME}/2026-10-05.html", COLLECTED_AT),
    ]
    assert reading.rejections == []


def test_a_hidden_file_in_a_folder_of_pages_is_skipped(tmp_path):
    write_pages(
        tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"a", ".DS_Store": b"hidden"}
    )

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert [item.source_item_id for item in items_of(reading)] == ["a"]
    assert reading.rejections == []


def test_the_rest_of_an_interrupted_write_in_a_folder_of_pages_is_skipped(
    tmp_path, monkeypatch
):
    pages_dir = write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"a"})
    # The process killed between the write and the rename: the temporary file stays.
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", lambda source, target: None)
        write_file_atomically(pages_dir / "2026-10-06.html", b"partial")
    (rest,) = [path for path in pages_dir.iterdir() if path.name != "2026-10-05.html"]
    assert rest.name.startswith(".2026-10-06.html.")
    assert rest.name.endswith(".tmp")

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert [item.source_item_id for item in items_of(reading)] == ["a"]
    assert reading.rejections == []


def test_a_folder_inside_a_folder_of_pages_is_skipped_and_logged(tmp_path, caplog):
    pages_dir = write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"a"})
    (pages_dir / "archive").mkdir()
    (pages_dir / "archive" / "2026-10-04.html").write_bytes(b"inside")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert [item.source_item_id for item in items_of(reading)] == ["a"]
    assert reading.rejections == []
    assert (
        f"folder inside a collection folder, skipped: 'automated_watch/fake/{COLLECTION_NAME}/archive'"
        in caplog.text
    )


def test_a_folder_of_pages_not_named_by_a_collection_time_is_rejected_whole(
    tmp_path,
):
    write_pages(tmp_path, "latest", {"2026-10-04.html": b"a", "2026-10-05.html": b"b"})

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert items_of(reading) == []
    assert [rejection.raw_file_path for rejection in reading.rejections] == [
        "automated_watch/fake/latest"
    ]
    assert reading.rejections[0].reason.startswith("ValueError: time data 'latest'")


def test_an_unreadable_page_is_rejected_and_the_others_of_its_folder_are_read(
    tmp_path,
):
    write_pages(
        tmp_path,
        COLLECTION_NAME,
        {"2026-10-04.html": b"\xff", "2026-10-05.html": b"a"},
    )

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert [item.source_item_id for item in items_of(reading)] == ["a"]
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert (
        rejection.raw_file_path
        == f"automated_watch/fake/{COLLECTION_NAME}/2026-10-04.html"
    )
    assert rejection.reason.startswith("UnicodeDecodeError")


def test_an_unreadable_folder_of_pages_is_rejected_and_the_others_are_read(tmp_path):
    unreadable_dir = write_pages(
        tmp_path, "2026-10-04T093000Z", {"2026-10-04.html": b"a"}
    )
    write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"b"})
    unreadable_dir.chmod(0)
    try:
        reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())
    finally:
        unreadable_dir.chmod(0o755)

    assert [item.source_item_id for item in items_of(reading)] == ["b"]
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == "automated_watch/fake/2026-10-04T093000Z"
    assert rejection.reason.startswith("PermissionError")


def recording_kinds(opened_pages: list[bytes]) -> list[SourceKind]:
    """FAKE_PAGE_KINDS, with a reader that records each page it is given."""

    def read_and_record(raw: bytes) -> list[str]:
        opened_pages.append(raw)
        return read_lines(raw)

    return [SourceKind("fake", (), SourceReader("tldr", read_and_record, convert_line))]


def test_a_raw_file_already_imported_is_not_opened_and_a_new_one_is(tmp_path):
    write_pages(tmp_path, "2026-10-04T093000Z", {"2026-10-04.html": b"a"})
    write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"b"})
    opened_pages: list[bytes] = []

    reading = read_raw_items(
        tmp_path,
        recording_kinds(opened_pages),
        frozenset({"automated_watch/fake/2026-10-04T093000Z/2026-10-04.html"}),
    )

    assert opened_pages == [b"b"]
    assert reading.read_count == 1
    assert [raw_file.raw_file_path for raw_file in reading.files] == [
        f"automated_watch/fake/{COLLECTION_NAME}/2026-10-05.html"
    ]


def test_a_page_already_imported_is_skipped_and_the_others_of_its_folder_are_read(
    tmp_path,
):
    write_pages(
        tmp_path, COLLECTION_NAME, {"2026-10-04.html": b"a", "2026-10-05.html": b"b"}
    )
    opened_pages: list[bytes] = []

    reading = read_raw_items(
        tmp_path,
        recording_kinds(opened_pages),
        frozenset({f"automated_watch/fake/{COLLECTION_NAME}/2026-10-04.html"}),
    )

    assert opened_pages == [b"b"]
    assert [item.source_item_id for item in items_of(reading)] == ["b"]


def test_a_file_without_item_is_read_with_its_source_and_collection(tmp_path):
    write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b""})

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert reading.files == [
        RawFile(
            f"automated_watch/fake/{COLLECTION_NAME}/2026-10-05.html",
            "tldr",
            COLLECTED_AT,
            [],
            0,
        )
    ]
    assert reading.read_count == 1


def test_an_unreadable_page_gives_no_file_read_but_is_counted_as_opened(tmp_path):
    write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"\xff"})

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert reading.files == []
    assert reading.read_count == 1
    assert len(reading.rejections) == 1


def test_a_collection_not_named_by_its_time_opens_no_page(tmp_path):
    write_pages(tmp_path, "latest", {"2026-10-05.html": b"a"})

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS, frozenset())

    assert reading.files == []
    assert reading.read_count == 0
    assert [rejection.raw_file_path for rejection in reading.rejections] == [
        "automated_watch/fake/latest"
    ]


def test_a_file_read_counts_its_rejected_entries(tmp_path):
    catalog = (FIXTURES_DIR / "cisa_kev_extract.csv").read_text()
    catalog = catalog.replace(
        '"Citrix NetScaler Improper Input Validation Vulnerability"', '""'
    )
    source_dir = tmp_path / "automated_watch" / "cisa_kev"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.csv").write_text(catalog)

    (raw_file,) = read_raw_items(tmp_path, SOURCE_KINDS, frozenset()).files

    assert (len(raw_file.items), raw_file.rejection_count) == (3, 1)


def test_an_entry_rejected_by_its_reader_is_rejected_and_counted_with_its_file(
    tmp_path, caplog
):
    catalog = (FIXTURES_DIR / "cisa_kev_extract.csv").read_text()
    catalog = catalog.replace(",2026-09-27,", ",27/09/2026,", 1).replace(
        '"Citrix NetScaler Improper Input Validation Vulnerability"', '""'
    )
    source_dir = tmp_path / "automated_watch" / "cisa_kev"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.csv").write_text(catalog)

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert [item.source_item_id for item in items_of(reading)] == [
        "CVE-2026-86950",
        "CVE-2020-29583",
    ]
    reader_rejection, item_rejection = reading.rejections
    raw_file_path = f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv"
    assert reader_rejection == Rejection(
        raw_file_path, "line 3 ('CVE-2026-88772'): invalid dateAdded: '27/09/2026'"
    )
    assert "line 3 ('CVE-2026-88772')" in caplog.text
    # Its position counts the entries read: the row rejected by the reader is not one.
    assert item_rejection.reason.startswith("read entry 1: ValidationError")
    (raw_file,) = reading.files
    assert raw_file.rejection_count == 2


@pytest.mark.parametrize(
    "fixture_name, folder_name, extension",
    [
        ("arxiv_extract.xml", "arxiv_cscr_x_csai", "xml"),
        ("cisa_kev_extract.csv", "cisa_kev", "csv"),
        (
            "github_releases_extract.json",
            "github_releases_anthropics_claude_code",
            "json",
        ),
        ("github_advisories_extract.json", "github_advisories_pip", "json"),
    ],
)
def test_the_source_of_a_file_read_is_the_source_of_its_items(
    tmp_path, fixture_name, folder_name, extension
):
    copy_fixture(tmp_path, fixture_name, folder_name, extension)

    (raw_file,) = read_raw_items(tmp_path, SOURCE_KINDS, frozenset()).files

    assert raw_file.items
    assert {item.source_code for item in raw_file.items} == {raw_file.source_code}


def test_the_extracts_of_the_selected_library_are_read(tmp_path, zotero_dir):
    extract_dir = tmp_path / "selected_library" / "zotero"
    extract_dir.mkdir(parents=True)
    (extract_dir / f"{COLLECTION_NAME}.json").write_bytes(
        ZoteroSource(zotero_dir, RawStore(zotero_dir.parent / "data")).fetch(None)
    )

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert [
        (raw_file.raw_file_path, raw_file.source_code, raw_file.collected_at)
        for raw_file in reading.files
    ] == [(f"selected_library/zotero/{COLLECTION_NAME}.json", "zotero", COLLECTED_AT)]
    assert [item.source_item_id for item in items_of(reading)] == [
        "AAAAAAA1",
        "BBBBBBB2",
    ]
    assert reading.rejections == []


def test_a_folder_of_the_selected_library_without_a_source_kind_is_skipped(
    tmp_path, caplog
):
    (tmp_path / "selected_library" / "notes").mkdir(parents=True)

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert reading.files == []
    assert "folder without a source kind, skipped: 'notes'" in caplog.text


def test_a_raw_file_nested_too_deep_is_rejected_and_the_others_are_read(tmp_path):
    copy_fixture(tmp_path, "cisa_kev_extract.csv", "cisa_kev", "csv")
    nested_path = (
        tmp_path / "automated_watch" / "github_releases_anthropics_claude_code"
    ) / f"{COLLECTION_NAME}.json"
    nested_path.parent.mkdir(parents=True)
    nested_path.write_bytes(b"[" * 100_000)

    reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert [raw_file.source_code for raw_file in reading.files] == ["cisa_kev"]
    [rejection] = reading.rejections
    assert rejection.raw_file_path == (
        f"automated_watch/github_releases_anthropics_claude_code/{COLLECTION_NAME}.json"
    )
    assert rejection.reason.startswith("RecursionError: ")


def test_a_summary_with_a_nul_is_rejected_without_its_text(tmp_path, caplog):
    releases = json.loads((FIXTURES_DIR / "github_releases_extract.json").read_text())
    # At the start of the text: pydantic quotes its start and end, and cuts the middle.
    releases[0]["body"] = "RECEIVED_TEXT " + releases[0]["body"] + "\u0000"
    source_dir = tmp_path / "automated_watch" / "github_releases_anthropics_claude_code"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.json").write_text(json.dumps(releases))

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    assert len(items_of(reading)) == len(releases) - 1
    (rejection,) = reading.rejections
    assert rejection.reason.startswith("read entry 0: ValidationError")
    assert "summary" in rejection.reason
    assert "text with a NUL" in rejection.reason
    assert "RECEIVED_TEXT" not in rejection.reason
    assert "RECEIVED_TEXT" not in caplog.text


@pytest.mark.parametrize(
    "folder_name, extension, page",
    [
        (
            "github_releases_anthropics_claude_code",
            "json",
            b'[{"body": "RECEIVED_TEXT"',
        ),
        ("github_releases_anthropics_claude_code", "json", b'["RECEIVED_TEXT\xff"]'),
        ("arxiv_cscr_x_csai", "xml", b"<feed><entry>RECEIVED_TEXT &bogus;</entry>"),
        ("cisa_kev", "csv", b"cveID\nRECEIVED_TEXT\xff\n"),
        ("cisa_kev", "csv", b'cveID\n"RECEIVED_TEXT' + b"x" * 200_000 + b'"\n'),
    ],
)
def test_an_unreadable_page_is_rejected_without_its_text(
    tmp_path, caplog, folder_name, extension, page
):
    source_dir = tmp_path / "automated_watch" / folder_name
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.{extension}").write_bytes(page)

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS, frozenset())

    (rejection,) = reading.rejections
    assert "RECEIVED_TEXT" not in rejection.reason
    assert "RECEIVED_TEXT" not in caplog.text
