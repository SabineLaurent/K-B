"""The request and the response of POST /trend-reports (docs/tendances.md, "Contrats")."""

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from k_b.ai_api.connectors.llm_client import LlmFailure
from k_b.ai_api.stages.trend_writing import WritingFailure
from k_b.items import (
    Caution,
    ChoiceCriterion,
    Criterion,
    ReadmeState,
    TrendText,
    WindowState,
    WrittenDayInStrictModel,
    has_too_many_windows,
)

RequestDay = WrittenDayInStrictModel | None


class TrendReportRequestSchema(BaseModel):
    # Any other field refused, both fields required.
    model_config = ConfigDict(extra="forbid", strict=True)

    after: RequestDay = Field(
        description="The last window of the previous report; null for the first report."
    )
    previous_first_window: RequestDay = Field(
        description="The first window of the previous report; null with after only."
    )

    @model_validator(mode="after")
    def check_previous_report(self) -> Self:
        """Both null or both given, in order, over GH_ARCHIVE_MAX_CATCH_UP_WINDOWS windows at most:
        the windows of a report."""
        if self.after is None and self.previous_first_window is None:
            return self
        if self.after is None or self.previous_first_window is None:
            raise ValueError(
                "after and previous_first_window are not both null or given"
            )
        if self.previous_first_window > self.after:
            raise ValueError("previous_first_window is after after")
        if has_too_many_windows(self.previous_first_window, self.after):
            raise ValueError("the previous report holds too many windows")
        return self


class TrendPeriodSchema(BaseModel):
    first_report: bool
    windows: list[date] = Field(
        description="The windows of the report, the oldest first, the missing ones included."
    )
    missing_windows: list[date]
    windows_capped: bool = Field(
        description="Older windows after the previous report left out."
    )
    new_evaluated: bool = Field(
        description="False for the first report, and when every window of the previous report"
        " is missing."
    )
    latest_window: date | None = Field(
        description="The latest window in the base; null when it has none."
    )


class TrajectoryPointSchema(BaseModel):
    window_end: date
    state: WindowState
    rank: int | None = Field(description="The rank by stars, in the top only.")
    stars_gained: int | None = Field(
        description="Counted by GH Archive, a sample of the stars; in the top only."
    )


class RepositoryFactsSchema(BaseModel):
    license: str | None = Field(
        description="Its SPDX identifier; null when GitHub recognizes no license."
    )
    created_at: datetime
    language: str | None
    topics: list[str]
    stars_total: int = Field(description="Read on GitHub at the request, never kept.")
    cautions: list[Caution] = Field(
        description="created_recently (less than 7 days before the request), then no_license."
    )


class TrendRepositorySchema(BaseModel):
    repository_id: int
    repository_name: str = Field(description="Its name in the most recent window.")
    criteria: list[Criterion]
    best_rank: int
    trajectory: list[TrajectoryPointSchema] = Field(
        description="One point per window of the period, in its order."
    )
    facts: RepositoryFactsSchema | None = Field(
        description="Read on GitHub; null when the repository is not a candidate."
    )


class TrendTextsSchema(BaseModel):
    """Written in French by the model and checked by the code (docs/tendances.md, "Rédaction");
    null when empty or removed."""

    sector: str | None = Field(description="Its facts taken from the topics.")
    watch_link: str | None = Field(
        description="Its facts taken from the definition of a subject of the repository."
    )
    readme_summary: str | None = Field(
        description="What the README says, as its author says it; its facts taken from the"
        " README."
    )
    promise: str | None = Field(
        description="Its facts taken from the README or the description."
    )


class ChosenRepositorySchema(BaseModel):
    repository_id: int
    repository_name: str = Field(description="Its name in the most recent window.")
    criteria: list[ChoiceCriterion] = Field(
        description="Those the model gave and the code checked, in the order durable, new,"
        " accelerating, watch_subject."
    )
    watch_subjects: list[str] = Field(
        description="With watch_subject only, in the order of the subjects of the watch."
    )
    best_rank: int
    trajectory: list[TrajectoryPointSchema] = Field(
        description="One point per window of the period, in its order."
    )
    facts: RepositoryFactsSchema = Field(description="Read on GitHub.")
    readme: ReadmeState | None = Field(
        description="read; cut, to 4,000 characters once cleaned; absent (404, 410, or empty"
        " once cleaned); refused (a 403 that is no rate limit, a 451, a redirection); null when"
        " not read: GitHub failed, or the deadline came first."
    )
    texts: TrendTextsSchema | None = Field(
        description="Null when not written, with writing_failure."
    )
    texts_removed: list[TrendText] = Field(
        description="Removed by the checks, in the order sector, watch_link, readme_summary,"
        " promise."
    )
    writing_failure: WritingFailure | None = Field(
        description="Why the texts are not written: the state of the call to the model, or of"
        " GitHub on a README, after which no README is sent; null otherwise. The facts stay."
    )


class DroppedCandidatesSchema(BaseModel):
    not_found: int
    unavailable_for_legal_reasons: int
    moved: int = Field(description="A redirection, not followed.")
    id_mismatch: int = Field(description="Another repository under the name.")
    forbidden: int = Field(description="A 403 that is not a rate limit.")


class CandidatesSchema(BaseModel):
    selected: int = Field(
        description="The repositories whose sheet is read on GitHub, 60 at most, those meeting a"
        " criterion first; read plus the sum of dropped."
    )
    read: int
    dropped: DroppedCandidatesSchema = Field(
        description="Left out by GitHub, by reason; out of repositories."
    )


class TrendReportSchema(BaseModel):
    request_id: str
    model: str | None = Field(
        description="The model that chose the repositories, none chosen included; null when"
        " the choice failed or no candidate was read."
    )
    choice_failure: LlmFailure | None = Field(
        description="The state of a choice that failed; null otherwise. The report stays"
        " factual."
    )
    chosen: list[ChosenRepositorySchema] = Field(
        description="5 at most, in the order of the model; one chosen by watch_subject alone"
        " may be out of repositories."
    )
    period: TrendPeriodSchema
    repositories: list[TrendRepositorySchema] = Field(
        description="Those meeting a criterion, by best rank then repository_id, but the"
        " candidates GitHub left out."
    )
    repositories_dropped: int = Field(
        description="Repositories meeting a criterion left out, their name `.` or with `..`."
    )
    candidates: CandidatesSchema
