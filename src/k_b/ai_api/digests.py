"""The digests of a request: the items classified in batches, then each subject written, one call
after the other, under the deadline; nothing is written nor logged here.

After a writing failed with a 429, nothing more is sent: the items of the next subjects would
leave for an answer refused (minimisation, GDPR art. 5.1.c)."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx2
from pydantic import BaseModel

from k_b.ai_api.connectors.llm_client import LlmCall, LlmFailure, to_failure
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.stages.classification import (
    CLASSIFICATION_PROMPT_VERSION,
    build_batches,
    classify_batch,
)
from k_b.ai_api.stages.fidelity import check_claim
from k_b.ai_api.stages.writing import (
    WRITING_PROMPT_VERSION,
    Claim,
    WritingOutput,
    is_within_claim_bounds,
    write_subject,
)
from k_b.ai_api.watch_items import (
    WatchItem,
    WatchKind,
    WatchReading,
    select_for_writing,
    to_item_ref,
)
from k_b.core.config import NO_SUITABLE_SUBJECT_ANSWER, DigestSubject

type Stage = Literal["classify", "write"]
# A source URL is returned only with one of these schemes (docs/fiches-veille.md, "Réponse").
SOURCE_URL_SCHEMES = ("http://", "https://")


@dataclass(frozen=True)
class StageCall:
    """A call to the model and what its metric line needs of it."""

    stage: Stage
    # None for the classification.
    subject: str | None
    prompt_version: str
    items_in: int
    # Items of this call with a field cut: at 500 characters for the classification, at 2,000
    # for the writing.
    items_truncated: int
    # Of a writing whose output is checked; None otherwise. items_removed_by_checks counts the items no
    # longer cited once the claims out of their bounds or unfaithful are removed.
    facts_checked: int | None
    facts_found: int | None
    claims_removed: int | None
    items_removed_by_checks: int | None
    # Of a classification whose output is checked; None otherwise: the items given a subject,
    # those no subject suits, and those the model left without answer, items_in in all.
    items_with_subject: int | None
    items_no_suitable_subject: int | None
    items_unanswered: int | None
    llm_call: LlmCall[BaseModel]


@dataclass(frozen=True)
class DigestClaim:
    text: str
    item_ids: tuple[int, ...]


@dataclass(frozen=True)
class DigestSource:
    """Read from the data API, never from the output of the model."""

    item_id: int
    kind: WatchKind
    title: str
    url: str | None


@dataclass(frozen=True)
class Digest:
    subject: str
    claims: tuple[DigestClaim, ...]
    sources: tuple[DigestSource, ...]
    # Sent for this subject and cited by no claim of the model.
    items_not_retained_in_output: tuple[int, ...]
    # Every fact of every claim of the output, a claim removed included.
    facts_checked: int
    facts_found: int
    claims_removed: int
    # Cited by the model, no longer cited once its claims are removed.
    items_removed_by_checks: tuple[int, ...]


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


@dataclass(frozen=True)
class ClassificationFailure:
    """The request failed at the classification: its state, the Retry-After of a rate limit, the
    calls made."""

    state: LlmFailure
    retry_after_seconds: int | None
    stage_calls: tuple[StageCall, ...]


@dataclass(frozen=True)
class Classification:
    subject_by_item_id: Mapping[int, str]
    no_suitable_subject: tuple[int, ...]
    unanswered: tuple[int, ...]
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


def classify(
    http_client: httpx2.Client,
    settings: LlmSettings,
    items: Sequence[WatchItem],
    subjects: Sequence[DigestSubject],
    deadline: Deadline,
) -> Classification | ClassificationFailure:
    """The answer for each item, batch after batch: a subject, no suitable subject, or none."""
    answer_by_ref: dict[str, str] = {}
    stage_calls: list[StageCall] = []
    for batch in build_batches(items, subjects):
        if not deadline.allows_llm_request():
            return ClassificationFailure("llm_timeout", None, tuple(stage_calls))
        llm_call = classify_batch(http_client, settings, batch, subjects, deadline)
        answers = None if llm_call.output is None else llm_call.output.root
        # The answer of each item of the batch, None for an item left without: counted by the
        # same rule as the three cases of the request below.
        batch_answers = (
            None
            if answers is None
            else [answers.get(to_item_ref(item.item_id)) for item in batch.items]
        )
        stage_calls.append(
            StageCall(
                stage="classify",
                subject=None,
                prompt_version=CLASSIFICATION_PROMPT_VERSION,
                items_in=len(batch.items),
                items_truncated=batch.items_truncated,
                facts_checked=None,
                facts_found=None,
                claims_removed=None,
                items_removed_by_checks=None,
                items_with_subject=None
                if batch_answers is None
                else len(batch_answers)
                - batch_answers.count(NO_SUITABLE_SUBJECT_ANSWER)
                - batch_answers.count(None),
                items_no_suitable_subject=None
                if batch_answers is None
                else batch_answers.count(NO_SUITABLE_SUBJECT_ANSWER),
                items_unanswered=None
                if batch_answers is None
                else batch_answers.count(None),
                llm_call=llm_call,
            )
        )
        if answers is None:
            # A Retry-After only with llm_rate_limited, the one state of the spec that gives
            # it (503): neither with a retry cut by the deadline (504) nor with a 5xx (502).
            retry_after = (
                llm_call.retry_after_seconds
                if llm_call.outcome == "llm_rate_limited"
                else None
            )
            return ClassificationFailure(
                to_failure(llm_call.outcome), retry_after, tuple(stage_calls)
            )
        answer_by_ref.update(answers)
    answer_by_item_id = {
        item.item_id: answer_by_ref.get(to_item_ref(item.item_id)) for item in items
    }
    return Classification(
        subject_by_item_id={
            item_id: answer
            for item_id, answer in answer_by_item_id.items()
            if answer is not None and answer != NO_SUITABLE_SUBJECT_ANSWER
        },
        no_suitable_subject=tuple(
            item_id
            for item_id, answer in answer_by_item_id.items()
            if answer == NO_SUITABLE_SUBJECT_ANSWER
        ),
        unanswered=tuple(
            item_id for item_id, answer in answer_by_item_id.items() if answer is None
        ),
        stage_calls=tuple(stage_calls),
    )


def to_digest(
    subject: str, items_sent: Sequence[WatchItem], output: WritingOutput
) -> Digest:
    """The digest of a writing checked: the claims within their bounds and faithful, and what the
    code computes from them."""
    item_by_ref = {to_item_ref(item.item_id): item for item in items_sent}
    fidelities = [check_claim(claim, item_by_ref) for claim in output.claims]
    kept = [
        claim
        for claim, fidelity in zip(output.claims, fidelities, strict=True)
        if is_within_claim_bounds(claim) and fidelity.is_faithful
    ]
    cited_by_model = cited_refs(output.claims)
    cited_kept = cited_refs(kept)
    removed_by_checks = cited_by_model - cited_kept
    return Digest(
        subject=subject,
        claims=tuple(to_digest_claim(claim, item_by_ref) for claim in kept),
        sources=tuple(
            to_source(item)
            for item in items_sent
            if to_item_ref(item.item_id) in cited_kept
        ),
        items_not_retained_in_output=tuple(
            item.item_id
            for item in items_sent
            if to_item_ref(item.item_id) not in cited_by_model
        ),
        facts_checked=sum(fidelity.facts_checked for fidelity in fidelities),
        facts_found=sum(fidelity.facts_found for fidelity in fidelities),
        claims_removed=len(output.claims) - len(kept),
        items_removed_by_checks=tuple(
            item.item_id
            for item in items_sent
            if to_item_ref(item.item_id) in removed_by_checks
        ),
    )


def cited_refs(claims: Iterable[Claim]) -> set[str]:
    return {ref for claim in claims for ref in claim.item_ids}


def to_digest_claim(claim: Claim, item_by_ref: Mapping[str, WatchItem]) -> DigestClaim:
    return DigestClaim(
        text=claim.text,
        item_ids=tuple(item_by_ref[ref].item_id for ref in claim.item_ids),
    )


def to_source(item: WatchItem) -> DigestSource:
    url = (
        item.url
        if item.url is not None and item.url.startswith(SOURCE_URL_SCHEMES)
        else None
    )
    return DigestSource(
        item_id=item.item_id, kind=item.kind, title=item.source_title, url=url
    )
