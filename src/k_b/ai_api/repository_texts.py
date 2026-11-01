"""The texts of a repository as the model will receive them: hidden characters, HTML, code,
images, addresses, URLs and logins removed or masked, then cut (docs/tendances.md, "Défenses et
échecs"); pure code, the texts free text of their owner."""

import re
import unicodedata
from dataclasses import dataclass

from k_b.ai_api.watch_items import LOGIN, MASKED_LOGIN, MASKED_URL, URL

# A text is cut to this many times its bound before any pattern: URL takes 1.27 s on 20,000
# letters, four times more when the text doubles.
RAW_CUT_FACTOR = 4
# Removed: 31 points of the block of the tags are Cn, not Cf.
TAG_BLOCK = range(0xE0000, 0xE0080)
VARIATION_SELECTORS = frozenset(
    (
        *range(0xFE00, 0xFE10),
        *range(0xE0100, 0xE01F0),
        *range(0x180B, 0x180E),
        0x180F,
    )
)
REMOVED_CATEGORIES = frozenset({"Cf", "Co", "Cs"})
# Changed into a space, so that the words around do not stick.
SPACED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})
NEW_LINE = "\n"
# A comment not closed runs to the end of the text.
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
# A tag starts with a letter, /, ! or ?: "a < b > c" is kept.
HTML_TAG = re.compile(r"<[a-zA-Z/!?][^>]*>")
# A block not closed runs to the end of the text.
CODE_BLOCK = re.compile(r"(```|~~~).*?(?:\1|\Z)", re.DOTALL)
BADGE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# Before the URLs: jane.doe@www.example.com would become jane.doe@[url].
# No dot required: jane@localhost; x@latest is masked too.
EMAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*")
MASKED_EMAIL = "[email]"
# The word a raw cut breaks; the lookbehind keeps the search linear.
CUT_WORD = re.compile(r"(?<!\S)\S*\Z")
# The new lines are kept: the README of #369 has lines.
SPACES = re.compile(r"[^\S\n]+")


@dataclass(frozen=True)
class CleanedText:
    text: str
    # Whether the text was cut, before or after its cleaning.
    is_cut: bool


def clean_repository_text(text: str, max_chars: int) -> CleanedText:
    """The text without what hides an instruction or names a person, max_chars at most."""
    raw = text[: RAW_CUT_FACTOR * max_chars]
    cleaned = remove_hidden_characters(raw)
    cleaned = remove_markup(cleaned)
    cleaned = CODE_BLOCK.sub(" ", cleaned)
    cleaned = IMAGE.sub(" ", BADGE.sub(" ", cleaned))
    if len(raw) < len(text):
        cleaned = CUT_WORD.sub("", cleaned)
    cleaned = EMAIL.sub(MASKED_EMAIL, cleaned)
    cleaned = URL.sub(MASKED_URL, cleaned)
    cleaned = LOGIN.sub(MASKED_LOGIN, cleaned)
    cleaned = SPACES.sub(" ", cleaned).strip()
    return CleanedText(
        cleaned[:max_chars], len(raw) < len(text) or len(cleaned) > max_chars
    )


def remove_hidden_characters(text: str) -> str:
    """First, so that a hidden character does not break a pattern of the steps after."""
    return "".join(map(replace_hidden_character, text))


def replace_hidden_character(character: str) -> str:
    point = ord(character)
    if point in TAG_BLOCK or point in VARIATION_SELECTORS:
        return ""
    category = unicodedata.category(character)
    if category in REMOVED_CATEGORIES:
        return ""
    if category in SPACED_CATEGORIES and character != NEW_LINE:
        return " "
    return character


def remove_markup(text: str) -> str:
    """The comments, then the tags, again until the text no longer changes: one pass leaves
    `<<b>script>` a tag, and a comment can hide inside another."""
    while True:
        # Removed without a space: a space would break a tag or a comment it re-forms.
        without_comments = HTML_COMMENT.sub("", text)
        if without_comments != text:
            text = without_comments
            continue
        without_tags = HTML_TAG.sub("", text)
        if without_tags == text:
            return text
        text = without_tags
