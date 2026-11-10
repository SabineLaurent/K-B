"""The files kb writes in the vault, under veille/: written once, never through a symbolic link
kb sees, each text of a source as text, each path named in the vault, never whole.

Limits accepted by Sabine: a folder replaced by a symbolic link after refuse_linked_folders is
followed (CWE-59), though a share of Azure Files mounted without mfsymlinks has no symbolic link;
a file another program writes between the listing of the folder and the rename is replaced
(CWE-367), as it takes no claim."""

import re
import stat
import unicodedata
from pathlib import Path

from k_b.core.atomic_write import TemporaryFileFoundError, write_file_atomically
from k_b.core.config import BIDI_CONTROLS, CHARACTER_REFERENCE

# The characters a text loses: the controls (Cc) and the lone surrogates (Cs), which UTF-8
# cannot encode.
REMOVED_CATEGORIES = frozenset({"Cc", "Cs"})
# The ASCII punctuation that would make syntax of a text in Markdown or Obsidian: a link, an
# embed or a wikilink ([ ]), HTML (< >), a cell of a table (|), code (`), a tag (#), a comment
# (%%), a formula ($). Each is escaped by a backslash, as CommonMark allows for any ASCII
# punctuation; the backslash too, so that a text ending with one does not escape the character
# that follows it.
MARKDOWN_SYNTAX_CHARACTERS = frozenset("\\[]<>|`#%$")
# Beyond the characters of the sheets of the tops: a fence of code (~~~), an autolink of GFM or a
# field of Dataview (:: , http:, mailto:, xmpp:), an e-mail address (@). The & of a character
# reference is escaped by neutralize_text, as in the sheets of the tops. A bare URL stays text
# here: a claim of the model never makes a link (ADR of 2026-10-21, #209). In Obsidian, as the
# recipe of 2026-10-21 shows; cmark-gfm (GitHub) still links an e-mail address and its mailto:.
DIGEST_ESCAPED_CHARACTERS = MARKDOWN_SYNTAX_CHARACTERS | frozenset("~:@")
# The autolink of GFM that needs none of them, www. in any case (GitHub Flavored Markdown, 6.9):
# its dot is escaped, after the backslashes of the text.
WWW_DOT = re.compile(r"(www)\.", re.IGNORECASE)
# A list marker at the start of a text (CommonMark 0.31.2, 5.2 and 5.3): a claim starts a list
# item and a title a numbered line, where it would nest a list. [0-9], not \d, which takes the
# digits of other scripts too. A rule or an underline (---, ***, ===) never stands alone on its line:
# the claim ends with its sources, the title with its URL.
LEADING_LIST_MARKER = re.compile(r"^([-+*]|[0-9]{1,9}[.)])(?= |$)")
# Two colons in a row, once escaped: Dataview takes [key:: value], (key:: value) and key:: value for
# a field, and in reading mode looks for :: in the rendered text, where the escapes are gone
# (replaceInlineFields reads innerHTML, Dataview 0.5.68). A space keeps them apart: : : is shown.
ESCAPED_DOUBLE_COLON = re.compile(r"\\:(?=\\:)")


class VaultEntryRefusedError(Exception):
    """kb refuses an entry of the vault: a symbolic link (vault_link_refused), a sheet that is
    not a regular file (sheet_not_a_file), missing before the deletion of its ranking
    (sheet_missing), or the temporary file of a sheet (temporary_file_found)."""


def write_new_sheet(
    vault_dir: Path, sheets_dir: Path, sheet_path: Path, content: str
) -> bool:
    """Write the sheet unless it exists, even when another run writes it meanwhile; return
    whether it was written. Its folders are checked again first, as write_file_atomically follows
    a link; a temporary file of the sheet is refused, as its sheet may never come."""
    refuse_linked_folders(vault_dir, sheets_dir)
    if has_sheet(sheet_path, vault_dir):
        return False
    try:
        write_file_atomically(sheet_path, content.encode("utf-8"), replace=False)
    except TemporaryFileFoundError as error:
        named = error.temporary_path.relative_to(vault_dir).as_posix()
        raise VaultEntryRefusedError(
            f"temporary_file_found: {named} is there"
        ) from error
    except FileExistsError:
        # Written by another run since has_sheet: a link or another entry is refused as there.
        has_sheet(sheet_path, vault_dir)
        return False
    return True


def refuse_linked_folders(vault_dir: Path, sheets_dir: Path) -> None:
    """Refuse a symbolic link among the folders from the vault down to sheets_dir."""
    for folder in list_folders_down_to(vault_dir, sheets_dir):
        refuse_symbolic_link(folder, vault_dir)


def list_folders_down_to(vault_dir: Path, folder: Path) -> list[Path]:
    """The folders under vault_dir down to folder, the highest first."""
    parts = folder.relative_to(vault_dir).parts
    return [vault_dir.joinpath(*parts[:depth]) for depth in range(1, len(parts) + 1)]


def refuse_symbolic_link(path: Path, vault_dir: Path) -> None:
    """Raise VaultEntryRefusedError when path is a symbolic link, read by lstat, never its
    target."""
    if path.is_symlink():
        raise VaultEntryRefusedError(
            f"vault_link_refused: {path.relative_to(vault_dir).as_posix()} is a symbolic"
            " link"
        )


def has_sheet(sheet_path: Path, vault_dir: Path) -> bool:
    """Whether the sheet is written: a regular file, read by lstat; a link or another entry under
    its name is refused, as it would stand for a sheet that is not there."""
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
    """The text on one line, as text: controls, lone surrogates and bidirectional controls become
    spaces, each of escaped_characters and the & of a character reference escaped, in one pass."""
    visible = "".join(
        " "
        if character in BIDI_CONTROLS
        or unicodedata.category(character) in REMOVED_CATEGORIES
        else character
        for character in text
    )
    line = " ".join(visible.split())
    references = {match.start() for match in CHARACTER_REFERENCE.finditer(line)}
    return "".join(
        f"\\{character}"
        if character in escaped_characters or position in references
        else character
        for position, character in enumerate(line)
    )


def neutralize_digest_text(text: str) -> str:
    """The text on one line, as text, without an autolink, a field of Dataview nor a list; after
    neutralize_text, which would escape their backslash again."""
    neutralized = neutralize_text(text, DIGEST_ESCAPED_CHARACTERS)
    neutralized = ESCAPED_DOUBLE_COLON.sub(r"\\: ", WWW_DOT.sub(r"\1\\.", neutralized))
    return LEADING_LIST_MARKER.sub(escape_list_marker, neutralized)


def escape_list_marker(marker: re.Match[str]) -> str:
    """- becomes \\-, 2026. becomes 2026\\. : CommonMark lets any ASCII punctuation be escaped."""
    return f"{marker[1][:-1]}\\{marker[1][-1]}"
