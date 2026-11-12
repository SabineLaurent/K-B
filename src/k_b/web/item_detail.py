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
    keep_https_link,
    write_link_note,
    write_newsletter_name,
)
from k_b.web.french_dates import write_day
from k_b.web.received_text import clean_received_text

# Digits of ASCII only, without a zero first: one address for each item (Opquast 2025, rule 169).
# The one form of the id of an item in the site: #403 changes it here alone.
ITEM_ID = re.compile(r"[1-9][0-9]{0,18}")
# A line of blanks counts as empty: it ends a paragraph.
BLANK_LINES = re.compile(r"\n(?:[ \t]*\n)+")

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
NO_RELEASE_NOTES = "Aucune note de version."


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
    return ItemPage(
        page_title=write_page_title(detail),
        kind_label=labels.card_label,
        kind_lang=labels.label_lang,
        line=build_line(detail),
        title=clean_received_text(detail.title),
        title_lang=labels.title_lang,
        authors=write_authors(detail) if isinstance(detail, PaperDetail) else None,
        banner=find_banner(detail),
        banner_day=to_day(detail.withdrawn_at)
        if isinstance(detail, VulnerabilityDetail) and detail.withdrawn_at
        else None,
        facts=build_facts(detail),
        texts=build_texts(detail),
        empty_text=NO_RELEASE_NOTES
        if isinstance(detail, ReleaseDetail) and not build_texts(detail)
        else None,
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
            return f"Alerte {clean_received_text(detail.ghsa_id)}"
        case ReleaseDetail():
            tag = clean_received_text(detail.tag_name)
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
                LinePart(clean_received_text(detail.tag_name), is_code=True),
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


def write_authors(paper: PaperDetail) -> str:
    """The authors in the order of arXiv, after a visible label (C17)."""
    return "Auteurs: " + ", ".join(map(clean_received_text, paper.authors))


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
            Fact("Éditeur", (clean_received_text(detail.vendor),), lang="en"),
            Fact("Produit", (clean_received_text(detail.product),), lang="en"),
        )
    if isinstance(detail, AdvisoryDetail):
        return (
            Fact(
                "Identifiant GitHub",
                (clean_received_text(detail.ghsa_id),),
                is_code=True,
            ),
            Fact("CVE", (detail.cve_id,), is_code=True)
            if detail.cve_id
            else Fact("CVE", (NO_CVE,)),
            Fact(
                "Paquets touchés",
                tuple(map(clean_received_text, detail.packages)),
                is_code=True,
                is_list=True,
            )
            if detail.packages
            else Fact("Paquets touchés", (NO_PACKAGE,)),
        )
    return ()


def build_texts(detail: ItemDetail) -> tuple[ItemText, ...]:
    """The long texts of the source, in English by hypothesis, as the titles of the feed."""
    match detail:
        case PaperDetail() | NewsletterArticleDetail():
            return (
                ItemText("Résumé", "resume", split_paragraphs(detail.summary), "en"),
            )
        case VulnerabilityDetail():
            paragraphs = split_paragraphs(detail.description)
            return (ItemText("Description", "description", paragraphs, "en"),)
        case ReleaseDetail():
            # Plain text, never Markdown rendered (D3, Sabine, 2026-11-11).
            notes = split_paragraphs(detail.body or "")
            if not notes:
                return ()
            return (ItemText("Notes de version, texte brut", "notes", notes, "en"),)
        case AdvisoryDetail():
            return ()
        case _:
            assert_never(detail)


def split_paragraphs(text: str) -> tuple[str, ...]:
    """The text cleaned, cut at its blank lines, each paragraph keeping its lines."""
    blocks = BLANK_LINES.split(clean_received_text(text))
    return tuple(block.strip("\n") for block in blocks if block.strip())
