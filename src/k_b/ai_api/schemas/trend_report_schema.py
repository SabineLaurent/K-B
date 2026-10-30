"""The request and the response of POST /trend-reports (docs/tendances.md, "Contrats")."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from k_b.items import (
    Criterion,
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


class TrendRepositorySchema(BaseModel):
    repository_id: int
    repository_name: str = Field(description="Its name in the most recent window.")
    criteria: list[Criterion]
    best_rank: int
    trajectory: list[TrajectoryPointSchema] = Field(
        description="One point per window of the period, in its order."
    )


class TrendReportSchema(BaseModel):
    request_id: str
    model: str | None = Field(
        description="The model that chose the repositories; null when none chose them."
    )
    period: TrendPeriodSchema
    repositories: list[TrendRepositorySchema] = Field(
        description="Those meeting a criterion, by best rank then repository_id."
    )
    repositories_dropped: int = Field(
        description="Repositories meeting a criterion left out, their name `.` or with `..`."
    )
