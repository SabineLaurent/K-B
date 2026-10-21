"""The files kb writes in the vault, under veille/: the sheets of the tops (etl/top_sheets.py) and
the digests of the watch (etl/digest_sheets.py), one place for both (#209).

A sheet is written once, never rewritten. kb never follows a symbolic link in the vault (decision
of Sabine, 2026-10-19). A text of a source is written as text, never as syntax. A path is named in
the vault, never whole: made of constants and a date, it never says where the vault is.
"""

import stat
import unicodedata
from pathlib import Path

from k_b.etl.raw_store import write_file_atomically

# The format characters that reorder a line as it is displayed (Unicode bidirectional controls
# and marks, UAX #9). U+200D, which joins the emojis, is kept.
BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
# The characters a text loses: the controls (Cc) and the lone surrogates (Cs), which UTF-8
# cannot encode.
REMOVED_CATEGORIES = frozenset({"Cc", "Cs"})
# The ASCII punctuation that would make syntax of a text in Markdown or Obsidian: a link, an
# embed or a wikilink ([ ]), HTML (< >), a cell of a table (|), code (`), a tag (#), a comment
# (%%), a formula ($). Each is escaped by a backslash, as CommonMark allows for any ASCII
# punctuation; the backslash too, so that a text ending with one does not escape the character
# that follows it.
MARKDOWN_SYNTAX_CHARACTERS = frozenset("\\[]<>|`#%$")


class VaultEntryRefusedError(Exception):
    """kb refuses an entry of the vault: a folder of the sheets, or a sheet, is a symbolic link
    (vault_link_refused, decision of Sabine, 2026-10-19); a sheet is not a regular file
    (sheet_not_a_file); kb write-tops: a sheet is not there before the deletion of its ranking
    (sheet_missing), decided by time-knight, delegation of Sabine of 2026-10-15."""


def write_new_sheet(
    vault_dir: Path, sheets_dir: Path, sheet_path: Path, content: str
) -> bool:
    """Write the sheet unless it exists; whether it was written. Its folders are checked again
    first: write_file_atomically follows a link."""
    refuse_linked_folders(vault_dir, sheets_dir)
    if has_sheet(sheet_path, vault_dir):
        return False
    write_file_atomically(sheet_path, content.encode("utf-8"))
    return True


def refuse_linked_folders(vault_dir: Path, sheets_dir: Path) -> None:
    """Refuse a symbolic link among the folders from the vault down to sheets_dir."""
    for folder in list_folders_down_to(vault_dir, sheets_dir):
        refuse_symbolic_link(folder, vault_dir)


def list_folders_down_to(vault_dir: Path, folder: Path) -> list[Path]:
    """The folders under vault_dir down to folder, the highest first: veille, veille/tops,
    veille/tops/<top>."""
    parts = folder.relative_to(vault_dir).parts
    return [vault_dir.joinpath(*parts[:depth]) for depth in range(1, len(parts) + 1)]


def refuse_symbolic_link(path: Path, vault_dir: Path) -> None:
    """Raise VaultEntryRefusedError when path is a symbolic link: is_symlink reads the link
    itself (lstat), never its target."""
    if path.is_symlink():
        raise VaultEntryRefusedError(
            f"vault_link_refused: {path.relative_to(vault_dir).as_posix()} is a symbolic"
            " link"
        )


def has_sheet(sheet_path: Path, vault_dir: Path) -> bool:
    """Whether the sheet is written: a regular file, read by lstat, never through a link. A
    link, or another entry (a folder, a FIFO) under its name, is refused: taken for a sheet, it
    would stand for one that is not there."""
    try:
        status = sheet_path.lstat()
    except FileNotFoundError:
        return False
    named = sheet_path.relative_to(vault_dir).as_posix()
    if stat.S_ISLNK(status.st_mode):
        raise VaultEntryRefusedError(f"vault_link_refused: {named} is a symbolic link")
    if not stat.S_ISREG(status.st_mode):
        raise VaultEntryRefusedError(f"sheet_not_a_file: {named} is not a regular file")
    return True


def neutralize_text(text: str, escaped_characters: frozenset[str]) -> str:
    """The text on one line, as text: its controls, lone surrogates and bidirectional controls
    become spaces, its whitespace one space, each of escaped_characters escaped."""
    visible = "".join(
        " "
        if character in BIDI_CONTROLS
        or unicodedata.category(character) in REMOVED_CATEGORIES
        else character
        for character in text
    )
    return "".join(
        f"\\{character}" if character in escaped_characters else character
        for character in " ".join(visible.split())
    )
