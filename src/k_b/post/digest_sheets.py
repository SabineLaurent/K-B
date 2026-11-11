"""The digests of the watch in the vault: one Markdown sheet per subject and per day, written
once by kb digest from the response of the AI API, with the limit of post/vault_files.py.

Its path is made of constants, a subject of the closed list and a day; each text of the response
is written as text, as the response is untrusted (OWASP LLM10)."""

import json
import os
import re
import unicodedata
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import unquote

from k_b.core.config import CHARACTER_REFERENCE, WATCH_DIR_NAME
from k_b.core.dates import format_date
from k_b.items import parse_aware_datetime
from k_b.post.ai_api_client import Digest, DigestsResponse, Source
from k_b.post.vault_files import (
    VaultEntryRefusedError,
    has_sheet,
    neutralize_digest_text,
    refuse_linked_folders,
    write_new_sheet,
)

URL_SCHEMES = ("http://", "https://")
# A URL is written, as an autolink, only when it is made of the characters of RFC 3986 (unreserved,
# delimiters, a percent and two hexadecimal digits), less [ ] and $, a wikilink and a formula of
# Obsidian: it cannot leave its <…>, where a backslash escapes nothing (CommonMark 0.31.2, 6.5).
URL_CHARACTERS = re.compile(r"(?:[A-Za-z0-9._~:/?#@!&'()*+,;=-]|%[0-9A-Fa-f]{2})+")
# What a URL may not hold once its percents are decoded (markdown-it shows them decoded): a control,
# a format character (the bidirectional ones, U+200B to U+200F, U+FEFF, U+00AD), a surrogate, a line
# or paragraph separator. A link would read otherwise than it leads (CWE-451).
HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
NO_CLAIM = "Aucune affirmation retenue."
NO_ITEM = "Aucun item classé dans ce sujet."
# The name of a sheet kb writes: a note of Sabine or a temporary file in the folder is not one.
SHEET_NAME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.md")
# The front matter opens a sheet; these bytes hold it whole, read without the rest of the sheet.
MAX_FRONT_MATTER_BYTES = 4096
FRONT_MATTER_OPENING = b"---\n"
FRONT_MATTER_CLOSING = b"\n---\n"
UNTIL_KEY = "until: "


def find_sheets_dir(vault_dir: Path, subject: str) -> Path:
    return vault_dir / WATCH_DIR_NAME / subject


def find_sheet_path(vault_dir: Path, subject: str, day: date) -> Path:
    return find_sheets_dir(vault_dir, subject) / f"{day.isoformat()}.md"


def refuse_written_sheets(
    vault_dir: Path, subject_names: Sequence[str], day: date
) -> None:
    """Before the request, refuse a sheet of a subject already written for day, or a folder down
    to it that is a symbolic link; creates nothing."""
    for subject in subject_names:
        sheets_dir = find_sheets_dir(vault_dir, subject)
        refuse_linked_folders(vault_dir, sheets_dir)
        refuse_existing_sheet(find_sheet_path(vault_dir, subject, day), vault_dir)


def refuse_existing_sheet(sheet_path: Path, vault_dir: Path) -> None:
    if has_sheet(sheet_path, vault_dir):
        raise find_sheet_exists_error(sheet_path, vault_dir)


def find_sheet_exists_error(
    sheet_path: Path, vault_dir: Path
) -> VaultEntryRefusedError:
    return VaultEntryRefusedError(
        f"sheet_exists: {sheet_path.relative_to(vault_dir).as_posix()} is there;"
        " kb digest never rewrites a sheet"
    )


def read_subject_starts(
    vault_dir: Path, subject_names: Sequence[str], now: datetime
) -> dict[str, datetime]:
    """The start of each subject with a sheet: the until of its last sheet (#565)."""
    starts: dict[str, datetime] = {}
    for subject in subject_names:
        until = find_previous_until(vault_dir, subject, now)
        if until is not None:
            starts[subject] = until
    return starts


def find_previous_until(
    vault_dir: Path, subject: str, now: datetime
) -> datetime | None:
    """The until of the last sheet of subject, the one of the greatest day; None without a sheet.
    A last sheet that is a link, or without one valid until up to now, is refused."""
    sheets_dir = find_sheets_dir(vault_dir, subject)
    try:
        names = [
            entry.name
            for entry in os.scandir(sheets_dir)
            if SHEET_NAME.fullmatch(entry.name)
        ]
    except FileNotFoundError:
        return None
    if not names:
        return None
    sheet_path = sheets_dir / max(names)
    # Refuses a link or another entry under the name of the sheet, read by lstat.
    has_sheet(sheet_path, vault_dir)
    until = read_until(sheet_path)
    if until is None or until > now:
        raise VaultEntryRefusedError(
            f"previous_sheet_invalid: {sheet_path.relative_to(vault_dir).as_posix()} has no"
            " until in its front matter that is a date with its zone, up to now"
        )
    return until


def read_until(sheet_path: Path) -> datetime | None:
    """The until of the front matter of the sheet, read without following a link; None when the
    front matter is not there, or holds none or more than one until that is a date."""
    descriptor = os.open(sheet_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as sheet:
        head = sheet.read(MAX_FRONT_MATTER_BYTES)
    end = head.find(FRONT_MATTER_CLOSING)
    if not head.startswith(FRONT_MATTER_OPENING) or end == -1:
        return None
    try:
        lines = head[len(FRONT_MATTER_OPENING) : end].decode("utf-8").split("\n")
    except UnicodeDecodeError:
        return None
    values = [
        line.removeprefix(UNTIL_KEY) for line in lines if line.startswith(UNTIL_KEY)
    ]
    if len(values) != 1:
        return None
    try:
        return parse_aware_datetime(values[0], "until").astimezone(UTC)
    except ValueError:
        return None


def write_digest_sheet(
    vault_dir: Path, response: DigestsResponse, digest: Digest
) -> str:
    """Write the sheet of digest, of the UTC day of the end of the window; return its path in the
    vault. A sheet written meanwhile is refused (sheet_exists), and one another run is writing
    (temporary_file_found): neither is replaced, with the limits of post/vault_files.py."""
    return write_sheet(
        vault_dir, response, digest.subject, render_digest_sheet(response, digest)
    )


def write_empty_sheet(vault_dir: Path, response: DigestsResponse, subject: str) -> str:
    """Write the sheet of a subject no item fell in, as write_digest_sheet: its until is the start
    of the next digest of the subject."""
    return write_sheet(
        vault_dir, response, subject, render_empty_sheet(response, subject)
    )


def write_sheet(
    vault_dir: Path, response: DigestsResponse, subject: str, content: str
) -> str:
    sheet_path = find_sheet_path(vault_dir, subject, response.window.until.date())
    if not write_new_sheet(
        vault_dir, find_sheets_dir(vault_dir, subject), sheet_path, content
    ):
        # Seen by write_new_sheet: refused on that one look, never looked at again.
        raise find_sheet_exists_error(sheet_path, vault_dir)
    return sheet_path.relative_to(vault_dir).as_posix()


def render_empty_sheet(response: DigestsResponse, subject: str) -> str:
    return "\n".join([*render_heading(response, subject), NO_ITEM]) + "\n"


def render_heading(response: DigestsResponse, subject: str) -> list[str]:
    """The front matter of a sheet, then its title; since is the start of its subject."""
    window = response.window
    return [
        "---",
        f"subject: {subject}",
        f"generated: {format_date(window.until)}",
        # Checked by MODEL_NAME; written as a string of JSON, which YAML reads as it is.
        f"model: {json.dumps(response.model)}",
        f"since: {format_date(response.since_by_subject[subject])}",
        f"until: {format_date(window.until)}",
        f"items_capped: {json.dumps(response.items_capped)}",
        # A kind of the closed list (ItemKind) and a date: null when nothing is cut.
        f"capped_kind: {window.capped_kind or 'null'}",
        f"covered_after: {format_date(window.covered_after) or 'null'}",
        f"request_id: {response.request_id}",
        "---",
        "",
        f"# Veille {subject} du {window.until.date().isoformat()}",
        "",
    ]


def render_digest_sheet(response: DigestsResponse, digest: Digest) -> str:
    """The Markdown of a sheet: a front matter, the claims citing their sources by number, then
    the sources; the same response gives the same bytes."""
    lines = render_heading(response, digest.subject)
    if not digest.claims:
        return "\n".join([*lines, NO_CLAIM]) + "\n"
    number_by_item = {
        source.item_id: number for number, source in enumerate(digest.sources, start=1)
    }
    lines += [
        f"- {neutralize_digest_text(claim.text)}"
        f" ({cite_sources(sorted(number_by_item[item_id] for item_id in claim.item_ids))})"
        for claim in digest.claims
    ]
    lines += ["", "## Sources", ""]
    lines += [
        f"{number}. {render_source(source)}"
        for number, source in enumerate(digest.sources, start=1)
    ]
    return "\n".join(lines) + "\n"


def cite_sources(numbers: list[int]) -> str:
    listed = ", ".join(str(number) for number in numbers)
    return f"source {listed}" if len(numbers) == 1 else f"sources {listed}"


def render_source(source: Source) -> str:
    title = neutralize_digest_text(source.title)
    if source.url is None or not is_writable_url(source.url):
        return f"{title} (sans URL)"
    return f"{title} — <{source.url}>"


def is_writable_url(url: str) -> bool:
    """Whether the URL can be written as an autolink, never rewritten: :: would make a field of
    Dataview, a character reference is decoded even in an autolink, and kb download-watch-sheets
    refuses ~~~ anywhere in a line."""
    return (
        url.startswith(URL_SCHEMES)
        and URL_CHARACTERS.fullmatch(url) is not None
        and "::" not in url
        and "~~~" not in url
        and CHARACTER_REFERENCE.search(url) is None
        and not has_hidden_character(url)
    )


def has_hidden_character(url: str) -> bool:
    """Whether the URL, its percents decoded, holds a character not shown as itself; a
    percent-encoding that is not UTF-8 counts as one."""
    try:
        decoded = unquote(url, errors="strict")
    except UnicodeDecodeError:
        return True
    return any(
        unicodedata.category(character) in HIDDEN_CATEGORIES for character in decoded
    )
