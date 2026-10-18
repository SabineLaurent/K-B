"""The adjustable settings of K-B (ADR of 2026-10-10, "Configuration")."""

import re
from dataclasses import dataclass
from datetime import timedelta
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

# How long before the last collection a clip of the vault still counts as changed, and is copied
# again: the clock of a file system can be coarser than, or lag behind, the one of kb (a tick of
# Linux; a vault mounted from the host in a container, #200), an assumption not measured. A clip
# copied again is left out already_seen at the import (decision of 2026-10-17: a loss without a
# trace is worse than a few bytes of raw).
CLIP_CHANGE_MARGIN = timedelta(seconds=60)

# How many log files of past days kb keeps, of each log (logs/kb.log.<day> and
# logs/kb-serve.log.<day> of the data directory), the oldest removed at the rotation: about a
# month of daily collections (Sabine, 2026-10-14).
LOG_FILES_KEPT = 30

# The local defaults of kb serve, each changed by its variable (data_api/settings.py;
# .claude/rules/poc.md, rule 2): the data API listens on the machine only and answers these hosts
# only.
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

# The call to the model by the AI API (ai_api/connectors/llm_client.py; docs/fiches-veille.md). Waiting for
# a connection, for a connection of the pool, for each write of the request, and for each read of
# the answer: a call that is not streamed sends nothing before its answer is whole, so the read
# timeout bounds the wait for an answer that comes in one block. Measured by #158 on gpt-6-luna
# (2026-10-17): about 7.35 ms per output token, so 8,192 tokens take about 60 seconds; 90 leaves
# a margin. Connection, pool and write: no failure over 20 real calls, bodies of 27,000
# characters.
LLM_CONNECT_TIMEOUT_SECONDS = 5
LLM_POOL_TIMEOUT_SECONDS = 5
LLM_WRITE_TIMEOUT_SECONDS = 10
LLM_CALL_TIMEOUT_SECONDS = 90
# The wait before the retry after a 429, a 5xx or a failed connection without Retry-After; a
# Retry-After above the maximum is not waited: the call ends there. A call lasts 2 × (5 + 90) +
# 20 = 210 seconds when its answers come in one block; an answer sent in pieces can last longer,
# since each read has its own timeout: the bound of the whole is the one of the request (#205).
LLM_RETRY_WAIT_SECONDS = 2
LLM_RETRY_AFTER_MAX_SECONDS = 20
# Not set: temperature=0. "none" for a reasoning model, which takes no temperature alone
# (gpt-6-luna refuses temperature 0 without it: 400 unsupported_value, #158).
LLM_REASONING_EFFORT: Literal["none"] | None = None
# The base URL of the replay provider: a reserved domain (RFC 6761), never resolved, since the
# replay answers in the client itself.
LLM_REPLAY_BASE_URL = "https://replay.invalid/v1"

# The reading of the watch by the AI API through the data API (ai_api/connectors/data_api_client.py;
# docs/fiches-veille.md, "Lecture plafonnée"). The URL of kb serve with its defaults, changed by
# KB_DATA_API_URL; it does not follow KB_DATA_API_PORT: set KB_DATA_API_URL too when the port of
# kb serve changes.
DATA_API_URL = f"http://{DATA_API_HOST}:{DATA_API_PORT}"
# Assumed values for a service on the same machine or in the same compose network. They bound
# each wait (a connection, each piece of an answer read), neither a request nor the reading: the
# bound of a digest request is DIGEST_REQUEST_TIMEOUT_SECONDS, which shortens them as it nears.
DATA_API_CONNECT_TIMEOUT_SECONDS = 5
DATA_API_POOL_TIMEOUT_SECONDS = 5
DATA_API_WRITE_TIMEOUT_SECONDS = 10
DATA_API_READ_TIMEOUT_SECONDS = 10
# The largest body of an answer of the data API, read or announced by Content-Length; beyond, the
# reading stops with data_api_invalid_response (Sabine, 2026-10-15: a bound now, to be corrected
# later if needed). Above the worst honest answer, estimated in the review of #204 at about 2 MB
# for a page of the list and 0.75 MB for a detail. A defense in depth (OWASP API4:2023, API10:2023); the duration stays bounded by
# DIGEST_REQUEST_TIMEOUT_SECONDS (#205).
MAX_DATA_API_BODY_BYTES = 4_000_000
# The items read for one request, at most: the rare kinds first (OWASP API4:2023).
MAX_ITEMS_PER_DIGEST_REQUEST = 300
# The items sent to the writing of one digest, the most recent first, and the length of each of
# their fields once masked.
MAX_ITEMS_PER_DIGEST = 60
MAX_FIELD_CHARS_FOR_WRITING = 2000

# The classification of the items of a request (ai_api/stages/classification.py): batches in the order
# of the reading, each of 50 items and 36,000 characters of user message at most, about 9,000
# input tokens (#158: 46 items took about 5,500). 300 items make 6 batches, up to about 10 when
# the titles are long. The long text of an item is cut to 500 characters: sorting needs less text
# than writing.
MAX_ITEMS_PER_CLASSIFICATION_CALL = 50
MAX_CLASSIFICATION_INPUT_CHARS = 36_000
MAX_FIELD_CHARS_FOR_CLASSIFICATION = 500


# A subject of the digests: its name, a value of enum and a folder name, and its definition, sent
# to the model with it.
@dataclass(frozen=True)
class DigestSubject:
    name: str
    definition: str


# The closed list of subjects, kept by Sabine (docs/fiches-veille.md, "Sujets"); an item that
# fits several goes to the first of them, in this order. Changed by a PR; the tests use their own.
DIGEST_SUBJECTS = (
    DigestSubject(
        "vulnerabilities",
        "une faille identifiée (CVE, GHSA) : catalogue CISA KEV, alertes GitHub des paquets"
        " suivis, article qui la décrit",
    ),
    DigestSubject(
        "llm_security",
        "attaques et défenses propres aux modèles et aux agents (injection d'instructions,"
        " jailbreak, empoisonnement, porte dérobée), sans CVE ni GHSA",
    ),
    DigestSubject(
        "agent_frameworks",
        "versions et nouvelles de LangChain, LangGraph, LlamaIndex et des cadres d'agents",
    ),
    DigestSubject(
        "coding_assistants",
        "assistants de code (Claude Code et autres) : versions, fonctions, usages",
    ),
    DigestSubject(
        "models",
        "nouveaux modèles, évaluations, capacités et limites annoncées",
    ),
    DigestSubject(
        "ai_industry",
        "entreprises, produits, financements et régulation de l'IA",
    ),
    DigestSubject(
        "cybersecurity",
        "incidents, campagnes d'attaque, outils et pratiques de sécurité hors IA, sans CVE ni"
        " GHSA",
    ),
    DigestSubject(
        "software_engineering",
        "outils, langages et pratiques de développement hors IA",
    ),
)

# The bound of a digest request, from its arrival: the reading by the data API and every call to
# the model, which go one after the other. Under the 240 seconds the HTTP ingress of Azure
# Container Apps gives a request, with 40 for the last call under way and the answer. Measured by
# #158 on gpt-6-luna: about 98 seconds for 8 subjects, the judge included (113 with the slowest
# calls). Beyond it, a subject not yet written is llm_timeout, the others are returned.
DIGEST_REQUEST_TIMEOUT_SECONDS = 200
# The time a request to the model needs at least: none is sent with less left, so that the items
# are not sent for an answer the deadline would throw away. Above the slowest writing measured by
# #158 (9.3 s), not above the longest one the output cap allows (about 60 s): a longer writing
# started with less time left can still end in llm_timeout.
MIN_SECONDS_FOR_LLM_REQUEST = 10
