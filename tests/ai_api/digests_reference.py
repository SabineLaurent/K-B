"""The reference set of POST /digests: its recording, run once by the user who has the model, and
what its replay shares with it.

    uv run --env-file .env python tests/ai_api/digests_reference.py

Only the settings of the model are read of the environment, and the items are imported from two
CC0 extracts into a temporary folder: no text is copied, no set is written over."""

import json
import os
import secrets
import shutil
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import httpx2
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from pydantic import AwareDatetime, BaseModel, ConfigDict, SecretStr

from k_b.ai_api.app import create_app
from k_b.ai_api.connectors.data_api_client import read_watch
from k_b.ai_api.connectors.data_api_settings import DataApiSettings
from k_b.ai_api.connectors.github_settings import GithubSettings
from k_b.ai_api.connectors.llm_client import PROVIDER_FAILURES, build_http_client
from k_b.ai_api.connectors.llm_replay import ResponseStep
from k_b.ai_api.connectors.llm_settings import (
    PROVIDER_VARIABLE,
    REPLAY_MODEL,
    LlmSettings,
    read_llm_settings_or_refusal,
)
from k_b.ai_api.connectors.trace_export import TraceExport
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.dependencies import (
    open_data_api_client,
    open_llm_client,
    read_request_time,
)
from k_b.ai_api.observability.metric_instruments import ModelMetrics
from k_b.ai_api.stage_calls import DigestStage
from k_b.ai_api.stages.classification import CLASSIFICATION_PROMPT_VERSION
from k_b.ai_api.stages.writing import WRITING_PROMPT_VERSION
from k_b.core.config import (
    DIGEST_CLIENT,
    DIGEST_SUBJECTS,
    DIGEST_WINDOW_DAYS,
    GITHUB_TRACKED_REPOSITORIES,
    LLM_REPLAY_BASE_URL,
    MAX_DIGEST_WINDOW_DAYS,
    MODEL_NAME,
    DigestSubject,
)
from k_b.data_api.app import create_app as create_data_app
from k_b.database.creation import create_database
from k_b.etl.pipeline import import_raw_files
from k_b.etl.raw_store import AUTOMATED_WATCH_DIR_NAME, RAW_DIR_NAME
from k_b.etl.source_kinds import SOURCE_KINDS

REPOSITORY_DIR = Path(__file__).parents[2]
REFERENCE_PATH = REPOSITORY_DIR / "tests" / "fixtures" / "digests_reference.json"
README_PATH = REPOSITORY_DIR / "README.md"
# The request of the set: its window covers the three papers of the arXiv extract and the three
# vulnerabilities of 2026 of the KEV extract; the advisories, of June, are older.
REQUEST_TIME = datetime(2026, 10, 8, 12, 0, 30, tzinfo=UTC)
WINDOW_DAYS = MAX_DIGEST_WINDOW_DAYS
COLLECTION = "2026-10-05T093000Z"
IMPORTED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)
# The client of the data API the AI API is, as in the tests of the route.
DATA_API_CLIENT = "AI_DIGEST"
READING_SECONDS = 10
STAGE_BY_SCHEMA_NAME: dict[str, DigestStage] = {
    "classification": "classify",
    "digest": "write",
}
PROMPT_VERSION_BY_STAGE: dict[DigestStage, str] = {
    "classify": CLASSIFICATION_PROMPT_VERSION,
    "write": WRITING_PROMPT_VERSION,
}
# A subject the model could not answer for: a recording with one of them is not kept.
UNAVAILABLE_STATES = PROVIDER_FAILURES | {"llm_timeout"}


class Extract(NamedTuple):
    """An extract of the collection the items of the set come from, and its license."""

    fixture: str
    folder: str
    extension: str
    license: str


EXTRACT_BY_KIND = {
    "paper": Extract(
        "tests/fixtures/arxiv_extract.xml", "arxiv_cscr_x_csai", "xml", "CC0 1.0"
    ),
    "vulnerability": Extract(
        "tests/fixtures/cisa_kev_extract.csv", "cisa_kev", "csv", "CC0 1.0"
    ),
}


class ReferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReferenceSubject(ReferenceModel):
    name: str
    definition: str


class ReferenceItem(ReferenceModel):
    """An item the AI API read for the request, as the data API serves it, with its extract."""

    # The id the model is sent and answers with (i<item_id>).
    item_id: int
    kind: str
    title: str
    url: str | None
    source_file: str
    license: str


class RecordedCall(ReferenceModel):
    """A request to the model, in the order the replay sends it, and its answer as it came."""

    stage: DigestStage
    prompt_version: str
    model: str
    # The model the provider says answered, if it names one.
    response_model: str | None
    reasoning_effort: str | None
    called_at: AwareDatetime
    step: ResponseStep


class DigestsReference(ReferenceModel):
    request_time: AwareDatetime
    window_days: int
    subjects: list[ReferenceSubject]
    items: list[ReferenceItem]
    calls: list[RecordedCall]


def read_reference(path: Path) -> DigestsReference:
    return DigestsReference.model_validate_json(path.read_bytes())


def build_reference_base(data_dir: Path) -> Path:
    """The SQLite base of data_dir, imported from the extracts by the code of kb import."""
    for extract in EXTRACT_BY_KIND.values():
        folder = data_dir / RAW_DIR_NAME / AUTOMATED_WATCH_DIR_NAME / extract.folder
        folder.mkdir(parents=True)
        shutil.copyfile(
            REPOSITORY_DIR / extract.fixture,
            folder / f"{COLLECTION}.{extract.extension}",
        )
    database_path = data_dir / "k-b.sqlite"
    create_database(database_path)
    import_raw_files(
        data_dir,
        database_path,
        SOURCE_KINDS,
        GITHUB_TRACKED_REPOSITORIES,
        IMPORTED_AT,
    )
    return database_path


@contextmanager
def open_data_api(database_path: Path) -> Iterator[TestClient]:
    """The data API of the base, in the process, with the key of the AI API."""
    key = secrets.token_urlsafe(32)
    with TestClient(
        create_data_app(database_path, {DATA_API_CLIENT: SecretStr(key)}),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {key}"},
    ) as client:
        yield client


def read_reference_items(
    data_api: TestClient, request_time: datetime, window_days: int
) -> list[ReferenceItem]:
    """The items POST /digests reads for this window, by the reading of the AI API."""
    reading = read_watch(
        data_api,
        request_time - timedelta(days=window_days),
        deadline=Deadline.after(READING_SECONDS),
    )
    return [
        ReferenceItem(
            item_id=item.item_id,
            kind=item.kind,
            title=item.source_title,
            url=item.url,
            source_file=EXTRACT_BY_KIND[item.kind].fixture,
            license=EXTRACT_BY_KIND[item.kind].license,
        )
        for item in reading.items
    ]


def build_ai_api(
    llm_settings: LlmSettings,
    subjects: Sequence[ReferenceSubject],
    request_time: datetime,
    data_api: TestClient,
    transport: httpx2.BaseTransport,
) -> TestClient:
    """The AI API of these subjects at this time, on the data API given, its model reached by
    the transport given; its spans and measures stay in memory."""
    key = secrets.token_urlsafe(32)
    app = create_app(
        {DIGEST_CLIENT: SecretStr(key)},
        llm_settings,
        # Never called: the data API given replaces its client.
        DataApiSettings(
            base_url="http://localhost", api_key=SecretStr(secrets.token_urlsafe(32))
        ),
        GithubSettings(token=SecretStr(f"github_pat_{secrets.token_hex(41)}")),
        [DigestSubject(subject.name, subject.definition) for subject in subjects],
        DIGEST_WINDOW_DAYS,
        ModelMetrics(MeterProvider(shutdown_on_exit=False)),
        TraceExport(
            TracerProvider(shutdown_on_exit=False),
            LoggerProvider(shutdown_on_exit=False),
        ),
    )

    def open_model_client() -> Iterator[httpx2.Client]:
        with build_http_client(llm_settings, transport=transport) as http_client:
            yield http_client

    app.dependency_overrides[open_llm_client] = open_model_client
    app.dependency_overrides[open_data_api_client] = lambda: data_api
    app.dependency_overrides[read_request_time] = lambda: request_time
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {key}"},
        raise_server_exceptions=False,
    )


def post_digests(ai_api: TestClient, window_days: int) -> httpx2.Response:
    return ai_api.post("/digests", json={"window_days": window_days})


def replay_settings(steps: Sequence[ResponseStep]) -> LlmSettings:
    return LlmSettings(
        provider="replay",
        base_url=LLM_REPLAY_BASE_URL,
        model=REPLAY_MODEL,
        api_key=None,
        reasoning_effort=None,
        replay_steps=tuple(steps),
    )


def read_stage(request: httpx2.Request) -> DigestStage:
    """The stage of a request to the model, by the name of the schema it asks for."""
    schema_name = json.loads(request.content)["response_format"]["json_schema"]["name"]
    return STAGE_BY_SCHEMA_NAME[schema_name]


def read_subject(request: httpx2.Request) -> str | None:
    """The subject of a writing, by its user message; None for a classification."""
    if read_stage(request) != "write":
        return None
    body = json.loads(request.content)
    user_message = next(m for m in body["messages"] if m["role"] == "user")
    subject: str = json.loads(user_message["content"])["subject"]["name"]
    return subject


def order_as_replayed[CallT](
    recorded: Sequence[tuple[str | None, CallT]], subject_names: Sequence[str]
) -> list[CallT]:
    """The calls in the order the replay sends them: the classification, then the writings in
    the order of the list. A provider writes the subjects at once (#630), so they end in any
    order; the attempts of a subject, made one after the other in its thread, keep theirs."""
    position = {name: index for index, name in enumerate(subject_names)}
    in_order = sorted(
        recorded, key=lambda pair: -1 if pair[0] is None else position[pair[0]]
    )
    return [call for _, call in in_order]


def read_response_model(body: bytes) -> str | None:
    """The model a completion names, if it is one; None for any other body."""
    try:
        model = json.loads(body).get("model")
    except (ValueError, AttributeError):
        return None
    return model if isinstance(model, str) and MODEL_NAME.fullmatch(model) else None


class RecordingTransport(httpx2.BaseTransport):
    """The transport of the provider, keeping each answer as a step of the replay, with the call
    it answers; an answer is given back read, without its encoding, so that the client decodes
    it once."""

    def __init__(self, settings: LlmSettings, subject_names: Sequence[str]) -> None:
        # trust_env=False, as open_http_client: no certificate of the environment is read.
        self.provider = httpx2.HTTPTransport(trust_env=False)
        self.settings = settings
        self.subject_names = subject_names
        # Each call with its subject, in the order the answers came: one thread per subject
        # appends to it, a list.append being atomic.
        self.recorded: list[tuple[str | None, RecordedCall]] = []
        self.transport_errors = 0

    @property
    def calls(self) -> list[RecordedCall]:
        return order_as_replayed(self.recorded, self.subject_names)

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            response = self.provider.handle_request(request)
            try:
                body = response.read()
            finally:
                response.close()
        except BaseException:
            self.transport_errors += 1
            raise
        stage = read_stage(request)
        retry_after = response.headers.get("Retry-After")
        call = RecordedCall(
            stage=stage,
            prompt_version=PROMPT_VERSION_BY_STAGE[stage],
            model=self.settings.model,
            response_model=read_response_model(body),
            reasoning_effort=self.settings.reasoning_effort,
            called_at=datetime.now(UTC).replace(microsecond=0),
            step=ResponseStep(
                kind="response",
                status=response.status_code,
                body=body.decode(),
                retry_after=retry_after,
            ),
        )
        self.recorded.append((read_subject(request), call))
        headers = {"Content-Type": response.headers.get("Content-Type", "")}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        return httpx2.Response(response.status_code, headers=headers, content=body)

    def close(self) -> None:
        self.provider.close()


def find_recording_refusal(
    response: httpx2.Response, transport: RecordingTransport
) -> str | None:
    """Why a recording is not kept: an answer the replay would not give the same way."""
    if transport.transport_errors:
        return f"transport errors: {transport.transport_errors}"
    for position, call in enumerate(transport.calls, start=1):
        if call.step.status != 200:
            return f"answer {position} of {len(transport.calls)}: status {call.step.status}"
    if response.status_code != 200:
        return f"POST /digests: status {response.status_code}"
    for failed in response.json()["failed_subjects"]:
        if failed["error"] in UNAVAILABLE_STATES:
            return f"subject {failed['subject']}: {failed['error']}"
    return None


def record(environ: Mapping[str, str]) -> int:
    """Record the set from one POST /digests on the model of the environment; 0 once written."""
    if REFERENCE_PATH.exists():
        print(
            f"{REFERENCE_PATH.name}: already recorded, no call sent; remove it to record again",
            file=sys.stderr,
        )
        return 1
    settings = read_llm_settings_or_refusal(environ)
    if isinstance(settings, str):
        print(settings, file=sys.stderr)
        return 1
    if settings.provider == "replay":
        print(f"{PROVIDER_VARIABLE}: replay, not a model", file=sys.stderr)
        return 1
    subjects = [
        ReferenceSubject(name=subject.name, definition=subject.definition)
        for subject in DIGEST_SUBJECTS
    ]
    transport = RecordingTransport(settings, [subject.name for subject in subjects])
    with (
        tempfile.TemporaryDirectory() as data_dir,
        open_data_api(build_reference_base(Path(data_dir))) as data_api,
    ):
        items = read_reference_items(data_api, REQUEST_TIME, WINDOW_DAYS)
        ai_api = build_ai_api(settings, subjects, REQUEST_TIME, data_api, transport)
        response = post_digests(ai_api, WINDOW_DAYS)
    refusal = find_recording_refusal(response, transport)
    if refusal is not None:
        print(f"not recorded: {refusal}", file=sys.stderr)
        return 1
    reference = DigestsReference(
        request_time=REQUEST_TIME,
        window_days=WINDOW_DAYS,
        subjects=subjects,
        items=items,
        calls=transport.calls,
    )
    with REFERENCE_PATH.open("x", encoding="utf-8") as reference_file:
        reference_file.write(reference.model_dump_json(indent=2) + "\n")
    print(f"{REFERENCE_PATH.name}: {len(items)} items, {len(transport.calls)} calls")
    return 0


if __name__ == "__main__":
    sys.exit(record(os.environ))
