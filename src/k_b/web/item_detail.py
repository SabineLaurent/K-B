"""The page of the detail of an item, without input nor output: the id of its address, then what
the page shows of each kind, in the order of the mockups (docs/site-web.md, "Détail")."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, assert_never

from k_b.items import MAX_INT64
from k_b.web.data_api_client import (
    AdvisoryDetail,
    ItemDetail,
    NewsletterArticleDetail,
    PaperDetail,
    ReleaseDetail,
    VulnerabilityDetail,
)
from k_b.web.feed import (
    LABELS_BY_KIND,
    NO_TITLE,
    keep_https_link,
    write_link_note,
    write_newsletter_name,
)
from k_b.web.french_dates import write_day
from k_b.web.received_text import (
    clean_received_text,
    clean_received_value,
    is_blank,
)

# Digits of ASCII only, without a zero first: one address for each item (Opquast 2025, rule 169).
# The one form of the id of an item in the site: #403 changes it here alone.
ITEM_ID = re.compile(r"[1-9][0-9]{0,18}")
# A line of blanks, any space of Unicode, counts as empty: it ends a paragraph, and goes at the start
# or the end of one; the indent of a line not blank is kept (D3).
BLANK_LINES = re.compile(r"\n(?:[^\S\n]*\n)+")
EDGE_BLANK_LINES = re.compile(r"^(?:[^\S\n]*\n)+|(?:\n[^\S\n]*)+$")

type Banner = Literal[
    "vulnerability_in_catalog",
    "vulnerability_withdrawn",
    "advisory_in_catalog",
    "advisory_absent_from_catalog",
    "advisory_without_cve",
]

RANSOMWARE_USE_LABELS = {"Known": "Connu", "Unknown": "Inconnu"}
CVE_MEANING = "Common Vulnerabilities and Exposures"
NO_CVE = "Aucune"
NO_PACKAGE = "Aucun"
NOT_GIVEN = "Non renseigné"
NO_TAG = "sans nom"
# What the page says of a long text empty or blank; an advisory has none.
EMPTY_TEXT_BY_KIND = {
    "paper": "Aucun résumé.",
    "newsletter_article": "Aucun résumé.",
    "vulnerability": "Aucune description.",
    "release": "Aucune note de version.",
}


@dataclass(frozen=True)
class Day:
    """A day as its time element gives it: ISO for the machine, the month in letters for people."""

    iso: str
    text: str


@dataclass(frozen=True)
class LinePart:
    """A part of the line under the kind: a text, in the font of the code for an identifier, or a
    label followed by its day."""

    text: str
    is_code: bool = False
    day: Day | None = None


@dataclass(frozen=True)
class Fact:
    """A term of the facts and its values; a list for the packages; lang en for a text of the
    source written in English (RGAA 8.7)."""

    term: str
    values: tuple[str, ...]
    term_meaning: str | None = None
    is_code: bool = False
    lang: str | None = None
    is_list: bool = False


@dataclass(frozen=True)
class ItemText:
    """A long text of the item under its heading, cut in paragraphs."""

    heading: str
    id: str
    paragraphs: tuple[str, ...]
    lang: str | None


@dataclass(frozen=True)
class ItemPage:
    """The detail of an item as its page shows it, every text received cleaned."""

    page_title: str
    kind_label: str
    kind_lang: str | None
    line: tuple[LinePart, ...]
    title: str
    title_lang: str | None
    authors: str | None
    banner: Banner | None
    banner_day: Day | None
    facts: tuple[Fact, ...]
    texts: tuple[ItemText, ...]
    empty_text: str | None
    # None: a URL out of https, never made a link.
    link: str | None
    link_label: str
    link_note: str
    link_lang: str | None


def read_item_id(text: str) -> int | None:
    """The id of an item in the address of its detail; None out of its form or beyond 64 bits."""
    if not ITEM_ID.fullmatch(text):
        return None
    item_id = int(text)
    return item_id if item_id <= MAX_INT64 else None


def build_item_page(detail: ItemDetail) -> ItemPage:
    labels = LABELS_BY_KIND[detail.kind]
    title = clean_received_value(detail.title)
    banner = find_banner(detail)
    texts = build_texts(detail)
    return ItemPage(
        page_title=write_page_title(detail),
        kind_label=labels.card_label,
        kind_lang=labels.label_lang,
        line=build_line(detail),
        title=title or NO_TITLE,
        title_lang=labels.title_lang if title else None,
        authors=write_authors(detail) if isinstance(detail, PaperDetail) else None,
        banner=banner,
        banner_day=to_day(detail.withdrawn_at)
        if banner == "vulnerability_withdrawn" and detail.withdrawn_at
        else None,
        facts=build_facts(detail),
        texts=texts,
        empty_text=None if texts else EMPTY_TEXT_BY_KIND.get(detail.kind),
        link=keep_https_link(detail.url),
        link_label=labels.link_label,
        link_note=write_link_note(labels),
        link_lang=labels.link_lang,
    )


def write_page_title(detail: ItemDetail) -> str:
    """A title of its own for each item, in French and its codes (RGAA 8.6): a part of a title
    cannot be marked in English (RGAA 8.7)."""
    match detail:
        case PaperDetail():
            return f"Papier arXiv {detail.arxiv_id}"
        case VulnerabilityDetail():
            return f"Faille {detail.cve_id}"
        case AdvisoryDetail():
            return f"Alerte {detail.ghsa_id}"
        case ReleaseDetail():
            tag = clean_received_value(detail.tag_name) or NO_TAG
            return f"Version {tag} de {detail.repository_name}"
        case NewsletterArticleDetail():
            name = write_newsletter_name(detail.edition)
            return (
                f"Article {name} du {write_day(detail.source_date)}, n° {detail.rank}"
            )
        case _:
            assert_never(detail)


def build_line(detail: ItemDetail) -> tuple[LinePart, ...]:
    """The identifiers and the dates under the kind, as in the mockups."""
    published = to_day(detail.source_date)
    match detail:
        case PaperDetail():
            return (
                LinePart(f"arXiv {detail.arxiv_id}", is_code=True),
                LinePart("Publié le", day=published),
                LinePart(
                    "dernière version arXiv le", day=to_day(detail.arxiv_updated_at)
                ),
            )
        case VulnerabilityDetail():
            added = LinePart("Ajoutée au catalogue le", day=published)
            if detail.revised_at is None:
                return (added,)
            revised = LinePart(
                "modification vue par K-B le", day=to_day(detail.revised_at)
            )
            return (added, revised)
        case AdvisoryDetail():
            return (LinePart("Publiée le", day=published),)
        case ReleaseDetail():
            return (
                LinePart(detail.repository_name, is_code=True),
                write_tag(detail.tag_name),
                LinePart("Publiée le", day=published),
            )
        case NewsletterArticleDetail():
            return (
                LinePart(write_newsletter_name(detail.edition)),
                LinePart("édition du", day=published),
                LinePart(f"n° {detail.rank}"),
            )
        case _:
            assert_never(detail)


def to_day(moment: datetime) -> Day:
    return Day(moment.date().isoformat(), write_day(moment))


def write_tag(tag_name: str) -> LinePart:
    """The version, in the font of the code; sans nom, in French, when the cleaning leaves none."""
    tag = clean_received_value(tag_name)
    return LinePart(tag, is_code=True) if tag else LinePart(NO_TAG)


def write_authors(paper: PaperDetail) -> str | None:
    """The authors in the order of arXiv, after a visible label (C17); an author left empty by the
    cleaning left out, and no line without author."""
    names = [name for name in map(clean_received_value, paper.authors) if name]
    return "Auteurs: " + ", ".join(names) if names else None


def find_banner(detail: ItemDetail) -> Banner | None:
    """By the field exploited of the data API, never supposed true. A vulnerability withdrawn has
    the banner of its withdrawal, never one that says exploited (Sabine, 2026-11-11)."""
    if isinstance(detail, VulnerabilityDetail):
        if detail.withdrawn_at is not None:
            return "vulnerability_withdrawn"
        return "vulnerability_in_catalog" if detail.exploited else None
    if isinstance(detail, AdvisoryDetail):
        if detail.exploited is None:
            return "advisory_without_cve"
        if detail.exploited:
            return "advisory_in_catalog"
        return "advisory_absent_from_catalog"
    return None


def build_facts(detail: ItemDetail) -> tuple[Fact, ...]:
    if isinstance(detail, VulnerabilityDetail):
        return (
            Fact("CVE", (detail.cve_id,), term_meaning=CVE_MEANING, is_code=True),
            Fact(
                "Usage par des rançongiciels",
                (RANSOMWARE_USE_LABELS[detail.ransomware_use],),
            ),
            write_english_fact("Éditeur", detail.vendor),
            write_english_fact("Produit", detail.product),
        )
    if isinstance(detail, AdvisoryDetail):
        return (
            Fact(
                "Identifiant GitHub",
                (detail.ghsa_id,),
                is_code=True,
            ),
            Fact("CVE", (detail.cve_id,), is_code=True)
            if detail.cve_id
            else Fact("CVE", (NO_CVE,)),
            write_packages(detail),
        )
    return ()


def write_packages(advisory: AdvisoryDetail) -> Fact:
    """The packages of an advisory, a package left empty by the cleaning left out; Aucun when none
    is left."""
    packages = tuple(
        package for package in map(clean_received_value, advisory.packages) if package
    )
    if not packages:
        return Fact("Paquets touchés", (NO_PACKAGE,))
    return Fact("Paquets touchés", packages, is_code=True, is_list=True)


def build_texts(detail: ItemDetail) -> tuple[ItemText, ...]:
    """The long text of the source under its heading, in English by hypothesis, as the titles of
    the feed; none when it is empty or blank."""
    match detail:
        case PaperDetail() | NewsletterArticleDetail():
            heading, text_id, text = "Résumé", "resume", detail.summary
        case VulnerabilityDetail():
            heading, text_id, text = "Description", "description", detail.description
        case ReleaseDetail():
            # Plain text, never Markdown rendered (D3, Sabine, 2026-11-11).
            heading, text_id = "Notes de version, texte brut", "notes"
            text = detail.body or ""
        case AdvisoryDetail():
            return ()
        case _:
            assert_never(detail)
    paragraphs = split_paragraphs(text)
    return (ItemText(heading, text_id, paragraphs, "en"),) if paragraphs else ()


def write_english_fact(term: str, text: str) -> Fact:
    """A fact the source writes in English; Non renseigné, in French, when the base holds none."""
    value = clean_received_value(text)
    return Fact(term, (value,), lang="en") if value else Fact(term, (NOT_GIVEN,))


def split_paragraphs(text: str) -> tuple[str, ...]:
    """The text cleaned, cut at its blank lines, each paragraph keeping its lines but the blank
    ones at its start or its end."""
    blocks = BLANK_LINES.split(clean_received_text(text))
    return tuple(
        EDGE_BLANK_LINES.sub("", block) for block in blocks if not is_blank(block)
    )
