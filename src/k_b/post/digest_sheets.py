"""The digests of the watch in the vault: one Markdown sheet per subject and per day, written
once by kb digest from the response of the AI API, with the limit of post/vault_files.py.

Its path is made of constants, a subject of the closed list and a day; each text of the response
is written as text, as the response is untrusted (OWASP LLM10)."""

import json
import re
import unicodedata
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from urllib.parse import unquote

from k_b.core.config import WATCH_DIR_NAME
from k_b.core.dates import format_date
from k_b.post.ai_api_client import Digest, DigestsResponse, Source
from k_b.post.vault_files import (
    CHARACTER_REFERENCE,
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


def write_digest_sheet(
    vault_dir: Path, response: DigestsResponse, digest: Digest
) -> str:
    """Write the sheet of digest, of the UTC day of the end of the window; return its path in the
    vault. A sheet written meanwhile is refused (sheet_exists), and one another run is writing
    (temporary_file_found): neither is replaced, with the limits of post/vault_files.py."""
    sheet_path = find_sheet_path(
        vault_dir, digest.subject, response.window.until.date()
    )
    content = render_digest_sheet(response, digest)
    if not write_new_sheet(
        vault_dir, find_sheets_dir(vault_dir, digest.subject), sheet_path, content
    ):
        # Seen by write_new_sheet: refused on that one look, never looked at again.
        raise find_sheet_exists_error(sheet_path, vault_dir)
    return sheet_path.relative_to(vault_dir).as_posix()


def render_digest_sheet(response: DigestsResponse, digest: Digest) -> str:
    """The Markdown of a sheet: a front matter, the claims citing their sources by number, then
    the sources; the same response gives the same bytes."""
    window = response.window
    lines = [
        "---",
        f"subject: {digest.subject}",
        f"generated: {format_date(window.until)}",
        # Checked by MODEL_NAME; written as a string of JSON, which YAML reads as it is.
        f"model: {json.dumps(response.model)}",
        f"window_days: {window.days}",
        f"since: {format_date(window.since)}",
        f"until: {format_date(window.until)}",
        f"items_capped: {json.dumps(response.items_capped)}",
        # A kind of the closed list (ItemKind) and a date: null when nothing is cut.
        f"capped_kind: {window.capped_kind or 'null'}",
        f"covered_after: {format_date(window.covered_after) or 'null'}",
        f"request_id: {response.request_id}",
        "---",
        "",
        f"# Veille {digest.subject} du {window.until.date().isoformat()}",
        "",
    ]
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
    Dataview, and a character reference is decoded even in an autolink."""
    return (
        url.startswith(URL_SCHEMES)
        and URL_CHARACTERS.fullmatch(url) is not None
        and "::" not in url
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
