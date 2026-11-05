"""The adjustable settings of K-B (ADR of 2026-10-10, "Configuration")."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

# The settings of the watch, by source (#123), each name with the prefix of its source (decision of
# 2026-10-13). The facts of the APIs and formats, and the size caps, stay in the code.

# arXiv. Papers both in cs.CR and cs.AI whose abstract has one of these keywords (decided in #6).
ARXIV_KEYWORDS = [
    "prompt injection",
    "jailbreak",
    "red teaming",
    "adversarial attack",
    "backdoor",
    "poisoning",
    "membership inference",
    "agent security",
]
# A paper is searchable only once announced, up to 3.5 days after its submission (Thursday
# 14:00 to Sunday 20:00, New York time), later on holidays. The window reaches back this far
# before the last collection so that late announcements are not lost; the overlap with the
# previous raw file is removed when merging, by arXiv identifier.
ARXIV_ANNOUNCEMENT_DELAY_MARGIN = timedelta(days=7)
# The first collection reaches back to the start of Sabine's training: 488 papers, 1.2 MB,
# measured on 2026-10-02.
ARXIV_FIRST_COLLECTION_START = datetime(2026, 5, 1, tzinfo=UTC)

# TLDR. Adding an edition is adding its slug, as in https://tldr.tech/<slug>/<YYYY-MM-DD>.
TLDR_TRACKED_EDITIONS = ("ai", "infosec", "dev", "tech")
# One page at a time, with a pause before each, from one edition to the next too: tldr.tech
# publishes no rate limit (decided in #6).
TLDR_PAUSE_BETWEEN_PAGES_SECONDS = 2
# For testing the collection; to widen when K-B is put into service.
TLDR_FIRST_COLLECTION_DAYS = 7

# GitHub. The ecosystems whose advisories are collected, written once: the type of a tracked
# repository and the list are the same values (#123).
type Ecosystem = Literal["pip", "npm"]
GITHUB_ECOSYSTEMS: tuple[Ecosystem, ...] = get_args(Ecosystem.__value__)


# A GitHub repository K-B watches, and the packages it publishes; the reasons are in
# docs/sources.md. Here, not in a source: the import writes the list to the base, and the
# collection derives its sources from it.
@dataclass(frozen=True)
class TrackedRepository:
    """A GitHub repository that K-B watches, with its ecosystem and the packages it publishes."""

    name: str
    ecosystem: Ecosystem
    # Only the main packages: integrations are added when they are used.
    packages: tuple[str, ...]


GITHUB_TRACKED_REPOSITORIES = (
    TrackedRepository(
        "langchain-ai/langchain",
        "pip",
        ("langchain", "langchain-core", "langchain-text-splitters"),
    ),
    TrackedRepository(
        "langchain-ai/langgraph", "pip", ("langgraph", "langgraph-checkpoint")
    ),
    TrackedRepository(
        "run-llama/llama_index", "pip", ("llama-index", "llama-index-core")
    ),
    TrackedRepository("anthropics/claude-code", "npm", ("@anthropic-ai/claude-code",)),
)
# The size of both tops, the API maximum: one request, deep enough to see a repository enter the
# top.
GITHUB_RANKING_SIZE = 100
# The search needs a criterion: this one keeps the whole top 100 (the 100th had 116,161 stars on
# 2026-10-02).
GITHUB_MOST_STARRED_SEARCH_QUERY = "stars:>10000"
# The same for the forks: the whole top 100 (533 repositories, the 100th had 27,552 forks on
# 2026-10-19).
GITHUB_MOST_FORKED_SEARCH_QUERY = "forks:>10000"

# GH Archive. The 30 first by stars and the 30 first by forks, together (decision of 2026-10-08).
GH_ARCHIVE_TOP_SIZE = 30
# A window: 3 full UTC days, from D-3 to D-1, rolling (decision of 2026-10-11).
GH_ARCHIVE_WINDOW_DAYS = 3
# Two weeks of missed collections: a repository that rose earlier adds little to the watch
# (decision of 2026-10-11). Beyond, the most recent windows are kept.
GH_ARCHIVE_MAX_CATCH_UP_WINDOWS = 15

# The trend report (docs/tendances.md, "Période", "Rang et critères"); the thresholds are to be
# reviewed on the first real reports. The first report reads the last 4 windows.
TREND_FIRST_REPORT_WINDOWS = 4
# Durable: in the top of 2 windows without a day in common, read over the period and the 2
# windows before it.
TREND_DURABLE_MIN_WINDOWS = 2
TREND_DURABLE_LOOKBACK_WINDOWS = 2
# A first collection of GH Archive takes the windows a first trend report reads, its period and the
# lookback of durable: the report of the first run misses none.
GH_ARCHIVE_FIRST_COLLECTION_WINDOWS = (
    TREND_FIRST_REPORT_WINDOWS + TREND_DURABLE_LOOKBACK_WINDOWS
)
# Accelerating: 5 ranks gained at least over the last run of windows in the top.
TREND_ACCELERATION_MIN_RANKS = 5
# The repositories whose sheet is read on GitHub, those meeting a criterion first.
TREND_MAX_CANDIDATES = 60
# A repository created less than 7 days before the request: a caution of its sheet.
TREND_RECENT_REPOSITORY_DAYS = 7
# The reading of the sheets on GitHub by the AI API (docs/tendances.md, "GitHub"). Requests per
# report, retries included: 60 candidates and room for their retries; the README of #369 will
# share it.
GITHUB_MAX_REQUESTS_PER_REPORT = 70
# A 403 that is not a rate limit leaves its candidate out; the third of a report stops the reading,
# so that a rate limit misread is never insisted on (decision of Sabine of 2026-10-31, Q1 (b)).
GITHUB_MAX_FORBIDDEN_PER_REPORT = 3
# The Retry-After returned for a rate limit, at most: the hour of the primary rate limit.
MAX_GITHUB_RETRY_AFTER_SECONDS = 3600
# The body of GET /repos/{owner}/{repo}: 6,382 bytes for fastapi/fastapi (2026-10-31,
# tests/fixtures/github_repository_extract.json); about 60 times it.
MAX_GITHUB_REPOSITORY_BYTES = 400_000
# The topics of a repository read, at most, by defense: a longer list is refused.
MAX_GITHUB_TOPICS = 100

# HTTP. A source download waits this long for each network operation: the connection, or each
# read (docs/specs-collecte.md).
HTTP_TIMEOUT_SECONDS = 30
# The redirections a source download follows, each one checked before it is requested: the number
# urllib followed.
HTTP_MAX_REDIRECTS = 10


# How long the base keeps the data of each acquisition mode, in years after its collection; the
# purge reads it (purge/base.py). None: K-B sets no duration, the library being kept by the user in
# Zotero and Obsidian (docs/registre-traitements.md, record 2). The watch: 3 years, for its items
# and the trends (ADR of 2026-10-20, decision 5). A state catalog (Zotero, CISA KEV) is kept
# without limit whatever its mode: the base holds its current state (decision of Sabine of
# 2026-11-04).
# One entry per value of the CHECK on source.acquisition_mode in schema.sql: a test keeps both
# lists equal.
RETENTION_YEARS_BY_ACQUISITION_MODE: dict[str, int | None] = {
    "watch": 3,
    "library": None,
    "wiki": None,
}

# How long a raw file is kept, in months after its collection, tops and copies of the clips
# included: the base is the source of truth (decision of Sabine of 2026-11-04; purge/raw.py). Of a
# state catalog, the raw keeps only the last file imported, whatever its age (purge/catalogs.py,
# ADR of 2026-10-19); of a top ranking, the last one readable, within the duration
# (post/top_sheets.py). Once the base has backups, a raw file goes as soon as two sound ones hold
# it: not coded yet (docs/registre-traitements.md, step 3).
RAW_RETENTION_MONTHS = 6

# How long before the last collection a clip of the vault still counts as changed, and is copied
# again: the clock of a file system can be coarser than, or lag behind, the one of kb (a tick of
# Linux; a vault mounted from the host in a container, #200), an assumption not measured. A clip
# copied again unchanged is left out already_seen at the import (decision of 2026-10-17: a loss
# without a trace is worse than a few bytes of raw).
CLIP_CHANGE_MARGIN = timedelta(seconds=60)

# The folder of the data directory that holds the logs of the runs: what a program did, to watch it.
LOGS_DIR_NAME = "logs"
# The logs kb writes there (commands/run_log.py), the only ones the purge deletes
# (purge/run_records.py): kb.log for every command, kb-serve-data.log and kb-serve-ai.log apart.
LOG_FILE_NAME = "kb.log"
SERVE_DATA_LOG_FILE_NAME = "kb-serve-data.log"
SERVE_AI_LOG_FILE_NAME = "kb-serve-ai.log"
LOG_FILE_NAMES = (LOG_FILE_NAME, SERVE_DATA_LOG_FILE_NAME, SERVE_AI_LOG_FILE_NAME)
# The folder that holds the journals of the imports: what an import decided about the data, in JSON.
JOURNALS_DIR_NAME = "journals"
# How many months a log and a journal are kept after the day in their name; the purge deletes the
# others, at the end of kb import (purge/run_records.py). The bottom of what the CNIL recommends for
# a log, six months to a year, a recommendation not binding (deliberation 2021-122; decision of
# Sabine of 2026-11-04, which replaces the 30 days of 2026-10-19).
RECORD_RETENTION_MONTHS = 6

# The local defaults of kb serve-data, each changed by its variable (data_api/settings.py;
# .claude/rules/poc.md, rule 2): the data API listens on the machine only and answers these hosts
# only.
DATA_API_HOST = "127.0.0.1"
DATA_API_PORT = 8000
DATA_API_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
# The key of a client of the data API (docs/specs-api.md, "Accès par clé"), checked by kb serve-data
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
# The name of a model: a deployment name of Azure, a model of OpenAI or of Mistral. Checked by the
# AI API in KB_LLM_MODEL, then by kb digest in the response, before it enters a sheet (#209);
# quoted in a log as it is.
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")
# The largest token count read in an answer of the provider (prompt, completion, reasoning): an
# answer beyond it is not read (llm_unavailable), since the answer of a provider is an input not
# trusted (OWASP API10:2023). Far above a call of K-B (about 9,000 input tokens and 8,192 output
# tokens at most for a digest, #205; for the choice of a trend report, 116,323 characters of user
# message measured at the cap by tests/ai_api/test_trend_selection.py, about 39,000 tokens at 3
# characters per token, assumed) and the context of any current model, and far below 2**53, the
# largest integer a float holds exactly: the cost of a metric line stays a finite number (review
# of #156).
MAX_TOKENS_READ_PER_ANSWER = 10_000_000
# The prices of gpt-6-luna (ADR of 2026-10-17, "Modèle des fiches : gpt-6-luna sur l'abonnement
# de l'organisme de formation"), in USD per million tokens, for cost_estimated of each metric
# line: Data Zone Standard, France Central, short context, effective from 2026-09-01. Read on
# 2026-10-21 in the Azure Retail Prices API (https://prices.azure.com/api/retail/prices,
# armRegionName francecentral, meters "6-luna ShortCo Inp Std DZ 1M Tokens" and "6-luna ShortCo
# Opt Std DZ 1M Tokens"), described by the page "Azure Retail Prices overview" of Microsoft Learn
# (https://learn.microsoft.com/ar-sa/rest/api/cost-management/retail-prices/azure-retail-prices,
# the address a web search of the same day gave).
# Every call is counted at these prices, the replay and another KB_LLM_MODEL included.
LLM_INPUT_USD_PER_MILLION_TOKENS = 0.12
LLM_OUTPUT_USD_PER_MILLION_TOKENS = 0.60

# The local defaults of kb serve-ai, each changed by its variable (ai_api/settings.py;
# .claude/rules/poc.md, rule 2): the AI API listens on the machine only, beside kb serve-data.
AI_API_HOST = "127.0.0.1"
AI_API_PORT = 8001
# The window of a digest request, in days (docs/fiches-veille.md, "Fenêtre"): the default, changed
# by KB_DIGEST_WINDOW_DAYS, and the bounds of both the variable and window_days of a request.
DIGEST_WINDOW_DAYS = 3
MIN_DIGEST_WINDOW_DAYS = 1
MAX_DIGEST_WINDOW_DAYS = 14

# The reading of the watch by the AI API through the data API (ai_api/connectors/data_api_client.py;
# docs/fiches-veille.md, "Lecture plafonnée"). The URL of kb serve-data with its defaults, changed by
# KB_DATA_API_URL; it does not follow KB_DATA_API_PORT: set KB_DATA_API_URL too when the port of
# kb serve-data changes.
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
# of the reading, each of 45 items and 36,000 characters of user message at most, about 9,000
# input tokens (#158: 46 items took about 5,500). 300 items make 7 batches, up to about 10 when
# the titles are long. The long text of an item is cut to 500 characters: sorting needs less text
# than writing. The schema of a batch has one property per item, within the bounds of strict mode
# that tests/ai_api/test_stages.py keeps: 45 items and 9 subjects give 450 values of enum, as 50
# items and 8 subjects did before 2026-11-01; 50 items would reach 500, the bound itself.
MAX_ITEMS_PER_CLASSIFICATION_CALL = 45
MAX_CLASSIFICATION_INPUT_CHARS = 36_000
MAX_FIELD_CHARS_FOR_CLASSIFICATION = 500
# The description of a candidate of a trend report sent to the choice of the model, once cleaned
# (ai_api/repository_texts.py): cut as the long text of the classification. 20 topics at most.
MAX_DESCRIPTION_CHARS_FOR_SELECTION = 500
MAX_TOPICS_FOR_SELECTION = 20
# The repositories the model may choose for a trend report (docs/tendances.md, "Choix").
TREND_MAX_CHOSEN = 5


# A subject of the digests: its name, a value of enum and a folder name, and its definition, sent
# to the model with it.
@dataclass(frozen=True)
class DigestSubject:
    """A subject of the digests: its name and the definition sent to the model."""

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
    DigestSubject(
        "tech_industry",
        "entreprises, produits, plateformes et matériel de la tech, hors IA",
    ),
)
# The answer of the classification for an item that no subject suits, then not retained: a
# reserved name, no subject of DIGEST_SUBJECTS may take it (a test keeps it).
NO_SUITABLE_SUBJECT_ANSWER = "no_suitable_subject"

# The folder of the vault that kb writes (ADR of 2026-10-19, "Coffre : organisation"): the digests
# of each subject in veille/<subject>/ (#209), the sheets of the top rankings in veille/tops/, the
# trend reports in veille/tendances/ (#366).
WATCH_DIR_NAME = "veille"
# Reserved names under veille/: no subject of DIGEST_SUBJECTS may take one, or its digests would be
# written in the folder of the sheets of the tops or of the trend reports (a test keeps it).
TOPS_DIR_NAME = "tops"
TRENDS_DIR_NAME = "tendances"

# The bound of a digest request, from its arrival: the reading by the data API and every call to
# the model, which go one after the other. Under the 240 seconds the HTTP ingress of Azure
# Container Apps gives a request, with 40 for the last call under way and the answer. Measured by
# #158 on gpt-6-luna: about 98 seconds for 8 subjects, the judge included (113 with the slowest
# calls). Beyond it, a subject not yet written is llm_timeout, the others are returned.
DIGEST_REQUEST_TIMEOUT_SECONDS = 200
# The bound of a trend report request: 1 + 31 GET /trends at most on a service of the same network,
# then GITHUB_MAX_REQUESTS_PER_REPORT GET /repos at most on GitHub, one after the other, then the
# call of the choice to the model; each timeout is shortened by it. As
# DIGEST_REQUEST_TIMEOUT_SECONDS and for the same reason: under the 240 seconds of kb and of the
# ingress of Azure Container Apps, with a margin for the last call under way. GitHub may leave too
# little time to the model: the choice then fails in llm_timeout, the report factual
# (docs/tendances.md). Its hold is measured by #370.
TREND_REPORT_REQUEST_TIMEOUT_SECONDS = 200
# The requests of kb digest and kb trend-report to the AI API (post/ai_api_client.py, #209, #366).
# The URL of kb serve-ai with its defaults, changed by KB_AI_API_URL; it does not follow
# KB_AI_API_PORT: set KB_AI_API_URL too when the port of kb serve-ai changes. Connection, pool and
# write: assumed values for a service on the same machine or in the same compose network, as for
# the data API. Read: the AI API answers in one block once its request is done, within
# DIGEST_REQUEST_TIMEOUT_SECONDS and the last call to the model under way (about 20 seconds more,
# ai_api/deadline.py); 240 is also the bound the HTTP ingress of Azure Container Apps gives a
# request, and holds TREND_REPORT_REQUEST_TIMEOUT_SECONDS, of the same length. No retry: a
# Retry-After is shown, never waited.
AI_API_URL = f"http://{AI_API_HOST}:{AI_API_PORT}"
AI_API_CONNECT_TIMEOUT_SECONDS = 5
AI_API_POOL_TIMEOUT_SECONDS = 5
AI_API_WRITE_TIMEOUT_SECONDS = 10
AI_API_READ_TIMEOUT_SECONDS = 240
# The wait for an answer shown out of a terminal (commands/wait_display.py): a log line every 10
# seconds, the step of the "Still creating... [10s elapsed]" of Terraform and the limit of attention
# of NN/g (docs/fiches-veille.md, "Console"). A constant, not a variable: no need to change it by
# deployment.
WAIT_LOG_INTERVAL_SECONDS = 10
# The time a request to the model needs at least: none is sent with less left, so that the items
# are not sent for an answer the deadline would throw away. Above the slowest writing measured by
# #158 (9.3 s), not above the longest one the output cap allows (about 60 s): a longer writing
# started with less time left can still end in llm_timeout.
MIN_SECONDS_FOR_LLM_REQUEST = 10

# The export of the metrics of the AI API in OpenTelemetry (ai_api/connectors/metrics_export.py,
# #162). Every 60 s, the default of the OpenTelemetry SDK; a request to the OTLP endpoint waits 5 s
# at most, and the last export on stop as long. The last export runs once uvicorn has ended the
# requests under way, which may take up to DIGEST_REQUEST_TIMEOUT_SECONDS: within the 10 s docker
# stop gives before SIGKILL only if no digest request is under way (.claude/rules/poc.md, rule 6);
# the stop delay of the container is #200's. Constants, not variables: no need to change them by
# deployment.
MILLISECONDS_PER_SECOND = 1000
METRICS_EXPORT_INTERVAL_SECONDS = 60
METRICS_EXPORT_TIMEOUT_SECONDS = 5
METRICS_STOP_TIMEOUT_SECONDS = 5

# The traces of the AI API and their log records (ai_api/connectors/trace_export.py), sent to the
# endpoint of the metrics. A request waits 3 s at most: a stop may send twice (the export under way,
# then the rest), so the traces and the logs stop within 2 × 3 s, beside the 5 s of the metrics, all
# three at once (ai_api/app.py), under the 10 s docker stop gives.
TRACE_EXPORT_TIMEOUT_SECONDS = 3
# Grafana Cloud Traces cuts each attribute at 2 KB: K-B cuts before, in bytes of UTF-8, as the SDK
# counts characters.
MAX_TRACE_ATTRIBUTE_BYTES = 2048
# The spans, or the log records, waiting to be sent: one batch at most, so that a stop sends one
# batch after the one under way (the default, 2,048 in batches of 512, could send four). A request
# makes a few dozen spans; beyond 512 waiting, the SDK drops the oldest one and logs it.
TRACE_QUEUE_SIZE = 512
# The longest a stop of the traces, or of the log records, waits: the two sendings above. The SDK
# bounds no total, as the timeout of an export bounds each wait of the socket only: the stop runs
# in a thread of its own, left behind when the time is up.
TRACE_STOP_TIMEOUT_SECONDS = 2 * TRACE_EXPORT_TIMEOUT_SECONDS
# The content of a request to the model (prompt, items sent, output), a log record of its own sent
# with the traces when KB_TRACE_CONTENT lets it (.claude/rules/poc.md, rule 5, exception): none, the
# default; the calls in anomaly only (decision D1 of Sabine, 2026-10-27); all, in the sandbox only.
type TraceContent = Literal["none", "anomalies", "all"]
TRACE_CONTENTS: tuple[TraceContent, ...] = get_args(TraceContent.__value__)
# The longest body of such a record, in bytes of UTF-8: Loki refuses a line beyond 256 KB, the
# margin is left to its own counting. Beyond, each text is cut, the structure kept.
MAX_CONTENT_EVENT_BYTES = 200_000
