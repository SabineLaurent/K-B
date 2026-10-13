"""SOURCE_KINDS: the only declaration of the sources, one kind per entry, in collection order.

In the package, only cli.py imports it: it gives it to the collection (E) and to the import
(T then L). The Zotero and GH Archive kinds have no instance here: cli.py creates them, on a
machine that says where the Zotero data directory, or the BigQuery key, is.
"""

from k_b.source_contract import SourceKind
from k_b.sources import (
    arxiv,
    cisa_kev,
    gh_archive,
    github_advisories,
    github_most_starred,
    github_releases,
    tldr,
    zotero,
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
        # No reader: the ranking does not enter the base (decision "Tops", 2026-10-08).
        None,
    ),
    SourceKind(arxiv.FOLDER_PREFIX, (ArxivSource(),), arxiv.READER),
    SourceKind(
        tldr.FOLDER_PREFIX,
        tuple(TldrSource(edition) for edition in TRACKED_EDITIONS),
        tldr.READER,
    ),
    # No instance: cli.py adds ZoteroSource when KB_ZOTERO_DIR is set. Its extracts are under
    # raw/selected_library/.
    SourceKind(zotero.FOLDER_PREFIX, (), zotero.READER),
    # No instance: cli.py adds GhArchiveSource when GOOGLE_APPLICATION_CREDENTIALS is set. No
    # reader of items: its rankings are not items, cli.py reads them with read_trend_files.
    SourceKind(gh_archive.FOLDER_PREFIX, (), None),
)
