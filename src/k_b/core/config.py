"""The adjustable settings of K-B (ADR of 2026-10-10, "Configuration")."""

import re
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
# The key of a client of the data API (docs/specs-api.md, "Accès par clé"), checked by kb serve
# for each client and by the AI API for the key it sends. secrets.token_urlsafe(32) gives 43
# characters: 32 is the minimum checked. The alphabet of token_urlsafe, the way of making a key
# the README gives. HTTPBearer strips the spaces around the key received
# (fastapi/security/utils.py): a key that starts or ends with one would be accepted at the start
# and never match.
MIN_API_KEY_LENGTH = 32
API_KEY_CHARACTERS = re.compile(r"[A-Za-z0-9_-]+")
# The log of kb in a file of the data directory as well as on stderr; KB_LOG_TO_FILE=false for
# stderr only, as in a container, whose stderr is its log.
LOG_TO_FILE = True

# The call to the model by the AI API (ai_api/llm_client.py; docs/fiches-veille.md). Assumed
# values, to be measured on the real model (#158). Waiting for a connection, for a connection of
# the pool, for each write of the request, and for each read of the answer: a call that is not
# streamed sends nothing before its answer is whole, so the read timeout bounds the wait for an
# answer that comes in one block.
LLM_CONNECT_TIMEOUT_SECONDS = 5
LLM_POOL_TIMEOUT_SECONDS = 5
LLM_WRITE_TIMEOUT_SECONDS = 10
LLM_CALL_TIMEOUT_SECONDS = 60
# The wait before the retry after a 429, a 5xx or a failed connection without Retry-After; a
# Retry-After above the maximum is not waited: the call ends there. A call lasts 2 × (5 + 60) +
# 20 = 150 seconds when its answers come in one block; an answer sent in pieces can last longer,
# since each read has its own timeout: the bound of the whole is the one of the request (#205).
LLM_RETRY_WAIT_SECONDS = 2
LLM_RETRY_AFTER_MAX_SECONDS = 20
# Not set: temperature=0. "none" for a reasoning model, which takes no temperature (ADR of
# 2026-10-15, "Modèle des fiches : gpt-5.6-luna sur Foundry").
LLM_REASONING_EFFORT: Literal["none"] | None = None
# The base URL of the replay provider: a reserved domain (RFC 6761), never resolved, since the
# replay answers in the client itself.
LLM_REPLAY_BASE_URL = "https://replay.invalid/v1"

# The reading of the watch by the AI API through the data API (ai_api/data_api_client.py;
# docs/fiches-veille.md, "Lecture plafonnée"). The URL of kb serve with its defaults:
# KB_DATA_API_URL changes it, with KB_DATA_API_PORT.
DATA_API_URL = f"http://{DATA_API_HOST}:{DATA_API_PORT}"
# Assumed values for a service on the same machine or in the same compose network; the bound of
# the whole request is DIGEST_REQUEST_TIMEOUT_SECONDS (#205).
DATA_API_CONNECT_TIMEOUT_SECONDS = 5
DATA_API_POOL_TIMEOUT_SECONDS = 5
DATA_API_WRITE_TIMEOUT_SECONDS = 10
DATA_API_READ_TIMEOUT_SECONDS = 10
# The items read for one request, at most: the rare kinds first (OWASP API4:2023).
MAX_ITEMS_PER_DIGEST_REQUEST = 300
# The items sent to the writing of one digest, the most recent first, and the length of each of
# their fields once masked.
MAX_ITEMS_PER_DIGEST = 60
MAX_FIELD_CHARS_FOR_WRITING = 2000
