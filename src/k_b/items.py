"""The common item every source is read into, before the import (docs/specs-collecte.md, step 2).

Which source field goes into which item field: docs/stockage.md.

And the row of a GH Archive ranking, which is not an item: the base constrains it, and the
import, which cannot import a source, writes it.
"""

import re
import unicodedata
from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

# The sources of seed_sources.sql: a test keeps both lists equal.
SourceCode = Literal[
    "github", "arxiv", "cisa_kev", "clipper", "tldr", "zotero", "gh_archive"
]

# The kinds of item of schema.sql: a test keeps both lists equal.
ItemKind = Literal[
    "paper",
    "vulnerability",
    "newsletter_article",
    "release",
    "advisory",
    "zotero_entry",
]

# knownRansomwareCampaignUse of CISA KEV.
RansomwareUse = Literal["Known", "Unknown"]

CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")
# The slug of a newsletter edition, as in https://tldr.tech/<slug>/<YYYY-MM-DD>.
EDITION_SLUG = re.compile(r"[a-z]+")
# An arXiv identifier without its version, as text: the form of since 2007 (2609.31282), or the
# one of before (hep-th/9901001, math.GT/0309136). sources/arxiv.py reads it in the identifier
# of a paper, sources/zotero.py in the reference of a document. [0-9], not \d: \d matches any
# Unicode digit, and a fullwidth one would make another publication.
ARXIV_ID = r"(?:[0-9]{4}\.[0-9]{4,5}|[a-z]+(?:-[a-z]+)?(?:\.[A-Z]{2})?/[0-9]{7})"
# The key Zotero gives a document or an annotation; the GLOB of schema.sql. Zotero's own
# alphabet is narrower: this form refuses no key it gives.
ZOTERO_KEY = r"[0-9A-Z]{8}"
# The largest integer SQLite holds, and BigQuery gives (INT64).
MAX_INT64 = 2**63 - 1
# The longest name a ranking may write in trend.repository_name, held by a CHECK too. A wide
# bound, not the one of GitHub: the longest of the collection of 2026-10-11 has 38 characters.
TREND_REPOSITORY_NAME_MAX_LENGTH = 255


def check_url_can_be_normalized(url: str) -> str:
    """Refuse the URL urlsplit refuses (an unclosed bracket, a host NFKC rewrites), and the URL
    without a host, which may be "https://" once its utm_* parameters are removed: merge.py
    splits every URL at the import, then validates the item again, where one refused would
    stop it all."""
    try:
        host = urlsplit(url).hostname
    except ValueError:
        # The error of urlsplit quotes the host as written: only the state is kept.
        raise ValueError(f"url cannot be split: {len(url)} characters") from None
    if not host:
        raise ValueError(f"url without a host: {len(url)} characters")
    return url


def check_text_has_no_control_character(text: str) -> str:
    """Refuse a control character, a NUL among them. SQLite stops a GLOB and a length() at the
    first NUL: the base would refuse, or measure short, a text the pattern accepts. Another
    one (an escape sequence) would reach the terminal that displays the text."""
    if any(unicodedata.category(character) == "Cc" for character in text):
        # A named error type: the refusal is told apart from any other value error.
        raise PydanticCustomError(
            "control_character",
            "text with a control character: {length} characters",
            {"length": len(text)},
        )
    return text


NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
# Kept as given, not as pydantic's HttpUrl, which rewrites it (adds a final slash): the base
# keeps the URL the source gave, without its utm_* parameters (merge.py). http is accepted for
# a Zotero entry only (check_url_scheme): Zotero keeps the URL a document was saved from.
WebUrl = Annotated[
    str,
    StringConstraints(pattern=r"^https?://\S+$"),
    AfterValidator(check_url_can_be_normalized),
]
CveId = Annotated[str, StringConstraints(pattern=r"^CVE-\d{4}-\d{4,}$")]
# owner/name; the GLOB of tracked_repository.repository_name in schema.sql.
RepositoryName = Annotated[str, StringConstraints(pattern=r"^[^/\s]+/[^/\s]+$")]
# The CHECK of newsletter_article.edition in schema.sql. Anchored, and given as text: pydantic
# searches an unanchored pattern, and a compiled one would accept a final line break.
NewsletterEdition = Annotated[
    str, StringConstraints(pattern=f"^{EDITION_SLUG.pattern}$")
]
ArxivId = Annotated[str, StringConstraints(pattern=f"^{ARXIV_ID}$")]
ZoteroKey = Annotated[str, StringConstraints(pattern=f"^{ZOTERO_KEY}$")]

# The fields each kind must fill, so that an entry the base would refuse is refused when read:
# one refused row would otherwise fail the whole import.
REQUIRED_FIELDS_BY_KIND = {
    "paper": ("url", "summary", "published_at", "revised_at"),
    "vulnerability": (
        "url",
        "cve",
        "summary",
        "published_at",
        "vendor",
        "product",
        "ransomware_use",
    ),
    "release": ("url", "published_at", "repository_name", "tag_name"),
    "advisory": ("url", "published_at"),
    "newsletter_article": ("url", "summary", "published_at", "edition", "rank"),
    # A Zotero entry may have no URL (ADR of 2026-10-13).
    "zotero_entry": ("item_type", "saved_at"),
}
# The source of each kind. Written to a reference table as the item of its source of truth, an
# item of another source would mark a CVE as exploited, or overwrite a paper; a release or an
# advisory is a GitHub subtype, a newsletter article a TLDR one, an entry a Zotero one.
SOURCE_BY_KIND = {
    "paper": "arxiv",
    "vulnerability": "cisa_kev",
    "release": "github",
    "advisory": "github",
    "newsletter_article": "tldr",
    "zotero_entry": "zotero",
}
# The fields only one kind may fill.
FIELDS_OF_ONE_KIND = {
    "vulnerability": ("vendor", "product", "ransomware_use"),
    "release": ("repository_name", "tag_name", "release_name"),
    "advisory": ("package_names",),
    "newsletter_article": ("edition", "rank"),
    "zotero_entry": ("item_type", "arxiv_id", "highlights"),
}
KINDS_WITH_CVE = ("vulnerability", "advisory")
KINDS_WITH_HTTP_URL = ("zotero_entry",)

# The longest text a source may write in each column of schema.sql, in characters, by kind and
# by the field that fills the column. Held twice (ADR of 2026-10-08): here when the raw is
# read, and by a CHECK of the column; a test keeps both equal.
CVE_MAX_LENGTH = 20
MAX_LENGTH_BY_KIND: dict[ItemKind, dict[str, int]] = {
    "paper": {"source_item_id": 20, "title": 500, "summary": 5_000},
    "vulnerability": {
        "cve": CVE_MAX_LENGTH,
        "title": 500,
        "summary": 5_000,
        "vendor": 200,
        "product": 500,
    },
    "release": {
        "tag_name": 255,
        "release_name": 255,
        "summary": 125_000,
        "url": 2_000,
    },
    "advisory": {
        "source_item_id": 19,
        "cve": CVE_MAX_LENGTH,
        "title": 1_024,
        "url": 2_000,
    },
    "newsletter_article": {
        "edition": 20,
        "title": 500,
        "summary": 5_000,
        "url": 2_000,
    },
    # Wide bounds: 91 characters at most for a title of the extract of 2026-10-13.
    "zotero_entry": {"item_type": 100, "title": 1_000, "url": 2_000, "arxiv_id": 20},
}
# The lists written as JSON: the most elements, held by a CHECK too, and the longest element,
# held here only (a CHECK of SQLite cannot go through the elements of a JSON list).
MAX_COUNT_BY_KIND: dict[ItemKind, dict[str, int]] = {
    "paper": {"authors": 1_000},
    "advisory": {"package_names": 100},
}
MAX_ELEMENT_LENGTH_BY_KIND: dict[ItemKind, dict[str, int]] = {
    "paper": {"authors": 200},
    "advisory": {"package_names": 255},
}


# The longest text of a highlight, in characters, held by a CHECK of highlight too; a test keeps
# both equal. A wide bound: 825 characters at most in the extract of 2026-10-13.
HIGHLIGHT_MAX_LENGTH_BY_FIELD = {"text": 10_000, "comment": 10_000}


class Highlight(BaseModel):
    """A highlight of a PDF of a Zotero entry: a row of the highlight table, written with its
    entry."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    zotero_key: ZoteroKey
    # Absent when Zotero gives none: the highlight is kept for its comment (decision of
    # 2026-10-13). A highlight without either is not one (check_text_or_comment).
    text: Annotated[str, Field(max_length=HIGHLIGHT_MAX_LENGTH_BY_FIELD["text"])] | None
    comment: (
        Annotated[str, Field(max_length=HIGHLIGHT_MAX_LENGTH_BY_FIELD["comment"])]
        | None
    )
    # dateAdded of Zotero.
    highlighted_at: AwareDatetime

    @model_validator(mode="after")
    def check_text_or_comment(self) -> "Highlight":
        if self.text is None and self.comment is None:
            raise ValueError("a highlight without text or comment")
        return self


class Item(BaseModel):
    # strict: a date given as text is refused, not parsed.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source_code: SourceCode
    source_item_id: NonEmptyText
    kind: ItemKind
    title: NonEmptyText
    # None for a Zotero entry only (REQUIRED_FIELDS_BY_KIND).
    url: WebUrl | None = None
    authors: tuple[NonEmptyText, ...] = ()
    published_at: AwareDatetime | None = None
    # arXiv only: the date of the version read.
    revised_at: AwareDatetime | None = None
    # Clipper and Zotero only: the day the document was saved by hand.
    saved_at: AwareDatetime | None = None
    summary: str | None = None
    collected_at: AwareDatetime
    # Relative to the raw folder, so the base can be rebuilt from a copy of it elsewhere.
    raw_file_path: NonEmptyText
    # CISA KEV only (vulnerability): vendorProject, product, knownRansomwareCampaignUse.
    vendor: NonEmptyText | None = None
    product: NonEmptyText | None = None
    ransomware_use: RansomwareUse | None = None
    # A vulnerability (CISA KEV) or an advisory (GitHub).
    cve: CveId | None = None
    # GitHub release only: its repository, tag_name, and name (None when GitHub gives none).
    repository_name: RepositoryName | None = None
    tag_name: NonEmptyText | None = None
    release_name: str | None = None
    # GitHub advisory only: the affected packages, each once.
    package_names: tuple[NonEmptyText, ...] = ()
    # Newsletter article only: the slug of its edition, and its position in the edition page,
    # from 1. published_at is the day of the edition, at midnight UTC.
    edition: NewsletterEdition | None = None
    rank: Annotated[int, Field(ge=1, le=MAX_INT64)] | None = None
    # Zotero entry only: source_item_id is its Zotero key; its type of document, its arXiv
    # reference without version, and the highlights of its PDF, in the order of the extract.
    item_type: NonEmptyText | None = None
    arxiv_id: ArxivId | None = None
    highlights: tuple[Highlight, ...] = ()

    @model_validator(mode="after")
    def check_the_fields_of_its_kind(self) -> "Item":
        check_source(self)
        check_required_fields(self)
        check_fields_of_other_kinds(self)
        check_cve(self)
        check_lengths(self)
        check_url_scheme(self)
        check_zotero_key(self)
        return self


def check_source(item: Item) -> None:
    source_code = SOURCE_BY_KIND.get(item.kind, item.source_code)
    if item.source_code != source_code:
        raise ValueError(f"a {item.kind} item from {item.source_code}")


def check_required_fields(item: Item) -> None:
    missing = [
        field
        for field in REQUIRED_FIELDS_BY_KIND.get(item.kind, ())
        if getattr(item, field) is None
    ]
    if missing:
        raise ValueError(f"a {item.kind} item without {', '.join(missing)}")
    if item.kind == "paper" and not item.authors:
        raise ValueError("a paper item without authors")
    if item.kind == "advisory" and not item.package_names:
        raise ValueError("an advisory item without packages")


def check_fields_of_other_kinds(item: Item) -> None:
    filled = [
        field
        for kind, fields in FIELDS_OF_ONE_KIND.items()
        if kind != item.kind
        for field in fields
        if getattr(item, field) not in (None, ())
    ]
    if filled:
        raise ValueError(f"a {item.kind} item with {', '.join(filled)}")


def check_cve(item: Item) -> None:
    if item.cve is not None and item.kind not in KINDS_WITH_CVE:
        raise ValueError(f"a {item.kind} item with a CVE")


def check_url_scheme(item: Item) -> None:
    if (
        item.url is not None
        and not item.url.startswith("https://")
        and item.kind not in KINDS_WITH_HTTP_URL
    ):
        raise ValueError(
            f"url not https for a {item.kind} item: {len(item.url)} characters"
        )


def check_zotero_key(item: Item) -> None:
    if item.kind == "zotero_entry" and not re.fullmatch(
        ZOTERO_KEY, item.source_item_id
    ):
        raise ValueError(
            f"source_item_id not a Zotero key: {len(item.source_item_id)} characters"
        )


def check_lengths(item: Item) -> None:
    """Refuse a text or a list longer than its maximum: the message says which field, its
    length and the maximum."""
    too_long = list_texts_too_long(item) + list_lists_too_long(item)
    if too_long:
        raise ValueError("; ".join(too_long))


def list_texts_too_long(item: Item) -> list[str]:
    too_long = []
    for field, maximum in MAX_LENGTH_BY_KIND.get(item.kind, {}).items():
        text = getattr(item, field)
        if text is not None and len(text) > maximum:
            too_long.append(
                f"{field} too long: {len(text)} characters, maximum {maximum}"
            )
    return too_long


def list_lists_too_long(item: Item) -> list[str]:
    too_long = []
    for field, maximum in MAX_COUNT_BY_KIND.get(item.kind, {}).items():
        count = len(getattr(item, field))
        if count > maximum:
            too_long.append(f"{field} too long: {count} elements, maximum {maximum}")
    for field, maximum in MAX_ELEMENT_LENGTH_BY_KIND.get(item.kind, {}).items():
        longest = max(map(len, getattr(item, field)), default=0)
        if longest > maximum:
            too_long.append(
                f"an element of {field} too long: {longest} characters,"
                f" maximum {maximum}"
            )
    return too_long


class TrendRow(BaseModel):
    """A repository of a GH Archive ranking, in a window of 3 days: a row of the trend table,
    not an item (ADR of 2026-10-08). Each CHECK of trend refuses nothing this row accepts; a
    test keeps both in step."""

    model_config = ConfigDict(strict=True, extra="forbid")

    # The last day of the window.
    window_end: date
    # repo.id of GitHub, and the last name seen in the window.
    repository_id: Annotated[int, Field(gt=0, le=MAX_INT64)]
    repository_name: Annotated[
        RepositoryName,
        Field(max_length=TREND_REPOSITORY_NAME_MAX_LENGTH),
        AfterValidator(check_text_has_no_control_character),
    ]
    stars_gained: Annotated[int, Field(ge=0, le=MAX_INT64)]
    forks_gained: Annotated[int, Field(ge=0, le=MAX_INT64)]
