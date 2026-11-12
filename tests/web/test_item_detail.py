"""The page of the detail of an item, without input nor output: the id of its address, its line of
kind and dates, its facts, its banner, its texts, and every text received cleaned
(docs/site-web.md, "Détail")."""

import json

import pytest
from item_fixture import (
    ADVISORY_ABSENT_FROM_CATALOG,
    ADVISORY_IN_CATALOG,
    ADVISORY_WITHOUT_CVE,
    NEWSLETTER_ARTICLE,
    PAPER,
    RELEASE,
    VULNERABILITY,
    WITHDRAWN_VULNERABILITY,
    make_detail,
)

from k_b.core.config import BIDI_CONTROLS
from k_b.web.data_api_client import DETAIL
from k_b.web.item_detail import (
    Day,
    Fact,
    ItemText,
    LinePart,
    build_item_page,
    read_item_id,
    split_paragraphs,
)
from k_b.web.received_text import clean_received_text


def build(item_id, **changes):
    """The page of the detail of item_id, read from JSON as the client reads the data API."""
    return build_item_page(
        DETAIL.validate_json(json.dumps(make_detail(item_id, **changes)))
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "0",
        "01",
        "+1",
        "-1",
        "1.0",
        "abc",
        " 1",
        "1\n",
        "1" * 20,
        str(2**63),
        # An Arabic-Indic digit and a fullwidth digit: int() would read both.
        chr(0x0661),
        chr(0xFF11),
    ],
)
def test_an_id_out_of_its_form_is_refused(text):
    assert read_item_id(text) is None


@pytest.mark.parametrize(("text", "item_id"), [("1", 1), (str(2**63 - 1), 2**63 - 1)])
def test_an_id_in_its_form_is_read(text, item_id):
    assert read_item_id(text) == item_id


def test_the_page_of_a_paper():
    page = build(PAPER)

    assert page.page_title == "Papier arXiv 2609.31282"
    assert (page.kind_label, page.kind_lang) == ("Papier", None)
    assert page.line == (
        LinePart("arXiv 2609.31282", is_code=True),
        LinePart("Publié le", day=Day("2026-09-25", "25 septembre 2026")),
        LinePart(
            "dernière version arXiv le", day=Day("2026-09-25", "25 septembre 2026")
        ),
    )
    assert page.title.startswith("Resource-Optimized")
    assert page.title_lang == "en"
    assert page.authors == "Auteurs: Ada May Fenwick"
    assert page.banner is None
    assert page.facts == ()
    assert page.texts == (
        ItemText(
            "Résumé",
            "resume",
            (make_detail(PAPER)["summary"],),
            "en",
        ),
    )
    assert page.link == "https://arxiv.org/abs/2609.31282"
    assert page.link_label == "Lire sur arxiv.org"
    assert page.link_note == "en anglais, site externe, nouvel onglet"


def test_the_authors_are_in_the_order_of_arxiv():
    page = build(PAPER, authors=["Ada May Fenwick", "Lena Marsh", "Zoë Quinn"])

    assert page.authors == "Auteurs: Ada May Fenwick, Lena Marsh, Zoë Quinn"


def test_the_page_of_a_vulnerability_in_the_catalog():
    page = build(VULNERABILITY)

    assert page.page_title == "Faille CVE-2026-86950"
    assert page.line == (
        LinePart("Ajoutée au catalogue le", day=Day("2026-09-29", "29 septembre 2026")),
    )
    assert page.banner == "vulnerability_in_catalog"
    assert page.facts == (
        Fact(
            "CVE",
            ("CVE-2026-86950",),
            term_meaning="Common Vulnerabilities and Exposures",
            is_code=True,
        ),
        Fact("Usage par des rançongiciels", ("Inconnu",)),
        Fact("Éditeur", ("Apple",), lang="en"),
        Fact("Produit", ("Multiple Products",), lang="en"),
    )
    assert [text.heading for text in page.texts] == ["Description"]
    assert page.link_label == "Voir la fiche sur nvd.nist.gov"


def test_a_vulnerability_revised_gives_the_date_k_b_saw_the_change():
    page = build(VULNERABILITY, revised_at="2026-10-06T09:30:00Z")

    assert page.line[-1] == LinePart(
        "modification vue par K-B le", day=Day("2026-10-06", "6 octobre 2026")
    )


@pytest.mark.parametrize(("use", "label"), [("Known", "Connu"), ("Unknown", "Inconnu")])
def test_the_use_by_ransomware_is_written_in_french(use, label):
    page = build(VULNERABILITY, ransomware_use=use)

    assert Fact("Usage par des rançongiciels", (label,)) in page.facts


def test_a_vulnerability_withdrawn_has_the_banner_of_its_withdrawal_never_exploited():
    page = build(WITHDRAWN_VULNERABILITY)

    assert page.banner == "vulnerability_withdrawn"
    assert page.banner_day == Day("2026-10-06", "6 octobre 2026")


def test_a_vulnerability_not_exploited_by_the_api_has_no_banner():
    """exploited is always true for a vulnerability: the site reads it, never supposes it."""
    assert build(VULNERABILITY, exploited=False).banner is None


@pytest.mark.parametrize(
    ("item_id", "banner"),
    [
        (ADVISORY_IN_CATALOG, "advisory_in_catalog"),
        (ADVISORY_ABSENT_FROM_CATALOG, "advisory_absent_from_catalog"),
        (ADVISORY_WITHOUT_CVE, "advisory_without_cve"),
    ],
)
def test_the_banner_of_an_advisory_has_three_states(item_id, banner):
    assert build(item_id).banner == banner


def test_the_page_of_an_advisory():
    page = build(ADVISORY_ABSENT_FROM_CATALOG)

    assert page.page_title == "Alerte GHSA-3644-q5cj-c5c7"
    assert page.line == (LinePart("Publiée le", day=Day("2026-05-13", "13 mai 2026")),)
    assert page.facts == (
        Fact("Identifiant GitHub", ("GHSA-3644-q5cj-c5c7",), is_code=True),
        Fact("CVE", ("CVE-2026-45134",), is_code=True),
        Fact(
            "Paquets touchés",
            ("langsmith", "langchain-classic", "langchain"),
            is_code=True,
            is_list=True,
        ),
    )
    assert page.texts == ()
    assert page.link_label == "Voir sur GitHub"


def test_an_advisory_without_cve_nor_package_says_none():
    page = build(ADVISORY_WITHOUT_CVE, packages=[])

    assert Fact("CVE", ("Aucune",)) in page.facts
    assert Fact("Paquets touchés", ("Aucun",)) in page.facts


def test_the_page_of_a_release():
    page = build(RELEASE)

    assert page.page_title == "Version v2.1.287 de anthropics/claude-code"
    assert (page.kind_label, page.kind_lang) == ("Release", "en")
    assert page.line == (
        LinePart("anthropics/claude-code", is_code=True),
        LinePart("v2.1.287", is_code=True),
        LinePart("Publiée le", day=Day("2026-10-01", "1er octobre 2026")),
    )
    [notes] = page.texts
    assert (notes.heading, notes.id, notes.lang) == (
        "Notes de version, texte brut",
        "notes",
        "en",
    )
    assert notes.paragraphs[0] == "## What's changed"
    assert notes.paragraphs[1].startswith("- Added Claude Mods")
    assert page.empty_text is None


@pytest.mark.parametrize("body", [None, "", " \n\t\n "])
def test_a_release_without_notes_says_so(body):
    page = build(RELEASE, body=body)

    assert page.texts == ()
    assert page.empty_text == "Aucune note de version."


def test_the_page_of_a_newsletter_article():
    page = build(NEWSLETTER_ARTICLE)

    assert page.page_title == "Article TLDR AI du 7 octobre 2026, n° 3"
    assert page.line == (
        LinePart("TLDR AI"),
        LinePart("édition du", day=Day("2026-10-07", "7 octobre 2026")),
        LinePart("n° 3"),
    )
    assert [text.heading for text in page.texts] == ["Résumé"]


def test_a_link_out_of_https_is_no_link():
    assert build(PAPER, url="http://arxiv.org/abs/2609.31282").link is None


def test_the_paragraphs_are_cut_at_the_blank_lines_their_lines_kept():
    text = "First line\nsecond line\n\n  \nSecond paragraph\n\n\n\nThird"

    assert split_paragraphs(text) == (
        "First line\nsecond line",
        "Second paragraph",
        "Third",
    )


def test_a_text_received_loses_its_control_characters_but_tab_and_line_feed():
    text = "a" + chr(0x07) + "b\tc" + chr(0x1B) + "d\ne" + chr(0x85) + "f"

    assert clean_received_text(text) == "ab\tcd\nef"


def test_a_text_received_has_its_line_endings_made_line_feeds():
    assert clean_received_text("a\r\nb\rc") == "a\nb\nc"


@pytest.mark.parametrize(
    "noncharacter", [0xFDD0, 0xFDEF, 0xFFFE, 0xFFFF, 0x1FFFE, 0x10FFFF]
)
def test_a_text_received_loses_its_noncharacters(noncharacter):
    assert clean_received_text("a" + chr(noncharacter) + "b") == "ab"


def test_a_text_received_loses_a_lone_surrogate():
    """Its encoding in UTF-8 would fail the page."""
    assert clean_received_text("a" + chr(0xD800) + "b") == "ab"


def test_every_text_of_a_detail_is_cleaned():
    bell = chr(0x07)
    page = build(
        RELEASE,
        title=f"Title{bell}",
        body=f"Notes{bell}\r\n\r\nMore",
        tag_name=f"v1{bell}",
    )

    assert page.title == "Title"
    assert page.texts[0].paragraphs == ("Notes", "More")
    assert page.page_title == "Version v1 de anthropics/claude-code"


@pytest.mark.parametrize(
    ("item_id", "field", "empty_text"),
    [
        (PAPER, "summary", "Aucun résumé."),
        (NEWSLETTER_ARTICLE, "summary", "Aucun résumé."),
        (VULNERABILITY, "description", "Aucune description."),
    ],
)
@pytest.mark.parametrize("text", ["", "  \n\n "])
def test_a_summary_or_a_description_empty_or_blank_says_so(
    item_id, field, empty_text, text
):
    """The base bounds their length only (schema.sql): an empty text is a value it holds."""
    page = build(item_id, **{field: text})

    assert page.texts == ()
    assert page.empty_text == empty_text


def test_a_title_left_empty_by_the_cleaning_is_said_without_title_in_french():
    """NonEmptyText lets through a title of control characters alone."""
    page = build(PAPER, title=chr(0x85) + chr(0xFFFE))

    assert (page.title, page.title_lang) == ("Sans titre", None)


def test_a_real_title_sans_titre_keeps_its_language():
    page = build(PAPER, title="Sans titre")

    assert (page.title, page.title_lang) == ("Sans titre", "en")


@pytest.mark.parametrize("control", sorted(BIDI_CONTROLS))
def test_a_text_received_loses_its_bidirectional_controls(control):
    """Never closed, an override would reorder the text after it in its line (U+202E)."""
    assert clean_received_text("v1.0" + control + " date") == "v1.0 date"


def test_an_empty_vendor_or_product_is_said_not_given():
    page = build(VULNERABILITY, vendor="", product=chr(0x07))

    assert Fact("Éditeur", ("Non renseigné",)) in page.facts
    assert Fact("Produit", ("Non renseigné",)) in page.facts


def test_a_tag_left_empty_by_the_cleaning_is_said_without_name():
    page = build(RELEASE, tag_name=chr(0x01))

    assert page.page_title == "Version sans nom de anthropics/claude-code"
    assert page.line[1] == LinePart("sans nom")


@pytest.mark.parametrize(
    ("authors", "line"),
    [
        (["", chr(0x07), "Lena Marsh"], "Auteurs: Lena Marsh"),
        ([""], None),
        ([], None),
    ],
)
def test_an_author_left_empty_is_left_out_and_no_author_no_line(authors, line):
    assert build(PAPER, authors=authors).authors == line


def test_a_line_of_unicode_blanks_ends_a_paragraph_and_blank_lines_around_go():
    """A no-break space or an ideographic space is a blank; the indent of a line is kept (D3)."""
    text = "   \nFixes bug\n\u00a0\nMore\n\u3000\n  indented line\n"

    assert split_paragraphs(text) == ("Fixes bug", "More", "  indented line")
