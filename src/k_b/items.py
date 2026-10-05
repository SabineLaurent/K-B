"""The common item every source is read into, before the merge (docs/specs-collecte.md, step 2).

Which source field goes into which item field: docs/stockage.md.
"""

from datetime import UTC, datetime, time
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from k_b.arxiv_papers import Paper
from k_b.cisa_kev import Vulnerability
from k_b.github_advisories import Advisory
from k_b.github_most_starred import StarredRepository
from k_b.github_releases import Release

# The sources of seed_sources.sql: a test keeps both lists equal.
SourceCode = Literal["github", "arxiv", "cisa_kev", "clipper", "tldr", "zotero", "gh_archive"]

NVD_PAGE_URL = "https://nvd.nist.gov/vuln/detail/"

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
    repository_name: RepositoryName | None = None


def convert_paper(paper: Paper, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code="arxiv",
        source_item_id=paper.arxiv_id,
        title=paper.title,
        url=paper.url,
        authors=paper.authors,
        published_at=paper.published_at,
        revised_at=paper.updated_at,
        summary=paper.summary,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
    )


def convert_vulnerability(
    vulnerability: Vulnerability, collected_at: datetime, raw_file_path: str
) -> Item:
    return Item(
        source_code="cisa_kev",
        source_item_id=vulnerability.cve_id,
        title=vulnerability.vulnerability_name,
        url=NVD_PAGE_URL + vulnerability.cve_id,
        # dateAdded is a day: stored at midnight UTC, a writing convention (docs/stockage.md).
        published_at=datetime.combine(vulnerability.date_added, time(), tzinfo=UTC),
        summary=vulnerability.short_description,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
        cve=vulnerability.cve_id,
    )


def convert_release(release: Release, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code="github",
        source_item_id=str(release.release_id),
        title=f"{release.repository} {release.name or release.tag_name}",
        url=release.url,
        published_at=release.published_at,
        summary=release.body,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
    )


def convert_advisory(advisory: Advisory, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code="github",
        source_item_id=advisory.ghsa_id,
        title=advisory.summary,
        url=advisory.url,
        published_at=advisory.published_at,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
        cve=advisory.cve_id,
    )


def convert_starred_repository(
    repository: StarredRepository, collected_at: datetime, raw_file_path: str
) -> Item:
    return Item(
        source_code="github",
        source_item_id=repository.full_name,
        title=repository.full_name,
        url=repository.url,
        summary=repository.description,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
        repository_name=repository.full_name,
    )
