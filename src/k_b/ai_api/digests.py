"""The digests of a request: the items classified in batches, then each subject written, one call
after the other, under the deadline; nothing is written nor logged here.

After a writing failed with a 429, nothing more is sent: the items of the next subjects would
leave for an answer refused (minimisation, GDPR art. 5.1.c)."""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx2

from k_b.ai_api.connectors.llm_client import LlmFailure, to_failure
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.stage_calls import Stage, StageCall
from k_b.ai_api.stages.checking import Digest, to_digest
from k_b.ai_api.stages.classification import ClassificationFailure, classify
from k_b.ai_api.stages.writing import WRITING_PROMPT_VERSION, write_subject
from k_b.ai_api.watch_items import WatchReading, select_for_writing
from k_b.core.config import DigestSubject


@dataclass(frozen=True)
class FailedSubject:
    subject: str
    stage: Stage
    error: LlmFailure


@dataclass(frozen=True)
class DigestsResult:
    digests: tuple[Digest, ...]
    failed_subjects: tuple[FailedSubject, ...]
    # Of the classification, in the order of the reading: the items no subject suits, and the
    # items the model left without answer.
    no_suitable_subject: tuple[int, ...]
    unanswered: tuple[int, ...]
    # Items read.
    items_in: int
    # Items with a field cut for the writing.
    items_truncated: int
    # Dropped by the reading, then beyond MAX_ITEMS_PER_DIGEST of a digest.
    items_dropped_before_writing_stage: int
    items_capped: bool
    stage_calls: tuple[StageCall, ...]


def build_digests(
    http_client: httpx2.Client,
    settings: LlmSettings,
    reading: WatchReading,
    subjects: Sequence[DigestSubject],
    deadline: Deadline,
) -> DigestsResult | ClassificationFailure:
    """The digests of the items read, one subject after the other in the order of the list."""
    classification = classify(http_client, settings, reading.items, subjects, deadline)
    if isinstance(classification, ClassificationFailure):
        return classification
    digests: list[Digest] = []
    failed_subjects: list[FailedSubject] = []
    stage_calls = list(classification.stage_calls)
    items_truncated = 0
    items_dropped_before_writing_stage = reading.items_dropped
    is_rate_limited = False
    for subject in subjects:
        subject_items = [
            item
            for item in reading.items
            if classification.subject_by_item_id.get(item.item_id) == subject.name
        ]
        if not subject_items:
            continue
        if is_rate_limited:
            failed_subjects.append(
                FailedSubject(subject.name, "write", "llm_rate_limited")
            )
            continue
        if not deadline.allows_llm_request():
            failed_subjects.append(FailedSubject(subject.name, "write", "llm_timeout"))
            continue
        selection = select_for_writing(subject_items)
        items_truncated += selection.items_truncated
        items_dropped_before_writing_stage += selection.items_dropped
        llm_call = write_subject(
            http_client, settings, subject, selection.items, deadline
        )
        digest = (
            None
            if llm_call.output is None
            else to_digest(subject.name, selection.items, llm_call.output)
        )
        stage_calls.append(
            StageCall(
                stage="write",
                subject=subject.name,
                prompt_version=WRITING_PROMPT_VERSION,
                items_in=len(selection.items),
                items_truncated=selection.items_truncated,
                facts_checked=None if digest is None else digest.facts_checked,
                facts_found=None if digest is None else digest.facts_found,
                claims_removed=None if digest is None else digest.claims_removed,
                items_removed_by_checks=None
                if digest is None
                else len(digest.items_removed_by_checks),
                items_with_subject=None,
                items_no_suitable_subject=None,
                items_unanswered=None,
                llm_call=llm_call,
            )
        )
        if digest is None:
            failed_subjects.append(
                FailedSubject(subject.name, "write", to_failure(llm_call.outcome))
            )
            is_rate_limited = llm_call.saw_rate_limit
        else:
            digests.append(digest)
    return DigestsResult(
        digests=tuple(digests),
        failed_subjects=tuple(failed_subjects),
        no_suitable_subject=classification.no_suitable_subject,
        unanswered=classification.unanswered,
        items_in=len(reading.items),
        items_truncated=items_truncated,
        items_dropped_before_writing_stage=items_dropped_before_writing_stage,
        items_capped=reading.items_capped,
        stage_calls=tuple(stage_calls),
    )
