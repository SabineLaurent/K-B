"""The adjustable settings of K-B (ADR of 2026-10-10, "Configuration")."""

from dataclasses import dataclass
from typing import Literal


# A GitHub repository K-B watches; the list is in etl/sources/tracked_repositories.py until #123
# moves it here. Defined here, not with the list: the import writes it to the base, and a
# generic module does not import the sources.
@dataclass(frozen=True)
class TrackedRepository:
    name: str
    ecosystem: Literal["pip", "npm"]
    # Only the main packages: integrations are added when they are used.
    packages: tuple[str, ...]


# How long the data of each acquisition mode is kept, in years after its collection; the purge
# (#83) reads it. None: K-B sets no duration, the library being kept by the user in Zotero and
# Obsidian (docs/registre-traitements.md, record 2). For now, to be reviewed (ADR of 2026-10-10).
# One entry per value of the CHECK on source.acquisition_mode in schema.sql: a test keeps both
# lists equal.
RETENTION_YEARS_BY_ACQUISITION_MODE: dict[str, int | None] = {
    "watch": 2,
    "library": None,
    "wiki": None,
}

# How many log files of past days kb keeps, of each log (logs/kb.log.<day> and
# logs/kb-serve.log.<day> of the data directory), the oldest removed at the rotation: about a
# month of daily collections (Sabine, 2026-10-14).
LOG_FILES_KEPT = 30

# The local defaults of kb serve, each changed by its variable (cli.py; .claude/rules/poc.md,
# rule 2): the data API listens on the machine only and answers these hosts only.
DATA_API_HOST = "127.0.0.1"
DATA_API_PORT = 8000
DATA_API_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
# The log of kb in a file of the data directory as well as on stderr; KB_LOG_TO_FILE=false for
# stderr only, as in a container, whose stderr is its log.
LOG_TO_FILE = True
