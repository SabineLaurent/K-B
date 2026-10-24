"""The fidelity of a claim: each fact, normalized, is in its text and in a field sent of the item it
cites (docs/fiches-veille.md, "Fidélité")."""

import re
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from k_b.ai_api.stages.writing import Claim, Fact
from k_b.ai_api.watch_items import WatchItem, WatchKind
from k_b.core.config import MAX_FIELD_CHARS_FOR_WRITING

# Dashes U+2010 to U+2015 and the minus sign U+2212 become "-", the typographic quotes "'" and '"'.
PUNCTUATION = str.maketrans(
    {
        **{chr(code): "-" for code in (*range(0x2010, 0x2016), 0x2212)},
        chr(0x2018): "'",
        chr(0x2019): "'",
        chr(0x201C): '"',
        chr(0x201D): '"',
    }
)
BLANKS = re.compile(r"\s+")
INVISIBLE_CATEGORY = "Cf"
# Applied to a normalized text. A separator is any run without letter nor digit: CVE_2026_0001 is
# a CVE too (decision of Sabine of 2026-10-24). An identifier ends at a limit, as any fact: neither
# a letter nor a digit after it, nor a . or a - followed by one.
END_LIMIT = r"(?![^\W_]|[.-][^\W_])"
CVE = re.compile(rf"cve[\W_]*(\d{{4}})[\W_]*(\d{{4,}}){END_LIMIT}")
GHSA = re.compile(
    rf"ghsa[\W_]*([0-9a-z]{{4}})[\W_]*([0-9a-z]{{4}})[\W_]*([0-9a-z]{{4}}){END_LIMIT}"
)
# Added after a field cut for the writing: a letter, so that its end is not a limit (…1.2 may be
# the start of 1.2.9).
CUT_END = "a"
# The fields where an ordinary fact is searched; a CVE or a GHSA only equals cve_id or ghsa_id.
SEARCHED_FIELDS_BY_KIND: dict[WatchKind, tuple[str, ...]] = {
    "paper": ("title", "summary"),
    "vulnerability": ("title", "description", "vendor", "product", "ransomware_use"),
    "release": ("repository_name", "tag_name", "title", "body"),
    "advisory": ("title", "packages"),
    "newsletter_article": ("title", "summary"),
}


@dataclass(frozen=True)
class ClaimFidelity:
    facts_checked: int
    facts_found: int
    # Every fact found, every identifier of the text declared, every item cited carrying a fact.
    is_faithful: bool


def check_claim(claim: Claim, item_by_ref: Mapping[str, WatchItem]) -> ClaimFidelity:
    """The facts of the claim checked, each against the item it cites."""
    text = normalize(claim.text)
    text_identifiers = set(find_identifiers(text))
    found_facts = [
        fact
        for fact in claim.facts
        if is_fact_found(fact, text, text_identifiers, item_by_ref[fact.item_id])
    ]
    declared = {to_canonical_identifier(normalize(fact.value)) for fact in claim.facts}
    return ClaimFidelity(
        facts_checked=len(claim.facts),
        facts_found=len(found_facts),
        is_faithful=len(found_facts) == len(claim.facts)
        and text_identifiers <= declared
        and set(claim.item_ids) <= {fact.item_id for fact in found_facts},
    )


def normalize(text: str) -> str:
    """NFKC, casefold, invisible characters removed, dashes and quotes unified, blanks reduced."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    visible = "".join(
        char for char in folded if unicodedata.category(char) != INVISIBLE_CATEGORY
    )
    return BLANKS.sub(" ", visible.translate(PUNCTUATION))


def is_fact_found(
    fact: Fact, text: str, text_identifiers: set[str], item: WatchItem
) -> bool:
    value = normalize(fact.value)
    if CVE.search(value) or GHSA.search(value):
        identifier = to_canonical_identifier(value)
        return (
            identifier is not None
            and identifier in text_identifiers
            and any(
                to_canonical_identifier(normalize(field)) == identifier
                for field in list_identifier_fields(item)
            )
        )
    # A value without letter nor digit says nothing of the item, and a space is found anywhere.
    if not any(char.isalnum() for char in value):
        return False
    return is_found(value, text) and any(
        is_found(value, to_searched_text(field)) for field in list_searched_fields(item)
    )


def to_searched_text(field: str) -> str:
    """The field normalized; at the length of the cut, its end is not a limit."""
    is_cut = len(field) >= MAX_FIELD_CHARS_FOR_WRITING
    return normalize(field) + (CUT_END if is_cut else "")


def find_identifiers(text: str) -> Iterator[str]:
    """The CVE and GHSA of a normalized text, in their canonical form."""
    for cve in CVE.finditer(text):
        yield to_canonical_cve(cve)
    for ghsa in GHSA.finditer(text):
        yield to_canonical_ghsa(ghsa)


def to_canonical_identifier(value: str) -> str | None:
    """CVE-YYYY-NNNN or GHSA-xxxx-xxxx-xxxx if the normalized value is one, and nothing more."""
    if cve := CVE.fullmatch(value):
        return to_canonical_cve(cve)
    if ghsa := GHSA.fullmatch(value):
        return to_canonical_ghsa(ghsa)
    return None


def to_canonical_cve(cve: re.Match[str]) -> str:
    return f"CVE-{cve[1]}-{cve[2]}"


def to_canonical_ghsa(ghsa: re.Match[str]) -> str:
    return f"GHSA-{ghsa[1]}-{ghsa[2]}-{ghsa[3]}"


def list_identifier_fields(item: WatchItem) -> list[str]:
    values = (getattr(item.fields, name, None) for name in ("cve_id", "ghsa_id"))
    return [value for value in values if value is not None]


def list_searched_fields(item: WatchItem) -> list[str]:
    """Each text of the fields searched, each name of the packages apart; a null field skipped."""
    texts: list[str] = []
    for name in SEARCHED_FIELDS_BY_KIND[item.kind]:
        value = getattr(item.fields, name)
        if isinstance(value, list):
            texts.extend(value)
        elif value is not None:
            texts.append(value)
    return texts


def is_found(value: str, text: str) -> bool:
    """Whether the value is in the text at least once between its limits."""
    start = text.find(value)
    while start != -1:
        end = start + len(value)
        if not joins_a_word(text, start - 1, -1) and not joins_a_word(text, end, 1):
            return True
        start = text.find(value, start + 1)
    return False


def joins_a_word(text: str, position: int, step: int) -> bool:
    """Whether the character at position is a letter or a digit, or a . or a - with one beyond it."""
    if not 0 <= position < len(text):
        return False
    char = text[position]
    if char.isalnum():
        return True
    beyond = position + step
    return char in ".-" and 0 <= beyond < len(text) and text[beyond].isalnum()
