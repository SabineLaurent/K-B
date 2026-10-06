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

CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
# Kept as given, not as pydantic's HttpUrl, which rewrites it (adds a final slash): the merge
# compares URLs as text.
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$")]
CveId = Annotated[str, StringConstraints(pattern=r"^CVE-\d{4}-\d{4,}$")]
RepositoryName = Annotated[str, StringConstraints(pattern=r"^[^/\s]+/[^/\s]+$")]


class Item(BaseModel):
    # strict: a date given as text is refused, not parsed.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source_code: SourceCode
    source_item_id: NonEmptyText
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
    # Fields of the item's subtype in the base (docs/stockage.md): vulnerability, repository.
    cve: CveId | None = None
    # A GitHub advisory without CVE is still a vulnerability: the CVE alone cannot tell.
    is_vulnerability: bool = False
    repository_name: RepositoryName | None = None

    @model_validator(mode="after")
    def check_a_cve_is_a_vulnerability(self) -> "Item":
        if self.cve is not None and not self.is_vulnerability:
            raise ValueError("an item with a CVE must be a vulnerability")
        return self
