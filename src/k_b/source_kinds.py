"""SOURCE_KINDS: the only declaration of the sources, one kind per entry, in collection order.

In the package, only cli.py imports it: it gives it to the collection (E) and to the import
(T then L).
"""

from k_b.source_contract import SourceKind
from k_b.sources import (
    arxiv,
    cisa_kev,
    github_advisories,
    github_most_starred,
    github_releases,
    tldr,
)
from k_b.sources.arxiv import ArxivSource
from k_b.sources.cisa_kev import CisaKevSource
from k_b.sources.github_advisories import GithubAdvisoriesSource
from k_b.sources.github_most_starred import GithubMostStarredSource
from k_b.sources.github_releases import GithubReleasesSource
from k_b.sources.tldr import TRACKED_EDITIONS, TldrSource
from k_b.sources.tracked_repositories import (
    TRACKED_REPOSITORIES,
    list_packages_by_ecosystem,
)

SOURCE_KINDS = (
    SourceKind(cisa_kev.FOLDER_PREFIX, (CisaKevSource(),), cisa_kev.READER),
    SourceKind(
        github_releases.FOLDER_PREFIX,
        tuple(
            GithubReleasesSource(repository.name) for repository in TRACKED_REPOSITORIES
        ),
        github_releases.READER,
    ),
    SourceKind(
        github_advisories.FOLDER_PREFIX,
        tuple(
            GithubAdvisoriesSource(ecosystem, packages)
            for ecosystem, packages in list_packages_by_ecosystem(
                TRACKED_REPOSITORIES
            ).items()
        ),
        github_advisories.READER,
    ),
    SourceKind(
        github_most_starred.FOLDER_PREFIX,
        (GithubMostStarredSource(),),
        github_most_starred.READER,
    ),
    SourceKind(arxiv.FOLDER_PREFIX, (ArxivSource(),), arxiv.READER),
    # No reader yet: its pages are skipped at the import until #57.
    SourceKind(
        tldr.FOLDER_PREFIX,
        tuple(TldrSource(edition) for edition in TRACKED_EDITIONS),
        None,
    ),
)
