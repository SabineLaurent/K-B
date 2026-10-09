import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from k_b.items import Item
from k_b.raw_items import read_raw_items
from k_b.source_contract import SourceKind, SourceReader
from k_b.source_kinds import SOURCE_KINDS

FIXTURES_DIR = Path(__file__).parent / "fixtures"
COLLECTION_NAME = "2026-10-05T093000Z"
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)


def read_lines(raw: bytes) -> list[str]:
    return raw.decode().splitlines()


def convert_line(line: str, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code="tldr",
        source_item_id=line,
        title=line,
        url=f"https://example.com/{line}",
        collected_at=collected_at,
        raw_file_path=raw_file_path,
    )


# A fake kind whose raw collections are folders of pages, each line of a page an entry.
FAKE_PAGE_KINDS = [SourceKind("fake", (), SourceReader(read_lines, convert_line))]


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


def write_most_starred_ranking(raw_dir: Path) -> None:
    """A ranking of 100 repositories, the size the source asks for, built from the fixture."""
    response = json.loads(
        (FIXTURES_DIR / "github_most_starred_extract.json").read_bytes()
    )
    model = response["items"][0]
    response["items"] = [
        {
            **model,
            "full_name": f"owner/repository-{rank}",
            "html_url": f"https://github.com/owner/repository-{rank}",
        }
        for rank in range(1, 101)
    ]
    source_dir = raw_dir / "automated_watch" / "github_most_starred"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.json").write_text(json.dumps(response))


def test_every_source_with_a_reader_gives_its_items(tmp_path):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv", "xml")
    copy_fixture(tmp_path, "cisa_kev_extract.csv", "cisa_kev", "csv")
    copy_fixture(
        tmp_path,
        "github_releases_extract.json",
        "github_releases_anthropics_claude_code",
        "json",
    )
    copy_fixture(
        tmp_path, "github_advisories_extract.json", "github_advisories_pip", "json"
    )
    write_most_starred_ranking(tmp_path)

    reading = read_raw_items(tmp_path, SOURCE_KINDS)

    count_by_raw_file = {}
    for item in reading.items:
        count_by_raw_file[item.raw_file_path] = (
            count_by_raw_file.get(item.raw_file_path, 0) + 1
        )
    assert count_by_raw_file == {
        f"automated_watch/arxiv/{COLLECTION_NAME}.xml": 3,
        f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv": 4,
        f"automated_watch/github_releases_anthropics_claude_code/{COLLECTION_NAME}.json": 3,
        f"automated_watch/github_advisories_pip/{COLLECTION_NAME}.json": 3,
        f"automated_watch/github_most_starred/{COLLECTION_NAME}.json": 100,
    }
    assert {item.collected_at for item in reading.items} == {COLLECTED_AT}
    assert reading.rejections == []


def test_a_release_is_titled_by_the_repository_of_its_url(tmp_path):
    # The releases of claude-code, in the folder of another tracked repository.
    copy_fixture(
        tmp_path,
        "github_releases_extract.json",
        "github_releases_langchain_ai_langchain",
        "json",
    )

    titles = [item.title for item in read_raw_items(tmp_path, SOURCE_KINDS).items]

    assert titles[0].startswith("anthropics/claude-code ")


def test_an_unreadable_file_is_rejected_and_the_others_are_read(tmp_path, caplog):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv", "xml")
    broken = tmp_path / "automated_watch" / "cisa_kev" / f"{COLLECTION_NAME}.csv"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"<html>not a catalog</html>")

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert len(reading.items) == 3
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv"
    assert rejection.reason.startswith("ValueError: catalog without the columns")
    assert f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv" in caplog.text


def test_a_file_name_that_is_not_a_collection_time_is_rejected(tmp_path):
    source_dir = tmp_path / "automated_watch" / "arxiv"
    source_dir.mkdir(parents=True)
    shutil.copyfile(FIXTURES_DIR / "arxiv_extract.xml", source_dir / "latest.xml")

    reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert reading.items == []
    assert [rejection.raw_file_path for rejection in reading.rejections] == [
        "automated_watch/arxiv/latest.xml"
    ]


def test_a_source_without_reader_is_skipped_and_logged(tmp_path, caplog):
    pages_dir = tmp_path / "automated_watch" / "tldr_ai" / COLLECTION_NAME
    pages_dir.mkdir(parents=True)
    (pages_dir / "2026-10-05.html").write_text("<html></html>")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert reading.items == []
    assert reading.rejections == []
    assert "source without a reader, skipped: tldr_ai" in caplog.text


def test_a_folder_of_no_source_kind_is_skipped_and_logged(tmp_path, caplog):
    copy_fixture(tmp_path, "arxiv_extract.xml", "unknown", "xml")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert reading.items == []
    assert reading.rejections == []
    assert "folder without a source kind, skipped: unknown" in caplog.text


def test_the_raw_files_of_an_untracked_repository_and_ecosystem_are_read(tmp_path):
    copy_fixture(
        tmp_path,
        "github_releases_extract.json",
        "github_releases_someone_untracked",
        "json",
    )
    copy_fixture(
        tmp_path,
        "github_advisories_extract.json",
        "github_advisories_rubygems",
        "json",
    )

    reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert {item.raw_file_path.split("/")[1] for item in reading.items} == {
        "github_releases_someone_untracked",
        "github_advisories_rubygems",
    }
    assert reading.rejections == []


def test_files_are_read_in_collection_order(tmp_path):
    for collection_name in ("2026-10-06T093000Z", "2026-10-05T093000Z"):
        source_dir = tmp_path / "automated_watch" / "arxiv"
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            FIXTURES_DIR / "arxiv_extract.xml", source_dir / f"{collection_name}.xml"
        )

    collection_times = [
        item.collected_at for item in read_raw_items(tmp_path, SOURCE_KINDS).items
    ]

    assert collection_times == sorted(collection_times)


def test_an_empty_raw_folder_gives_nothing(tmp_path):
    reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert reading.items == []
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
        reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert [item.source_item_id for item in reading.items] == [
        "CVE-2026-86950",
        "CVE-2026-88772",
        "CVE-2020-29583",
    ]
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == f"automated_watch/cisa_kev/{COLLECTION_NAME}.csv"
    assert rejection.reason.startswith("entry 2: ValidationError")
    assert "entry 2" in caplog.text


def test_hidden_files_are_ignored(tmp_path):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv", "xml")
    (tmp_path / "automated_watch" / "arxiv" / ".DS_Store").write_bytes(
        b"\x00\x00\x00\x01Bud1"
    )

    reading = read_raw_items(tmp_path, SOURCE_KINDS)

    assert len(reading.items) == 3
    assert reading.rejections == []


def test_a_folder_of_pages_is_read_page_by_page(tmp_path):
    # Written out of name order: the pages are read in name order.
    write_pages(
        tmp_path,
        COLLECTION_NAME,
        {"2026-10-05.html": b"c\nd", "2026-10-04.html": b"a\nb"},
    )

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS)

    assert [
        (item.source_item_id, item.raw_file_path, item.collected_at)
        for item in reading.items
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

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS)

    assert [item.source_item_id for item in reading.items] == ["a"]
    assert reading.rejections == []


def test_a_folder_inside_a_folder_of_pages_is_skipped_and_logged(tmp_path, caplog):
    pages_dir = write_pages(tmp_path, COLLECTION_NAME, {"2026-10-05.html": b"a"})
    (pages_dir / "archive").mkdir()
    (pages_dir / "archive" / "2026-10-04.html").write_bytes(b"inside")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS)

    assert [item.source_item_id for item in reading.items] == ["a"]
    assert reading.rejections == []
    assert (
        f"folder inside a collection folder, skipped: automated_watch/fake/{COLLECTION_NAME}/archive"
        in caplog.text
    )


def test_a_folder_of_pages_not_named_by_a_collection_time_is_rejected_whole(
    tmp_path,
):
    write_pages(tmp_path, "latest", {"2026-10-04.html": b"a", "2026-10-05.html": b"b"})

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS)

    assert reading.items == []
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

    reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS)

    assert [item.source_item_id for item in reading.items] == ["a"]
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
        reading = read_raw_items(tmp_path, FAKE_PAGE_KINDS)
    finally:
        unreadable_dir.chmod(0o755)

    assert [item.source_item_id for item in reading.items] == ["b"]
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == "automated_watch/fake/2026-10-04T093000Z"
    assert rejection.reason.startswith("PermissionError")
