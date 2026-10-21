"""The digests of the watch in the vault: one Markdown sheet per subject and per day, written by
kb digest from the response of the AI API (docs/fiches-veille.md, "Fiches dans le coffre"; #209).

A sheet is written once, never rewritten, never through a symbolic link (etl/vault_files.py). Its
path is made of constants, of a subject of the closed list and of a day, never of another value
of the response. Each text of the response, a claim written by the model or a title read from a
source, is written as text: the response is an input not trusted (OWASP LLM10). Its front matter
keys are in English, its text in French (rule of Sabine of 2026-10-21).
"""

import json
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from k_b.core.config import WATCH_DIR_NAME
from k_b.database.dates import format_date
from k_b.etl.ai_api_client import Digest, DigestsResponse, Source
from k_b.etl.vault_files import (
    MARKDOWN_SYNTAX_CHARACTERS,
    VaultEntryRefusedError,
    has_sheet,
    neutralize_text,
    refuse_linked_folders,
    write_new_sheet,
)

# Beyond the characters of the sheets of the tops: a fence of code (~~~), an autolink of GFM or a
# field of Dataview (:: , http:, mailto:, xmpp:), an e-mail address (@). A bare URL stays text
# here: a claim of the model never makes a link (ADR of 2026-10-21, #209).
DIGEST_ESCAPED_CHARACTERS = MARKDOWN_SYNTAX_CHARACTERS | frozenset("~:@")
# The autolink of GFM that needs none of them, www. in any case (GitHub Flavored Markdown, 6.9):
# its dot is escaped, after the backslashes of the text.
WWW_DOT = re.compile(r"(www)\.", re.IGNORECASE)
URL_SCHEMES = ("http://", "https://")
# A URL is written, as an autolink, only when it is made of the characters of RFC 3986 (unreserved,
# delimiters, a percent and two hexadecimal digits), less [ ] and $, a wikilink and a formula of
# Obsidian: it cannot leave its <…>, where a backslash escapes nothing (CommonMark 0.31.2, 6.5).
URL_CHARACTERS = re.compile(r"(?:[A-Za-z0-9._~:/?#@!&'()*+,;=-]|%[0-9A-Fa-f]{2})+")
NO_CLAIM = "Aucune affirmation retenue."


def find_sheets_dir(vault_dir: Path, subject: str) -> Path:
    return vault_dir / WATCH_DIR_NAME / subject


def find_sheet_path(vault_dir: Path, subject: str, day: date) -> Path:
    return find_sheets_dir(vault_dir, subject) / f"{day.isoformat()}.md"


def refuse_written_sheets(
    vault_dir: Path, subject_names: Sequence[str], day: date
) -> None:
    """Before the request: no sheet of a subject is written for day, and no folder down to it is
    a symbolic link. Raises VaultEntryRefusedError (sheet_exists, vault_link_refused,
    sheet_not_a_file): no item is sent to the model for a sheet that would not be written.
    Creates nothing."""
    for subject in subject_names:
        sheets_dir = find_sheets_dir(vault_dir, subject)
        refuse_linked_folders(vault_dir, sheets_dir)
        refuse_existing_sheet(find_sheet_path(vault_dir, subject, day), vault_dir)


def refuse_existing_sheet(sheet_path: Path, vault_dir: Path) -> None:
    if has_sheet(sheet_path, vault_dir):
        raise VaultEntryRefusedError(
            f"sheet_exists: {sheet_path.relative_to(vault_dir).as_posix()} is there;"
            " kb digest never rewrites a sheet"
        )


def write_digest_sheet(
    vault_dir: Path, response: DigestsResponse, digest: Digest
) -> str:
    """Write the sheet of digest, of the UTC day of the end of the window; its path in the vault.
    A sheet written meanwhile is refused, never rewritten (sheet_exists)."""
    sheet_path = find_sheet_path(
        vault_dir, digest.subject, response.window.until.date()
    )
    content = render_digest_sheet(response, digest)
    if not write_new_sheet(
        vault_dir, find_sheets_dir(vault_dir, digest.subject), sheet_path, content
    ):
        refuse_existing_sheet(sheet_path, vault_dir)
    return sheet_path.relative_to(vault_dir).as_posix()


def render_digest_sheet(response: DigestsResponse, digest: Digest) -> str:
    """The Markdown of a sheet: a front matter, the claims, each citing its sources by their
    number, then the sources. The same response gives the same bytes."""
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
        # Checked by LOWERCASE_NAME and as a date: null when nothing is cut.
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
    return url.startswith(URL_SCHEMES) and URL_CHARACTERS.fullmatch(url) is not None


def neutralize_digest_text(text: str) -> str:
    """The text on one line, as text, without an autolink: the characters of the sheets of the
    tops, ~ : @, and the dot of www. escaped."""
    return WWW_DOT.sub(r"\1\\.", neutralize_text(text, DIGEST_ESCAPED_CHARACTERS))
