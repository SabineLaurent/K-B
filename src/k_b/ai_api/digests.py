"""The digests of a request: the items classified in batches, then the subjects written at once,
under the deadline; nothing is written nor logged here, each step is a span.

After a writing failed with a 429, nothing more is sent: the items of the next subjects would
leave for an answer refused (minimisation, GDPR art. 5.1.c)."""

import contextvars
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import httpx2

from k_b.ai_api.connectors.llm_client import (
    LlmCall,
    LlmFailure,
    to_failure,
    trace_contents,
)
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.stage_calls import DigestStage, StageCall, find_skipped_state
from k_b.ai_api.stages.checking import Digest, to_digest
from k_b.ai_api.stages.classification import (
    Classification,
    ClassificationFailure,
    classify,
)
from k_b.ai_api.stages.writing import (
    WRITING_PROMPT_VERSION,
    WritingOutput,
    write_subject,
)
from k_b.ai_api.tracing import TRACING_OFF, Step, Tracing
from k_b.ai_api.watch_items import (
    WatchItem,
    WatchReading,
    WritingSelection,
    select_for_writing,
)
from k_b.core.config import DigestSubject


@dataclass(frozen=True)
class FailedSubject:
    subject: str
    stage: DigestStage
    error: LlmFailure


@dataclass(frozen=True)
class DigestsResult:
    digests: tuple[Digest, ...]
    failed_subjects: tuple[FailedSubject, ...]
    # In the order of the list: no item of the reading classified in them from their start.
    subjects_without_items: tuple[str, ...]
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
    # Classified in a subject, but dated before its start: in its previous digest.
    items_before_subject_start: int
    items_capped: bool
    stage_calls: tuple[StageCall, ...]


def build_digests(
    http_client: httpx2.Client,
    settings: LlmSettings,
    reading: WatchReading,
    subjects: Sequence[DigestSubject],
    subject_starts: Mapping[str, datetime],
    until: datetime,
    deadline: Deadline,
    *,
    tracing: Tracing = TRACING_OFF,
) -> DigestsResult | ClassificationFailure:
    """The digests of the items read, in the order of the list, each of its items dated from its
    start and before until, the start of its next digest; the subjects written at once."""
    classification = classify(
        http_client, settings, reading.items, subjects, deadline, tracing=tracing
    )
    if isinstance(classification, ClassificationFailure):
        return classification
    subjects_to_write: list[tuple[DigestSubject, list[WatchItem]]] = []
    subjects_without_items: list[str] = []
    items_before_subject_start = 0
    for subject in subjects:
        classified_items = list_subject_items(reading, classification, subject.name)
        # Before the selection for the writing: MAX_ITEMS_PER_DIGEST counts the items kept.
        items_from_start = [
            item
            for item in classified_items
            if item.source_date >= subject_starts[subject.name]
        ]
        items_before_subject_start += len(classified_items) - len(items_from_start)
        # From until, the start of the next digest: in it, not in this one too.
        subject_items = [item for item in items_from_start if item.source_date < until]
        if subject_items:
            subjects_to_write.append((subject, subject_items))
        else:
            subjects_without_items.append(subject.name)
    writings = write_subjects(
        http_client, settings, subjects_to_write, deadline, tracing=tracing
    )
    return DigestsResult(
        digests=tuple(w.digest for w in writings if w.digest is not None),
        failed_subjects=tuple(w.failure for w in writings if w.failure is not None),
        subjects_without_items=tuple(subjects_without_items),
        no_suitable_subject=classification.no_suitable_subject,
        unanswered=classification.unanswered,
        items_in=len(reading.items),
        items_truncated=sum(w.items_truncated for w in writings),
        items_dropped_before_writing_stage=reading.items_dropped
        + sum(w.items_dropped for w in writings),
        items_before_subject_start=items_before_subject_start,
        items_capped=reading.items_capped,
        stage_calls=(
            *classification.stage_calls,
            *(w.stage_call for w in writings if w.stage_call is not None),
        ),
    )


@dataclass(frozen=True)
class SubjectWriting:
    """What the writing of a subject gives: its digest or its failure, and its call to the model,
    None for a subject skipped before any request."""

    digest: Digest | None
    failure: FailedSubject | None
    stage_call: StageCall | None
    items_truncated: int = 0
    items_dropped: int = 0


def write_subjects(
    http_client: httpx2.Client,
    settings: LlmSettings,
    subjects_to_write: Sequence[tuple[DigestSubject, list[WatchItem]]],
    deadline: Deadline,
    *,
    tracing: Tracing,
) -> list[SubjectWriting]:
    """Each subject written in its thread, all at once, the writings in the order of the list
    whatever order they end in (decision of Sabine of 2026-11-17, #630). The client of httpx2 is
    shared: its pool is thread-safe. Each thread runs in a copy of the context, where the span of
    the request is current: OpenTelemetry keeps it in contextvars, which a thread does not get."""
    rate_limited = threading.Event()
    if settings.provider == "replay" or len(subjects_to_write) < 2:
        # In series, stopped by a fault: the answers of the replay follow the order of the
        # requests (connectors/llm_replay.py).
        return [
            write_one_subject(
                http_client,
                settings,
                subject,
                subject_items,
                deadline,
                rate_limited,
                tracing=tracing,
            )
            for subject, subject_items in subjects_to_write
        ]
    with ThreadPoolExecutor(max_workers=len(subjects_to_write)) as pool:
        futures = [
            pool.submit(
                contextvars.copy_context().run,
                write_one_subject,
                http_client,
                settings,
                subject,
                subject_items,
                deadline,
                rate_limited,
                tracing=tracing,
            )
            for subject, subject_items in subjects_to_write
        ]
        return [future.result() for future in futures]


def write_one_subject(
    http_client: httpx2.Client,
    settings: LlmSettings,
    subject: DigestSubject,
    subject_items: list[WatchItem],
    deadline: Deadline,
    rate_limited: threading.Event,
    *,
    tracing: Tracing,
) -> SubjectWriting:
    """The writing of a subject and its checks, a span; nothing sent past the deadline or after a
    429 of another subject. In parallel, the subjects leave at once, before any 429 is known: the
    rule holds for those not sent yet (decision of Sabine of 2026-11-18, #630)."""
    with tracing.step(
        "write_subject", attributes={"k_b.subject": subject.name}
    ) as step:
        skipped_state = find_skipped_state(rate_limited.is_set(), deadline)
        if skipped_state is not None:
            # A span in error, without request: nothing is sent for this subject.
            step.fail(skipped_state)
            return SubjectWriting(
                digest=None,
                failure=FailedSubject(subject.name, "write", skipped_state),
                stage_call=None,
            )
        selection = select_for_writing(subject_items)
        llm_call = write_subject(
            http_client,
            settings,
            subject,
            selection.items,
            deadline,
            tracing=tracing,
        )
        # Sent before the checks of the stage: a fault in them would lose it. A claim removed
        # is no anomaly (decision D1 of Sabine, 2026-10-27).
        trace_contents(llm_call, tracing=tracing)
        digest = (
            None
            if llm_call.output is None
            else to_digest(subject.name, selection.items, llm_call.output)
        )
        trace_writing(step, selection, llm_call, digest, tracing=tracing)
    if digest is None and llm_call.saw_rate_limit:
        rate_limited.set()
    return SubjectWriting(
        digest=digest,
        failure=None
        if digest is not None
        else FailedSubject(subject.name, "write", to_failure(llm_call.outcome)),
        stage_call=to_stage_call(subject, selection, llm_call, digest),
        items_truncated=selection.items_truncated,
        items_dropped=selection.items_dropped,
    )


def to_stage_call(
    subject: DigestSubject,
    selection: WritingSelection,
    llm_call: LlmCall[WritingOutput],
    digest: Digest | None,
) -> StageCall:
    """The call of a writing and what its metric line needs of it."""
    return StageCall(
        stage="write",
        subject=subject.name,
        prompt_version=WRITING_PROMPT_VERSION,
        items_in=len(selection.items),
        items_truncated=selection.items_truncated,
        facts_checked=None if digest is None else digest.facts_checked,
        facts_found=None if digest is None else digest.facts_found,
        facts_found_in_item=None if digest is None else digest.facts_found_in_item,
        facts_found_in_text=None if digest is None else digest.facts_found_in_text,
        claims_removed=None if digest is None else digest.claims_removed,
        items_removed_by_checks=None
        if digest is None
        else len(digest.items_removed_by_checks),
        items_with_subject=None,
        items_no_suitable_subject=None,
        items_unanswered=None,
        llm_call=llm_call,
    )


def list_subject_items(
    reading: WatchReading, classification: Classification, subject: str
) -> list[WatchItem]:
    """The items the classification put in subject, in the order of the reading."""
    return [
        item
        for item in reading.items
        if classification.subject_by_item_id.get(item.item_id) == subject
    ]


def trace_writing(
    step: Step,
    selection: WritingSelection,
    llm_call: LlmCall[WritingOutput],
    digest: Digest | None,
    *,
    tracing: Tracing,
) -> None:
    """The result of a writing on its span, by identifiers and counts, and the evaluation of each
    claim removed, tied to the request whose output was checked."""
    step.set(
        {
            "k_b.outcome": llm_call.outcome,
            "k_b.items.dropped": selection.items_dropped,
            "k_b.items.truncated": selection.items_truncated,
        }
    )
    step.set_ids("k_b.items.sent.ids", [item.item_id for item in selection.items])
    if digest is None:
        step.fail(to_failure(llm_call.outcome))
        return
    step.set(
        {
            "k_b.facts.checked": digest.facts_checked,
            "k_b.facts.found": digest.facts_found,
            "k_b.facts.found_in_item": digest.facts_found_in_item,
            "k_b.facts.found_in_text": digest.facts_found_in_text,
            "k_b.claims.removed": digest.claims_removed,
        }
    )
    step.set_ids("k_b.items.not_retained.ids", digest.items_not_retained_in_output)
    step.set_ids("k_b.items.removed_by_checks.ids", digest.items_removed_by_checks)
    for removed in digest.removed_claims:
        tracing.evaluate(llm_call.span_ref, removed.index, removed.reasons)
