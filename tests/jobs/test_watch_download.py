"""The listing of the container watch for the Mac: a blob is a sheet only by a closed list of names,
under the bounds of a sheet and of a listing; the text of a sheet holds nothing kb never writes."""

import logging
from datetime import UTC, datetime

import pytest
from jobs.storage_fakes import FakeBlob, FakeContainer, open_fake_container_client

from k_b.jobs import watch_download
from k_b.jobs.watch_download import (
    DownloadResult,
    describe_download_result,
    find_sheet_text_refusal,
    list_watch_sheets,
    read_sheet_name,
)

PUBLISHED_ON = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
SHEET_NAME = "models/2026-11-10.md"
# The folders of veille the tests know: a subject, a top, the trend reports.
FOLDERS = frozenset({"models", "tops/most_starred", "tendances"})
# Each a name that a closed list must refuse, as two identities of jobs write in watch: a climb out
# of veille, an absolute path, a backslash, a doubled or a final slash, a line feed after the name,
# digits of another script, a date written otherwise or impossible, three folders deep, a hidden
# name, an extension in capitals, a sheet out of any folder.
TRAPPED_NAMES = (
    "../2026-11-10.md",
    "models/../../2026-11-10.md",
    "/models/2026-11-10.md",
    "models\\2026-11-10.md",
    "models//2026-11-10.md",
    "models/2026-11-10.md/",
    "models/2026-11-10.md\n",
    "models/" + "".join(chr(0x0660 + digit) for digit in (2, 0, 2, 6)) + "-11-10.md",
    "models/20261110.md",
    "models/2026-W46-2.md",
    "models/2026-13-40.md",
    "tops/most_starred/old/2026-11-10.md",
    ".models/2026-11-10.md",
    "models/.2026-11-10.md",
    "models/2026-11-10.MD",
    "2026-11-10.md",
)


def list_sheets_of(container, result=None):
    result = result or DownloadResult()
    with open_fake_container_client(container) as container_client:
        return list_watch_sheets(container_client, FOLDERS, result), result


@pytest.mark.parametrize("folder", ["models", "tops/most_starred"])
def test_a_folder_of_one_or_two_levels_is_read_back_from_the_name_of_its_sheet(folder):
    sheet_name = read_sheet_name(f"{folder}/2026-11-10.md")

    assert (sheet_name.folder, sheet_name.day) == (folder, "2026-11-10")


@pytest.mark.parametrize("name", TRAPPED_NAMES)
def test_a_name_out_of_the_closed_list_is_not_a_sheet(name):
    assert read_sheet_name(name) is None


def test_a_sheet_is_listed_with_its_folder_its_day_and_its_place():
    container = FakeContainer(
        "watch", {SHEET_NAME: FakeBlob(b"# models", PUBLISHED_ON)}
    )

    sheets, result = list_sheets_of(container)

    assert [(sheet.folder, sheet.day, sheet.where) for sheet in sheets] == [
        ("models", "2026-11-10", "blob 1 of 1")
    ]
    assert sheets[0].blob.name == SHEET_NAME
    assert result.listed == 1
    assert not result.has_failed


def test_a_trapped_name_is_refused_by_its_place_and_the_sheets_are_still_listed(caplog):
    container = FakeContainer(
        "watch",
        {
            SHEET_NAME: FakeBlob(b"# models", PUBLISHED_ON),
            "../models/2026-11-10.md": FakeBlob(b"# out", PUBLISHED_ON),
        },
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        sheets, result = list_sheets_of(container)

    assert [sheet.blob.name for sheet in sheets] == [SHEET_NAME]
    assert result.refused == {"sheet_name_refused": 1}
    assert result.has_failed
    assert "blob 1 of 2 refused: sheet_name_refused" in caplog.text
    assert "../" not in caplog.text


def test_a_sheet_of_a_folder_unknown_is_left_aside_without_failing():
    container = FakeContainer(
        "watch",
        {
            SHEET_NAME: FakeBlob(b"# models", PUBLISHED_ON),
            "a_subject_retired/2026-11-10.md": FakeBlob(b"# retired", PUBLISHED_ON),
            "tops/a_top_retired/2026-11-10.md": FakeBlob(b"# retired", PUBLISHED_ON),
            "tops/2026-11-10.md": FakeBlob(b"# retired", PUBLISHED_ON),
        },
    )

    sheets, result = list_sheets_of(container)

    assert [sheet.blob.name for sheet in sheets] == [SHEET_NAME]
    assert result.left_aside == {"sheet_folder_unknown": 3}
    assert not result.has_failed


def test_a_sheet_larger_than_the_bound_is_refused_with_its_size(monkeypatch, caplog):
    monkeypatch.setattr(watch_download, "MAX_WATCH_SHEET_BYTES", 8)
    container = FakeContainer(
        "watch", {SHEET_NAME: FakeBlob(b"# models!", PUBLISHED_ON)}
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        sheets, result = list_sheets_of(container)

    assert sheets == []
    assert result.refused == {"sheet_too_large": 1}
    assert "blob 1 of 1 refused: sheet_too_large, 9 bytes, maximum 8" in caplog.text


def test_a_listing_longer_than_the_bound_stops_and_fails_the_sheets_listed_kept(
    monkeypatch, caplog
):
    monkeypatch.setattr(watch_download, "MAX_WATCH_LISTED_BLOBS", 2)
    container = FakeContainer(
        "watch",
        {
            f"models/2026-11-{day:02}.md": FakeBlob(b"# models", PUBLISHED_ON)
            for day in (8, 9, 10)
        },
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        sheets, result = list_sheets_of(container)

    assert [sheet.day for sheet in sheets] == ["2026-11-08", "2026-11-09"]
    assert result.listed == 2
    assert result.is_truncated
    assert result.has_failed
    assert "listing stopped: more than 2 blobs" in caplog.text


@pytest.mark.parametrize(
    ("content", "refusal"),
    [
        (b"# models\xff", "sheet_text_not_utf8"),
        (b"# models\xed\xa0\x80", "sheet_text_not_utf8"),
        (b"# models\x00", "sheet_text_with_control_character"),
        (b"# models\r\n", "sheet_text_with_control_character"),
        (b"# models\x1b[2J", "sheet_text_with_control_character"),
        ("# models\u0085".encode(), "sheet_text_with_control_character"),
        # Right-to-left override, left-to-right isolate, Arabic letter mark: neutralize_text
        # turns each into a space.
        (("# models" + chr(0x202E)).encode(), "sheet_text_with_bidirectional_control"),
        (("# models" + chr(0x2066)).encode(), "sheet_text_with_bidirectional_control"),
        (("# models" + chr(0x061C)).encode(), "sheet_text_with_bidirectional_control"),
        # A query of Dataview, in a block, inline, in JavaScript inline; a backtick after an even
        # number of backslashes is not escaped.
        (b"```dataview\nTABLE file.path\n```\n", "sheet_text_with_code"),
        (b"- `= this.file.name`\n", "sheet_text_with_code"),
        (b"- `$= dv.current()`\n", "sheet_text_with_code"),
        (b"- a \\\\`code`\n", "sheet_text_with_code"),
        # A fence of tildes anywhere in a line: in a quote or a list, it still opens a block.
        (b"~~~dataview\nTABLE file.path\n~~~\n", "sheet_text_with_tilde_fence"),
        (b"> ~~~dataview\n", "sheet_text_with_tilde_fence"),
        (b"- ~~~dataview\n", "sheet_text_with_tilde_fence"),
        # An embed: a remote image, a note of the vault.
        (b"![](https://attacker.example/p.png)\n", "sheet_text_with_embed"),
        (b"![[a note]]\n", "sheet_text_with_embed"),
        # HTML, or a command of Templater; a < after an even number of backslashes is not escaped.
        (b"<img src=https://attacker.example/p.png>\n", "sheet_text_with_html"),
        (b"<% tp.file.title %>\n", "sheet_text_with_html"),
        (b"a \\\\<b>\n", "sheet_text_with_html"),
        # A character reference, which CommonMark decodes, even in an autolink: &#x202E; would
        # give back the right-to-left override (second code review, finding 3).
        (b"facture &#x202E;fdp.exe\n", "sheet_text_with_character_reference"),
        (b"- &#8238;a\n", "sheet_text_with_character_reference"),
        (b"- &rlm;a\n", "sheet_text_with_character_reference"),
        (b"- <https://x.example/&#x202E;>\n", "sheet_text_with_character_reference"),
        (b"- a \\\\&rlm;\n", "sheet_text_with_character_reference"),
    ],
)
def test_a_text_kb_never_writes_is_refused(content, refusal):
    assert find_sheet_text_refusal(content) == refusal


def test_a_text_of_lines_and_tabs_in_utf_8_is_a_sheet():
    assert find_sheet_text_refusal("# Modèles\n\n\t- un dépôt\n".encode()) is None


@pytest.mark.parametrize(
    "text",
    [
        # The syntax kb escapes in a text of a source: an odd number of backslashes before it.
        "- \\`code\\` \\~\\~\\~ !\\[image\\](url) \\<b\\> \\\\\\`",
        # An escaped character reference; another & stays as it is.
        "- R&D \\&rlm; \\&#x202E; <https://example.com/a?b=1&c=2>\n",
        # The autolinks, the links of the tops and the tildes of a URL kb writes.
        "- Titre — <https://example.com/~user/a>\n",
        "- <http://example.com/>\n",
        "| 1 | [owner/name](https://github.com/owner/name) | 3 | ~~ |\n",
    ],
)
def test_the_markdown_kb_writes_is_a_sheet(text):
    assert find_sheet_text_refusal(text.encode()) is None


def test_the_zero_width_joiner_of_an_emoji_is_kept_in_a_sheet():
    emoji = chr(0x1F469) + chr(0x200D) + chr(0x1F4BB)
    assert find_sheet_text_refusal(f"# models {emoji}\n".encode()) is None


def test_the_result_names_each_outcome_and_its_reasons():
    result = DownloadResult(listed=5, copied=1, already_there=1, left_to_next_run=1)
    result.left_aside["sheet_folder_unknown"] += 1
    result.refused["sheet_name_refused"] += 1

    assert describe_download_result(result) == (
        "5 blobs listed: 1 copied, 1 already there, 1 left to the next run,"
        " 1 left aside (sheet_folder_unknown: 1), 1 refused (sheet_name_refused: 1),"
        " 0 failed"
    )
