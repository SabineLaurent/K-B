"""A text received from the data API, cleaned once before the site shows it: the characters HTML
refuses dropped (WHATWG, "Preprocessing the input stream"; RGAA 8.2), and the bidirectional
controls, which, never closed, would reorder the text after them in its line; the line endings made
line feeds. NonEmptyText refuses a NUL and a lone surrogate only (items.py)."""

import unicodedata

from k_b.core.config import BIDI_CONTROLS

KEPT_CONTROLS = frozenset("\t\n")
DROPPED_CATEGORIES = frozenset({"Cc", "Cs"})
# U+FDD0 to U+FDEF, and the last two code points of each plane: U+FFFE, U+FFFF, U+1FFFE...
FIRST_NONCHARACTER = 0xFDD0
LAST_NONCHARACTER = 0xFDEF
PLANE_END = 0xFFFE


def clean_received_text(text: str) -> str:
    """The text without its controls but the tab and the line feed, without its bidirectional
    controls, its noncharacters nor a lone surrogate, its \\r\\n and \\r made \\n."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(character for character in unified if is_kept(character))


def clean_received_value(text: str) -> str | None:
    """The text cleaned; None when the cleaning leaves only blanks, for the caller to say so."""
    cleaned = clean_received_text(text)
    return cleaned if cleaned.strip() else None


def is_kept(character: str) -> bool:
    if character in KEPT_CONTROLS:
        return True
    if character in BIDI_CONTROLS:
        return False
    if unicodedata.category(character) in DROPPED_CATEGORIES:
        return False
    return not is_noncharacter(character)


def is_noncharacter(character: str) -> bool:
    code_point = ord(character)
    return (
        FIRST_NONCHARACTER <= code_point <= LAST_NONCHARACTER
        or code_point & PLANE_END == PLANE_END
    )
