"""The common item every source is read into, before the merge (docs/specs-collecte.md, step 2).

Which source field goes into which item field: docs/stockage.md.
"""

import re
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)

# The sources of seed_sources.sql: a test keeps both lists equal.
SourceCode = Literal[
    "github", "arxiv", "cisa_kev", "clipper", "tldr", "zotero", "gh_archive"
]

# The kinds of item of schema.sql: a test keeps both lists equal.
ItemKind = Literal[
    "paper", "vulnerability", "newsletter_article", "release", "advisory"
]

# knownRansomwareCampaignUse of CISA KEV.
RansomwareUse = Literal["Known", "Unknown"]

CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
# Kept as given, not as pydantic's HttpUrl, which rewrites it (adds a final slash): the merge
# compares URLs as text.
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$")]
CveId = Annotated[str, StringConstraints(pattern=r"^CVE-\d{4}-\d{4,}$")]

# The fields each kind must fill, so that an entry the base would refuse is refused when read:
# one refused row would otherwise fail the whole import.
REQUIRED_FIELDS_BY_KIND = {
    "paper": ("summary", "published_at", "revised_at"),
    "vulnerability": (
        "cve",
        "summary",
        "published_at",
        "vendor",
        "product",
        "ransomware_use",
    ),
}
KEV_FIELDS = ("vendor", "product", "ransomware_use")
KINDS_WITH_CVE = ("vulnerability", "advisory")


class Item(BaseModel):
    # strict: a date given as text is refused, not parsed.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source_code: SourceCode
    source_item_id: NonEmptyText
    kind: ItemKind
    title: NonEmptyText
    url: HttpsUrl
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

    @model_validator(mode="after")
    def check_the_fields_of_its_kind(self) -> "Item":
        check_required_fields(self)
        check_kev_fields(self)
        check_cve(self)
        return self


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


def check_kev_fields(item: Item) -> None:
    filled = [field for field in KEV_FIELDS if getattr(item, field) is not None]
    if filled and item.kind != "vulnerability":
        raise ValueError(f"a {item.kind} item with {', '.join(filled)}")


def check_cve(item: Item) -> None:
    if item.cve is not None and item.kind not in KINDS_WITH_CVE:
        raise ValueError(f"a {item.kind} item with a CVE")
