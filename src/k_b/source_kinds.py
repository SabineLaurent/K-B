"""SOURCE_KINDS: the only declaration of the sources, one kind per entry, in collection order.

In the package, only cli.py imports it: it gives it to the collection (E) and to the import
(T then L).
"""

from k_b import (
    arxiv_papers,
    arxiv_source,
    cisa_kev,
    cisa_kev_source,
    github_advisories,
    github_advisories_source,
    github_most_starred,
    github_most_starred_source,
    github_releases,
    github_releases_source,
    tldr_source,
)
from k_b.arxiv_source import ArxivSource
from k_b.cisa_kev_source import CisaKevSource
from k_b.github_advisories_source import GithubAdvisoriesSource
from k_b.github_most_starred_source import GithubMostStarredSource
from k_b.github_releases_source import GithubReleasesSource
from k_b.source import SourceKind
from k_b.tldr_source import TRACKED_EDITIONS, TldrSource
from k_b.tracked_repositories import TRACKED_REPOSITORIES, list_packages_by_ecosystem

SOURCE_KINDS = (
    SourceKind(cisa_kev_source.FOLDER_PREFIX, (CisaKevSource(),), cisa_kev.READER),
    SourceKind(
        github_releases_source.FOLDER_PREFIX,
        tuple(
            GithubReleasesSource(repository.name) for repository in TRACKED_REPOSITORIES
        ),
        github_releases.READER,
    ),
    SourceKind(
        github_advisories_source.FOLDER_PREFIX,
        tuple(
            GithubAdvisoriesSource(ecosystem, packages)
            for ecosystem, packages in list_packages_by_ecosystem(
                TRACKED_REPOSITORIES
            ).items()
        ),
        github_advisories.READER,
    ),
    SourceKind(
        github_most_starred_source.FOLDER_PREFIX,
        (GithubMostStarredSource(),),
        github_most_starred.READER,
    ),
    SourceKind(arxiv_source.FOLDER_PREFIX, (ArxivSource(),), arxiv_papers.READER),
    # No reader yet: its pages are skipped at the import until #57.
    SourceKind(
        tldr_source.FOLDER_PREFIX,
        tuple(TldrSource(edition) for edition in TRACKED_EDITIONS),
        None,
    ),
)
