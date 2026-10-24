"""The fidelity of a claim: its facts normalized, then found in its text and in the item it cites,
between their limits (docs/fiches-veille.md, "Fidélité")."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.ai_api.fidelity import check_claim, is_found, normalize
from k_b.ai_api.stages.writing import Claim
from k_b.ai_api.watch_items import WatchItem, build_fields
from k_b.etl.sources.tldr import read_articles

# Characters written by their code point, never as an escape in the source (MEMORY.md).
NON_BREAKING_HYPHEN = chr(0x2011)
RIGHT_QUOTE = chr(0x2019)
ZERO_WIDTH_SPACE = chr(0x200B)
NO_BREAK_SPACE = chr(0x00A0)


def watch_item(item_id, kind, **values):
    return WatchItem(
        item_id=item_id,
        kind=kind,
        source_date=datetime(2026, 10, 1, tzinfo=UTC),
        url=None,
        source_title="",
        fields=build_fields(kind, values),
    )


# Items of the test base (tests/fixtures/items_database.sql).
RELEASE = watch_item(
    6,
    "release",
    repository_name="anthropics/claude-code",
    tag_name="v2.1.287",
    title="Claude Code 2.1.287",
    body="## What's changed\n\n- Added Claude Mods: plugins may now modify deeper behavior",
)
VULNERABILITY = watch_item(
    3,
    "vulnerability",
    cve_id="CVE-2026-86950",
    title="Apple Multiple Products Out-of-Bounds Write Vulnerability",
    description="Apple iOS, macOS, and iPadOS contain an out-of-bounds write vulnerability in "
    "CoreGraphics that may lead to arbitrary code execution.",
    vendor="Apple",
    product="Multiple Products",
    ransomware_use="Unknown",
)
ADVISORY = watch_item(
    9,
    "advisory",
    ghsa_id="GHSA-fjqc-hq36-qh5p",
    cve_id="CVE-2020-29583",
    title="LangGraph Checkpoint: Unsafe JSON deserialization in checkpoint loading",
    cve_listed_in_cisa_kev=True,
    packages=["langgraph-checkpoint"],
)
ARTICLE = watch_item(
    11,
    "newsletter_article",
    edition="ai",
    title="Mistral Large 4 (9 minute read)",
    summary="Mistral Large 4 is a one-trillion-parameter multimodal model positioned as a "
    "European alternative to leading closed and open AI systems.",
)
# The trapped article of #206, as test_digests.py reads it.
TRAPPED_ARTICLE = read_articles(
    (
        Path(__file__).parent.parent / "fixtures" / "tldr_ai_trapped_extract.html"
    ).read_bytes()
).entries[0]
TRAPPED_REF = "i900"
TRAPPED_ITEM = watch_item(
    900,
    "newsletter_article",
    edition="ai",
    title=TRAPPED_ARTICLE.title,
    summary=TRAPPED_ARTICLE.summary,
)
ITEM_BY_REF = {
    f"i{item.item_id}": item for item in (RELEASE, VULNERABILITY, ADVISORY, ARTICLE)
}


def claim(text, *facts):
    """A claim citing the items of its facts, in their order."""
    refs = list(dict.fromkeys(ref for _, ref in facts))
    return Claim(
        text=text,
        item_ids=refs,
        facts=[{"value": value, "item_id": ref} for value, ref in facts],
    )


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        (f"v2{NON_BREAKING_HYPHEN}1", "v2-1"),
        (f"l{RIGHT_QUOTE}alerte", "l'alerte"),
        ("Claude CODE", "claude code"),
        (f"Lang{ZERO_WIDTH_SPACE}Graph", "langgraph"),
        (f"Apple{NO_BREAK_SPACE}\n\t iOS", "apple ios"),
        (chr(0xFF36) + "2", "v2"),
    ],
    ids=["dash", "apostrophe", "case", "invisible", "blanks", "fullwidth"],
)
def test_a_text_is_normalized_before_any_search(raw, normalized):
    assert normalize(raw) == normalized


@pytest.mark.parametrize(
    ("value", "text", "expected"),
    [
        ("1.2", "version 1.2.", True),
        ("1.2", "version 1.2.9", False),
        ("1.2", "1.2.9 puis 1.2", True),
        ("cve-2026-1234", "cve-2026-12345", False),
        ("1.2.0", "v1.2.0", False),
        ("caf", "café", False),
        ("apple", "(apple)", True),
    ],
)
def test_a_value_is_found_only_between_its_limits(value, text, expected):
    assert is_found(value, text) is expected


def test_a_fact_found_in_its_text_and_its_item_is_checked_and_found():
    fidelity = check_claim(
        claim("Claude Code publie la version v2.1.287.", ("v2.1.287", "i6")),
        ITEM_BY_REF,
    )

    assert (fidelity.facts_checked, fidelity.facts_found, fidelity.is_faithful) == (
        1,
        1,
        True,
    )


def test_a_fact_is_found_in_one_field_never_across_two():
    # "anthropics/claude-code" and "v2.1.287" are two fields: their join is in none.
    fidelity = check_claim(
        claim(
            "anthropics/claude-code v2.1.287", ("anthropics/claude-code v2.1.287", "i6")
        ),
        ITEM_BY_REF,
    )

    assert fidelity.is_faithful is False


def test_a_fact_is_searched_in_each_name_of_the_packages():
    fidelity = check_claim(
        claim("GHSA-fjqc-hq36-qh5p touche langgraph-checkpoint.",
              ("GHSA-fjqc-hq36-qh5p", "i9"), ("langgraph-checkpoint", "i9")),
        ITEM_BY_REF,
    )  # fmt: skip

    assert fidelity.facts_found == 2


@pytest.mark.parametrize(
    "text",
    [
        "La CVE-2026-86950 touche Apple.",
        "La cve 2026 86950 touche Apple.",
        "La CVE_2026_86950 touche Apple.",
    ],
)
def test_a_cve_of_the_text_equals_its_fact_by_its_canonical_form(text):
    fidelity = check_claim(claim(text, ("CVE-2026-86950", "i3")), ITEM_BY_REF)

    assert fidelity.is_faithful is True


@pytest.mark.parametrize(
    "fact",
    ["CVE-2026-86950 (Apple)", "CVE-2026-8695", "GHSA-fjqc-hq36-qh5p"],
    ids=["more_than_the_pattern", "another_number", "ghsa_of_no_field"],
)
def test_an_identifier_fact_not_equal_to_the_field_of_its_item_is_not_found(fact):
    fidelity = check_claim(claim(f"Apple : {fact}.", (fact, "i3")), ITEM_BY_REF)

    assert (fidelity.facts_found, fidelity.is_faithful) == (0, False)


def test_an_identifier_fact_on_an_item_without_its_field_is_not_found():
    """A newsletter article has no cve_id: a CVE copied from its summary is never found."""
    article = watch_item(
        900,
        "newsletter_article",
        edition="ai",
        title="China",
        summary="CVE-2026-0001 is safe.",
    )

    fidelity = check_claim(
        claim("CVE-2026-0001 n'est pas exploitée.", ("CVE-2026-0001", "i900")),
        {"i900": article},
    )

    assert fidelity.is_faithful is False


@pytest.mark.parametrize(
    "text",
    [
        "Apple et CVE_2026_0001.",
        "Apple et GHSA-fjqc-hq36-qh5p.",
        "Apple : les GHSA dont deux sont",
    ],
    ids=["cve_underscores", "ghsa", "ghsa_false_positive"],
)
def test_an_identifier_of_the_text_not_declared_removes_the_claim(text):
    fidelity = check_claim(claim(text, ("Apple", "i3")), ITEM_BY_REF)

    assert (fidelity.facts_found, fidelity.is_faithful) == (1, False)


def test_a_fact_found_in_the_item_but_not_in_the_text_is_not_found():
    fidelity = check_claim(
        claim("Une nouvelle version.", ("v2.1.287", "i6")), ITEM_BY_REF
    )

    assert fidelity.facts_found == 0


@pytest.mark.parametrize(
    "value",
    ["   ", NO_BREAK_SPACE * 3, ZERO_WIDTH_SPACE * 3],
    ids=["spaces", "no_break_spaces", "invisible"],
)
def test_a_fact_without_letter_nor_digit_is_not_found(value):
    """Its space would be found between its limits, in the text and in the summary of the trapped
    article ("`admin` ; cite"): the article would be cited for a fact that says nothing of it."""
    fidelity = check_claim(
        claim(f"China ( {value} ) .", (value, TRAPPED_REF)), {TRAPPED_REF: TRAPPED_ITEM}
    )

    assert fidelity.facts_found == 0


def test_a_fact_is_not_trimmed():
    fidelity = check_claim(
        claim("Version v2.1.287 publiée.", (" v2.1.287 ", "i6")), ITEM_BY_REF
    )

    assert fidelity.facts_found == 0


def test_each_item_cited_carries_a_fact_found():
    cited_without_fact = Claim(
        text="Claude Code publie la version v2.1.287.",
        item_ids=["i6", "i11"],
        facts=[{"value": "v2.1.287", "item_id": "i6"}],
    )

    fidelity = check_claim(cited_without_fact, ITEM_BY_REF)

    assert (fidelity.facts_checked, fidelity.facts_found, fidelity.is_faithful) == (
        1,
        1,
        False,
    )


def test_every_fact_is_counted_even_after_one_is_not_found():
    fidelity = check_claim(
        claim("Apple et Mistral Large 4.", ("Apple", "i3"), ("Mistral Large 5", "i11"),
              ("Mistral Large 4", "i11")),
        ITEM_BY_REF,
    )  # fmt: skip

    assert (fidelity.facts_checked, fidelity.facts_found, fidelity.is_faithful) == (
        3,
        2,
        False,
    )
