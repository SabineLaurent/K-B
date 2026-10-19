import json
import logging
from functools import partial
from pathlib import Path

import pytest
from k_b.etl.top_sheets import (
    Top,
    TopSheetsOutcome,
    neutralize_description,
    write_top_sheets,
)

from k_b.commands.sigterm import StoppedBySigtermError
from k_b.core.config import DIGEST_SUBJECTS, TOPS_DIR_NAME, WATCH_DIR_NAME
from k_b.etl import top_sheets
from k_b.etl.raw_store import RawStore
from k_b.etl.sources import github_most_forked, github_most_starred

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
STARRED_RESPONSE = (FIXTURES_DIR / "github_most_starred_extract.json").read_bytes()
FORKED_RESPONSE = (FIXTURES_DIR / "github_most_forked_extract.json").read_bytes()
# The tops of kb write-tops, read with the size of the recorded responses: 3 repositories each.
STARRED_TOP = Top(
    "most_starred",
    "raw/automated_watch/github_most_starred",
    partial(github_most_starred.read_top_entries, expected_size=3),
    "Étoiles",
    "dépôts GitHub les plus étoilés",
)
FORKED_TOP = Top(
    "most_forked",
    "raw/automated_watch/github_most_forked",
    partial(github_most_forked.read_top_entries, expected_size=3),
    "Forks",
    "dépôts GitHub les plus forkés",
)
TEST_TOPS = (STARRED_TOP, FORKED_TOP)
RECORDED_RESPONSE_BY_TOP = {
    "most_starred": STARRED_RESPONSE,
    "most_forked": FORKED_RESPONSE,
}


def write_ranking(data_dir, top, collection_name, content=None):
    """A ranking of top in raw/, as kb collect writes it."""
    path = data_dir / top.folder_key / f"{collection_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(RECORDED_RESPONSE_BY_TOP[top.name] if content is None else content)
    return path


def response_with(response, **changes):
    """The recorded response, its first repository changed."""
    changed = json.loads(response)
    changed["items"][0].update(changes)
    return json.dumps(changed).encode()


def find_sheet(vault_dir, top, day):
    return vault_dir / "veille" / "tops" / top.name / f"{day}.md"


def list_files(directory):
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    )


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def vault_dir(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def test_a_ranking_gives_the_sheet_of_its_day_by_rank(data_dir, vault_dir):
    write_ranking(data_dir, FORKED_TOP, "2026-10-05T093000Z")

    outcome = write_top_sheets(RawStore(data_dir), vault_dir, FORKED_TOP)

    assert outcome == TopSheetsOutcome(
        written_count=1, existing_count=0, deleted_count=0, unreadable_count=0
    )
    assert find_sheet(vault_dir, FORKED_TOP, "2026-10-05").read_text("utf-8") == (
        "---\n"
        "classement: most_forked\n"
        "releve: 2026-10-05T09:30:00Z\n"
        "depots: 3\n"
        "---\n"
        "\n"
        "# Top 3 des dépôts GitHub les plus forkés, relevé du 2026-10-05\n"
        "\n"
        "| Rang | Dépôt | Forks | Description |\n"
        "|---|---|---|---|\n"
        "| 1 | [firstcontributions/first-contributions]"
        "(https://github.com/firstcontributions/first-contributions) | 111263 |"
        " 🚀✨ Help beginners to contribute to open source projects |\n"
        "| 2 | [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code) | 107886 |"
        " An agent-managed museum exhibit, built in Rust with Gajae-Code / LazyCodex —"
        " developed and maintained with no human intervention. |\n"
        "| 3 | [TheOdinProject/css-exercises](https://github.com/TheOdinProject/css-exercises)"
        " | 94375 |  |\n"
    )


def test_the_sheet_of_the_most_starred_counts_their_stars(data_dir, vault_dir):
    write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")

    write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    lines = (
        find_sheet(vault_dir, STARRED_TOP, "2026-10-05").read_text("utf-8").splitlines()
    )
    assert lines[6:9] == [
        "# Top 3 des dépôts GitHub les plus étoilés, relevé du 2026-10-05",
        "",
        "| Rang | Dépôt | Étoiles | Description |",
    ]
    assert lines[10] == (
        "| 1 | [codecrafters-io/build-your-own-x]"
        "(https://github.com/codecrafters-io/build-your-own-x) | 551156 |"
        " Master programming by recreating your favorite technologies from scratch. |"
    )


def test_the_same_ranking_gives_the_same_bytes(tmp_path):
    sheets = []
    for run in ("first", "second"):
        data_dir, vault_dir = tmp_path / run / "data", tmp_path / run / "vault"
        vault_dir.mkdir(parents=True)
        write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
        write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)
        sheets.append(find_sheet(vault_dir, STARRED_TOP, "2026-10-05").read_bytes())

    assert sheets[0] == sheets[1]


def test_the_url_is_built_from_the_name_never_read_in_html_url(data_dir, vault_dir):
    write_ranking(
        data_dir,
        STARRED_TOP,
        "2026-10-05T093000Z",
        response_with(STARRED_RESPONSE, html_url="https://github.com/someone/else"),
    )

    write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    sheet = find_sheet(vault_dir, STARRED_TOP, "2026-10-05").read_text("utf-8")
    assert "someone/else" not in sheet
    assert "(https://github.com/codecrafters-io/build-your-own-x)" in sheet


def test_each_day_of_collection_gets_its_sheet_and_the_older_rankings_are_deleted(
    data_dir, vault_dir
):
    older = write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    middle = write_ranking(data_dir, STARRED_TOP, "2026-10-06T093000Z")
    last = write_ranking(data_dir, STARRED_TOP, "2026-10-12T093000Z")

    outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome == TopSheetsOutcome(
        written_count=3, existing_count=0, deleted_count=2, unreadable_count=0
    )
    assert list_files(vault_dir) == [
        "veille/tops/most_starred/2026-10-05.md",
        "veille/tops/most_starred/2026-10-06.md",
        "veille/tops/most_starred/2026-10-12.md",
    ]
    assert (older.exists(), middle.exists(), last.exists()) == (False, False, True)


def test_two_rankings_of_a_day_give_one_sheet_the_one_of_the_first(data_dir, vault_dir):
    first = write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    second = write_ranking(
        data_dir,
        STARRED_TOP,
        "2026-10-05T153000Z",
        response_with(STARRED_RESPONSE, stargazers_count=999),
    )

    outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome == TopSheetsOutcome(
        written_count=1, existing_count=1, deleted_count=1, unreadable_count=0
    )
    sheet = find_sheet(vault_dir, STARRED_TOP, "2026-10-05").read_text("utf-8")
    assert "releve: 2026-10-05T09:30:00Z" in sheet
    assert "| 551156 |" in sheet
    assert (first.exists(), second.exists()) == (False, True)


def test_a_sheet_that_exists_is_never_rewritten(data_dir, vault_dir):
    write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    sheet = find_sheet(vault_dir, STARRED_TOP, "2026-10-05")
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"edited by the user\n")

    outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome.existing_count == 1
    assert outcome.written_count == 0
    assert sheet.read_bytes() == b"edited by the user\n"


def test_a_last_ranking_unreadable_keeps_the_last_readable_one(data_dir, vault_dir):
    readable = write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    unreadable = write_ranking(data_dir, STARRED_TOP, "2026-10-06T093000Z", b"not json")

    outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome == TopSheetsOutcome(
        written_count=1, existing_count=0, deleted_count=0, unreadable_count=1
    )
    assert (readable.exists(), unreadable.exists()) == (True, True)
    assert list_files(vault_dir) == ["veille/tops/most_starred/2026-10-05.md"]


def test_a_second_ranking_of_a_day_unreadable_is_read_and_kept(data_dir, vault_dir):
    """The sheet of its day exists: the ranking is read all the same, so that an unreadable one
    is never taken for the last readable."""
    readable = write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)
    unreadable = write_ranking(data_dir, STARRED_TOP, "2026-10-05T153000Z", b"{}")

    outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome == TopSheetsOutcome(
        written_count=0, existing_count=1, deleted_count=0, unreadable_count=1
    )
    assert (readable.exists(), unreadable.exists()) == (True, True)


def test_an_unreadable_ranking_is_logged_as_such(data_dir, vault_dir, caplog):
    write_ranking(data_dir, STARRED_TOP, "2026-10-06T093000Z", b"not json")

    with caplog.at_level(logging.INFO, logger=top_sheets.__name__):
        write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert (
        "most_starred ranking of 2026-10-06: ranking_unreadable, kept: JSONDecodeError"
        in caplog.text
    )


@pytest.mark.parametrize(
    "file_name", ["2026-10-5T093000Z.json", "notes.json", "2026-10-05T093000Z.json.bak"]
)
def test_a_file_not_named_by_a_collection_time_is_kept_and_its_name_never_logged(
    data_dir, vault_dir, caplog, file_name
):
    readable = write_ranking(data_dir, STARRED_TOP, "2026-10-04T093000Z")
    misnamed = readable.parent / file_name
    misnamed.write_bytes(STARRED_RESPONSE)

    with caplog.at_level(logging.INFO, logger=top_sheets.__name__):
        outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome.unreadable_count == 1
    assert (readable.exists(), misnamed.exists()) == (True, True)
    assert "most_starred: ranking_name_invalid, a file of its raw folder kept" in (
        caplog.text
    )
    assert file_name not in caplog.text


def test_a_ranking_written_after_the_folder_is_read_is_neither_read_nor_deleted(
    data_dir, vault_dir
):
    older = write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    last_listed = write_ranking(data_dir, STARRED_TOP, "2026-10-06T093000Z")

    class CollectionDuringTheListing(RawStore):
        def list_file_keys(self, folder_key):
            keys = super().list_file_keys(folder_key)
            write_ranking(data_dir, STARRED_TOP, "2026-10-07T093000Z")
            return keys

    outcome = write_top_sheets(
        CollectionDuringTheListing(data_dir), vault_dir, STARRED_TOP
    )

    assert outcome.deleted_count == 1
    assert (older.exists(), last_listed.exists()) == (False, True)
    assert (data_dir / STARRED_TOP.folder_key / "2026-10-07T093000Z.json").exists()
    assert not find_sheet(vault_dir, STARRED_TOP, "2026-10-07").exists()


def test_no_ranking_gives_no_sheet(data_dir, vault_dir):
    outcome = write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert outcome == TopSheetsOutcome(0, 0, 0, 0)
    assert list_files(vault_dir) == []


@pytest.mark.parametrize(
    "error", [PermissionError(13, "Permission denied"), StoppedBySigtermError()]
)
def test_a_sheet_not_written_deletes_no_ranking(
    data_dir, vault_dir, monkeypatch, error
):
    older = write_ranking(data_dir, STARRED_TOP, "2026-10-05T093000Z")
    last = write_ranking(data_dir, STARRED_TOP, "2026-10-06T093000Z")
    written_paths = []

    def write_then_fail(path, content):
        if written_paths:
            raise error
        written_paths.append(path)

    monkeypatch.setattr(top_sheets, "write_file_atomically", write_then_fail)

    with pytest.raises(type(error)):
        write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert (older.exists(), last.exists()) == (True, True)


def test_no_value_of_github_enters_the_path_of_a_sheet(data_dir, vault_dir):
    write_ranking(
        data_dir,
        STARRED_TOP,
        "2026-10-05T093000Z",
        response_with(STARRED_RESPONSE, description="../../../escaped\n../x.md"),
    )

    write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    assert list_files(vault_dir.parent) == [
        "data/raw/automated_watch/github_most_starred/2026-10-05T093000Z.json",
        "vault/veille/tops/most_starred/2026-10-05.md",
    ]


@pytest.mark.parametrize(
    ("description", "neutralized"),
    [
        (None, ""),
        ("", ""),
        ("first line\nsecond\r\nthird fourth", "first line second third fourth"),
        ("line\n---\nline", "line --- line"),
        ("[a link](https://example.com)", "\\[a link\\](https://example.com)"),
        ("![embed](x.png) [[wikilink]]", "!\\[embed\\](x.png) \\[\\[wikilink\\]\\]"),
        ("<script>alert(1)</script>", "\\<script\\>alert(1)\\</script\\>"),
        ("a | b", "a \\| b"),
        ("ends with a backslash \\", "ends with a backslash \\\\"),
        ("`code` and #tag", "\\`code\\` and \\#tag"),
        ("%%hidden and save $5 or $10", "\\%\\%hidden and save \\$5 or \\$10"),
        ("escape \x1b[31m red", "escape \\[31m red"),
        ("lone \ud800 surrogate", "lone surrogate"),
        ("right\u202eleft\u2066mark\u200f", "right left mark"),
        ("🚀✨ family 👨\u200d👩\u200d👧", "🚀✨ family 👨\u200d👩\u200d👧"),
    ],
)
def test_a_description_is_neutralized_on_one_line(description, neutralized):
    assert neutralize_description(description) == neutralized


def test_a_trapped_description_stays_in_its_cell(data_dir, vault_dir):
    write_ranking(
        data_dir,
        STARRED_TOP,
        "2026-10-05T093000Z",
        response_with(
            STARRED_RESPONSE, description="x |\n---\n# title\n<b>bold</b> \ud800"
        ),
    )

    write_top_sheets(RawStore(data_dir), vault_dir, STARRED_TOP)

    lines = (
        find_sheet(vault_dir, STARRED_TOP, "2026-10-05").read_text("utf-8").splitlines()
    )
    assert lines[10].endswith(" | x \\| --- \\# title \\<b\\>bold\\</b\\> |")
    assert [line for line in lines if line == "---"] == ["---", "---"]


def test_tops_is_a_reserved_name_no_subject_of_the_digests_may_take():
    """The digests of a subject are written in veille/<subject>/: a subject tops would write
    them in the folder of the sheets of the tops."""
    assert (WATCH_DIR_NAME, TOPS_DIR_NAME) == ("veille", "tops")
    assert TOPS_DIR_NAME not in {subject.name for subject in DIGEST_SUBJECTS}
