"""The request and the response of POST /digests (docs/fiches-veille.md)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from k_b.ai_api.connectors.llm_client import LlmFailure
from k_b.ai_api.stage_calls import DigestStage
from k_b.core.config import MAX_DIGEST_WINDOW_DAYS, MIN_DIGEST_WINDOW_DAYS
from k_b.items import UtcDatetime, WatchKind, parse_aware_datetime

WindowDays = Annotated[int, Field(ge=MIN_DIGEST_WINDOW_DAYS, le=MAX_DIGEST_WINDOW_DAYS)]


def read_start_text(start: object) -> datetime:
    """A start read as an ISO 8601 date with its zone: left to pydantic, a number would be a Unix
    time, and strict refuses the text FastAPI hands on."""
    return parse_aware_datetime(start, "start")


# Still a date-time to pydantic: the OpenAPI declares it so.
SubjectStart = Annotated[UtcDatetime, BeforeValidator(read_start_text)]


class DigestRequestSchema(BaseModel):
    # Any other field refused; strict: true, 3.0 and "3" are not integers.
    model_config = ConfigDict(extra="forbid", strict=True)

    window_days: WindowDays | None = Field(
        default=None,
        description="The window of a subject without a start; absent or null: the window of"
        " KB_DIGEST_WINDOW_DAYS.",
    )
    since_by_subject: dict[str, SubjectStart] | None = Field(
        default=None,
        description="The start of a subject, the until of its previous digest; a subject"
        " absent starts window_days before the request, a start more than"
        f" {MAX_DIGEST_WINDOW_DAYS} days before is brought to that bound.",
    )


class WindowSchema(BaseModel):
    days: int = Field(description="The window of a subject without a start, in days.")
    since: datetime = Field(
        description="The start of the reading: the oldest start of a subject."
    )
    until: datetime
    capped_kind: WatchKind | None = Field(
        description="The kind cut by the cap of the reading; null when nothing is cut."
    )
    covered_after: datetime | None = Field(
        description="The date of the first item of the kind cut left out, excluded: each item"
        " of that kind strictly more recent was read; null when nothing is cut."
    )


class ClaimSchema(BaseModel):
    text: str
    item_ids: list[int]


class SourceSchema(BaseModel):
    """Read from the data API, never from the output of the model."""

    item_id: int
    kind: WatchKind
    title: str
    url: str | None


class DigestSchema(BaseModel):
    subject: str
    claims: list[ClaimSchema]
    sources: list[SourceSchema]
    items_not_retained_in_output: list[int]
    claims_removed: int
    items_removed_by_checks: list[int]


class FailedSubjectSchema(BaseModel):
    subject: str
    stage: DigestStage
    error: LlmFailure


class DigestsSchema(BaseModel):
    request_id: str
    model: str = Field(
        description="The model of KB_LLM_MODEL that wrote the digests; replay for the replay."
    )
    window: WindowSchema
    since_by_subject: dict[str, datetime] = Field(
        description="The start applied to each subject: its items dated from it, and before"
        " window.until, are its own."
    )
    digests: list[DigestSchema]
    failed_subjects: list[FailedSubjectSchema]
    subjects_without_items: list[str] = Field(
        description="The subjects no item read and classified falls in, from their start."
    )
    no_suitable_subject: list[int] = Field(
        description="Items of the classification that no subject suits."
    )
    unanswered: list[int] = Field(
        description="Items the classification left without answer, in no digest either."
    )
    items_in: int
    items_truncated: int
    items_dropped_before_writing_stage: int
    items_before_subject_start: int = Field(
        description="Items classified in a subject but dated before its start."
    )
    items_capped: bool
