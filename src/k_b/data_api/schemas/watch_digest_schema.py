"""The responses of GET /digests/{subject} and GET /digests/{subject}/days: the API's own models,
never DigestProduction, so that a field added to the twin is not served; named apart from the
schemas of POST /digests of the AI API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from k_b.items import DigestOutcome, ItemKind

# The subjects of DIGEST_SUBJECTS (core/config.py), written out for the OpenAPI to list them; kept
# equal by a test.
DigestSubjectName = Literal[
    "vulnerabilities",
    "llm_security",
    "agent_frameworks",
    "coding_assistants",
    "models",
    "ai_industry",
    "cybersecurity",
    "software_engineering",
    "tech_industry",
]

# A text of the model or of a source.
SHOWN_AS_TEXT = "Shown as text: on one line, without a hidden character, never escaped."


class WatchDigestClaimSchema(BaseModel):
    text: str = Field(description=f"Written by the model. {SHOWN_AS_TEXT}")
    item_ids: list[int] = Field(
        description="The item_id of its sources, among sources."
    )


class WatchDigestSourceSchema(BaseModel):
    item_id: int = Field(
        description="The item of the base: a base made again numbers its items anew, so lead to"
        " it only when its title is the one of the source."
    )
    title: str = Field(description=SHOWN_AS_TEXT)
    url: str | None = Field(
        description="An http or https URL the sheet writes as a link; null when it writes none."
    )


class WatchDigestSchema(BaseModel):
    subject: DigestSubjectName
    day: date = Field(description="The day of the twin, the day of until in UTC.")
    since: datetime = Field(
        description="The start of the window of the subject: a date of the sources, never of"
        " their arrival in K-B."
    )
    until: datetime = Field(description="The end of the window of the subject.")
    model: str = Field(description="The model that wrote the claims.")
    items_capped: bool = Field(
        description="The reading of the items was cut: the digest is not whole."
    )
    capped_kind: ItemKind | None = Field(
        description="The kind cut by the cap of the reading; null when nothing is cut."
    )
    covered_after: datetime | None = Field(
        description="The date of the first item of the kind cut left out, excluded: each item"
        " of that kind strictly more recent was read; null when nothing is cut."
    )
    outcome: DigestOutcome = Field(
        description="written: its claims; no_claim: no claim kept; no_item: no item fell in the"
        " subject. Without a claim, no source."
    )
    claims: list[WatchDigestClaimSchema]
    sources: list[WatchDigestSourceSchema]


class WatchDigestDaysSchema(BaseModel):
    # The most recent first, none after today (UTC).
    days: list[date]
    total: int = Field(description="The days of the subject, every page counted.")
