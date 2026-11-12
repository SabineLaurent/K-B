"""The responses of GET /tops/{top} and GET /tops/{top}/days: the API's own models, never
TopProduction, so that a field added to the twin is not served."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from k_b.core.config import MAX_TOP_LIMIT
from k_b.items import MAX_TOP_DESCRIPTION_CHARS, TopName


class TopRepositorySchema(BaseModel):
    rank: int
    repository_name: str
    url: str = Field(description="https://github.com/ followed by repository_name.")
    description: str | None = Field(
        description="Shown as text: on one line, without a hidden character, never escaped."
    )
    description_truncated: bool = Field(
        description=f"The description was cut at {MAX_TOP_DESCRIPTION_CHARS} characters."
    )
    count: int = Field(
        description="Its stars in most_starred, its forks in most_forked, at ranked_at."
    )


class TopSchema(BaseModel):
    top: TopName
    day: date = Field(description="The day of the twin, the day of ranked_at in UTC.")
    ranked_at: datetime = Field(
        description="The moment the ranking of the top was collected from GitHub."
    )
    repositories: list[TopRepositorySchema] = Field(
        description=f"By rank, the first limit of {MAX_TOP_LIMIT} at most."
    )


class TopDaysSchema(BaseModel):
    # The most recent first, none after today (UTC).
    days: list[date]
    total: int = Field(description="The days of the top, every page counted.")
