"""SOURCE_KINDS: the only declaration of the sources, one kind per entry, in collection order.

In the package, only commands/collect_command.py and commands/import_command.py import it: they
give it to the collection (E) and to the import (T then L). The Zotero, clipping and GH Archive
kinds have no instance here: etl/collected_sources.py creates them, on a machine that says where
the Zotero data directory, the Obsidian vault, or the BigQuery key, is.
"""

from k_b.etl.source_contract import SourceKind
from k_b.etl.sources import (
    arxiv,
    cisa_kev,
    clipping,
    gh_archive,
    github_advisories,
    github_most_forked,
    github_most_starred,
    github_releases,
    tldr,
    zotero,
)
from k_b.etl.sources.arxiv import ArxivSource
from k_b.etl.sources.cisa_kev import CisaKevSource
from k_b.etl.sources.github_advisories import GithubAdvisoriesSource
from k_b.etl.sources.github_most_forked import GithubMostForkedSource
from k_b.etl.sources.github_most_starred import GithubMostStarredSource
from k_b.etl.sources.github_releases import GithubReleasesSource
from k_b.etl.sources.tldr import TRACKED_EDITIONS, TldrSource
from k_b.etl.sources.tracked_repositories import (
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
        # No reader: the ranking does not enter the base (decision "Tops", 2026-10-07).
        None,
    ),
    SourceKind(
        github_most_forked.FOLDER_PREFIX,
        (GithubMostForkedSource(),),
        # No reader: the ranking does not enter the base (decision "Tops", 2026-10-07).
        None,
    ),
    SourceKind(arxiv.FOLDER_PREFIX, (ArxivSource(),), arxiv.READER),
    SourceKind(
        tldr.FOLDER_PREFIX,
        tuple(TldrSource(edition) for edition in TRACKED_EDITIONS),
        tldr.READER,
    ),
    # No instance: etl/collected_sources.py adds ZoteroSource when KB_ZOTERO_DIR is set, unless
    # KB_COLLECT_ONLY leaves it out. Its extracts are under raw/selected_library/.
    SourceKind(zotero.FOLDER_PREFIX, (), zotero.READER),
    # No instance: etl/collected_sources.py adds ClippingSource when KB_VAULT_DIR is set, unless
    # KB_COLLECT_ONLY leaves it out. Its copies are under raw/selected_library/.
    SourceKind(clipping.FOLDER_PREFIX, (), clipping.READER),
    # No instance: etl/collected_sources.py adds GhArchiveSource when
    # GOOGLE_APPLICATION_CREDENTIALS is set, unless KB_COLLECT_ONLY leaves it out. No reader of
    # items: its rankings are not items, commands/import_command.py reads them with
    # read_trend_files.
    SourceKind(gh_archive.FOLDER_PREFIX, (), None),
)
