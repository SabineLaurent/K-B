import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from k_b.raw_items import read_raw_items

FIXTURES_DIR = Path(__file__).parent / "fixtures"
COLLECTION_NAME = "2026-10-05T093000Z"
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)


def copy_fixture(raw_dir: Path, fixture: str, source: str, extension: str) -> Path:
    source_dir = raw_dir / "automation" / source
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
    source_dir = raw_dir / "automation" / "github_most_starred"
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

    reading = read_raw_items(tmp_path)

    count_by_raw_file = {}
    for item in reading.items:
        count_by_raw_file[item.raw_file_path] = (
            count_by_raw_file.get(item.raw_file_path, 0) + 1
        )
    assert count_by_raw_file == {
        f"automation/arxiv/{COLLECTION_NAME}.xml": 3,
        f"automation/cisa_kev/{COLLECTION_NAME}.csv": 4,
        f"automation/github_releases_anthropics_claude_code/{COLLECTION_NAME}.json": 3,
        f"automation/github_advisories_pip/{COLLECTION_NAME}.json": 3,
        f"automation/github_most_starred/{COLLECTION_NAME}.json": 100,
    }
    assert {item.collected_at for item in reading.items} == {COLLECTED_AT}
    assert reading.rejections == []


def test_a_release_keeps_the_repository_of_its_source(tmp_path):
    copy_fixture(
        tmp_path,
        "github_releases_extract.json",
        "github_releases_anthropics_claude_code",
        "json",
    )

    titles = [item.title for item in read_raw_items(tmp_path).items]

    assert titles[0].startswith("anthropics/claude-code ")


def test_an_unreadable_file_is_rejected_and_the_others_are_read(tmp_path, caplog):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv", "xml")
    broken = tmp_path / "automation" / "cisa_kev" / f"{COLLECTION_NAME}.csv"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"<html>not a catalog</html>")

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path)

    assert len(reading.items) == 3
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == f"automation/cisa_kev/{COLLECTION_NAME}.csv"
    assert rejection.reason.startswith("ValueError: catalog without the columns")
    assert f"automation/cisa_kev/{COLLECTION_NAME}.csv" in caplog.text


def test_a_file_name_that_is_not_a_collection_time_is_rejected(tmp_path):
    source_dir = tmp_path / "automation" / "arxiv"
    source_dir.mkdir(parents=True)
    shutil.copyfile(FIXTURES_DIR / "arxiv_extract.xml", source_dir / "latest.xml")

    reading = read_raw_items(tmp_path)

    assert reading.items == []
    assert [rejection.raw_file_path for rejection in reading.rejections] == [
        "automation/arxiv/latest.xml"
    ]


def test_a_source_without_reader_and_page_folders_are_skipped_and_logged(
    tmp_path, caplog
):
    pages_dir = tmp_path / "automation" / "tldr_ai" / COLLECTION_NAME
    pages_dir.mkdir(parents=True)
    (pages_dir / "2026-10-05.html").write_text("<html></html>")

    with caplog.at_level(logging.INFO):
        reading = read_raw_items(tmp_path)

    assert reading.items == []
    assert reading.rejections == []
    assert "tldr_ai" in caplog.text


def test_files_are_read_in_collection_order(tmp_path):
    for collection_name in ("2026-10-06T093000Z", "2026-10-05T093000Z"):
        source_dir = tmp_path / "automation" / "arxiv"
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            FIXTURES_DIR / "arxiv_extract.xml", source_dir / f"{collection_name}.xml"
        )

    collection_times = [item.collected_at for item in read_raw_items(tmp_path).items]

    assert collection_times == sorted(collection_times)


def test_an_empty_raw_folder_gives_nothing(tmp_path):
    reading = read_raw_items(tmp_path)

    assert reading.items == []
    assert reading.rejections == []


def test_an_entry_refused_as_an_item_is_rejected_and_the_others_of_its_file_are_read(
    tmp_path, caplog
):
    catalog = (FIXTURES_DIR / "cisa_kev_extract.csv").read_text()
    catalog = catalog.replace(
        '"Citrix NetScaler Improper Input Validation Vulnerability"', '""'
    )
    source_dir = tmp_path / "automation" / "cisa_kev"
    source_dir.mkdir(parents=True)
    (source_dir / f"{COLLECTION_NAME}.csv").write_text(catalog)

    with caplog.at_level(logging.WARNING):
        reading = read_raw_items(tmp_path)

    assert [item.source_item_id for item in reading.items] == [
        "CVE-2026-86950",
        "CVE-2026-88772",
        "CVE-2020-29583",
    ]
    assert len(reading.rejections) == 1
    rejection = reading.rejections[0]
    assert rejection.raw_file_path == f"automation/cisa_kev/{COLLECTION_NAME}.csv"
    assert rejection.reason.startswith("entry 2: ValidationError")
    assert "entry 2" in caplog.text


def test_hidden_files_are_ignored(tmp_path):
    copy_fixture(tmp_path, "arxiv_extract.xml", "arxiv", "xml")
    (tmp_path / "automation" / "arxiv" / ".DS_Store").write_bytes(
        b"\x00\x00\x00\x01Bud1"
    )

    reading = read_raw_items(tmp_path)

    assert len(reading.items) == 3
    assert reading.rejections == []
