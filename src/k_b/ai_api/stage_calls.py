"""The calls of the stages to the model, what the metric lines and the response read of them,
and when a call is not sent."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from k_b.ai_api.connectors.llm_client import LlmCall, LlmFailure
from k_b.ai_api.deadline import Deadline

# The stages of POST /digests, which a subject that failed names (docs/tendances.md, "Métriques").
type DigestStage = Literal["classify", "write"]
type Stage = DigestStage | Literal["select", "write_trends"]


@dataclass(frozen=True)
class StageCall:
    """A call to the model and what its metric line needs of it."""

    stage: Stage
    # None for the classification, the choice and the writing of a trend report.
    subject: str | None
    prompt_version: str
    items_in: int
    # Items of this call with a field cut: at 500 characters for the classification, at 2,000
    # for the writing.
    items_truncated: int
    # Of a writing whose output is checked; None otherwise. items_removed_by_checks counts the
    # items no longer cited once the claims out of their bounds or unfaithful are removed.
    facts_checked: int | None
    facts_found: int | None
    # Of a writing of POST /digests whose output is checked; None otherwise.
    facts_found_in_item: int | None
    facts_found_in_text: int | None
    claims_removed: int | None
    items_removed_by_checks: int | None
    # Of a classification whose output is checked; None otherwise: the items given a subject,
    # those no subject suits, and those the model left without answer, items_in in all.
    items_with_subject: int | None
    items_no_suitable_subject: int | None
    items_unanswered: int | None
    llm_call: LlmCall[BaseModel]


def find_skipped_state(is_rate_limited: bool, deadline: Deadline) -> LlmFailure | None:
    """Why a call is not sent: a 429 before it, or too little time left; None if it is. After a
    call that failed with a 429, nothing more is sent: the data of the next calls would leave for
    an answer refused (minimisation, GDPR art. 5.1.c)."""
    if is_rate_limited:
        return "llm_rate_limited"
    if not deadline.allows_llm_request():
        return "llm_timeout"
    return None
