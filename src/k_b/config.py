"""The adjustable settings of K-B (ADR of 2026-10-10, "Configuration")."""

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
