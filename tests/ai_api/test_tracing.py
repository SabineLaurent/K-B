"""The façade of the traces: a span per step, its failure named, its attributes cut, and the
evaluation of a claim removed tied to the request to the model."""

import pytest
from opentelemetry.trace import SpanKind, StatusCode

from k_b.ai_api.tracing import TRACING_OFF, cut_ids, cut_text
from k_b.core.config import MAX_TRACE_ATTRIBUTE_BYTES


class ItemTextError(Exception):
    """An error whose text quotes an item, as a ValidationError would."""


def test_a_step_is_a_span_of_its_kind_with_its_attributes(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with tracing.step("chat replay", "client", {"gen_ai.request.model": "replay"}):
        pass

    [span] = recorded_traces.spans.get_finished_spans()
    assert (span.name, span.kind) == ("chat replay", SpanKind.CLIENT)
    assert dict(span.attributes) == {"gen_ai.request.model": "replay"}
    assert span.status.status_code is StatusCode.UNSET


def test_a_step_inside_another_is_its_child(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with tracing.step("POST /digests", "server"), tracing.step("read_watch"):
        pass

    child, parent = recorded_traces.spans.get_finished_spans()
    assert child.parent.span_id == parent.context.span_id


def test_a_failed_step_names_its_state_without_description(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with tracing.step("write_subject") as step:
        step.fail("llm_timeout")

    [span] = recorded_traces.spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert span.attributes["error.type"] == "llm_timeout"


def test_an_exception_fails_the_step_by_its_type_never_its_text(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with pytest.raises(ItemTextError), tracing.step("POST /digests", "server"):
        raise ItemTextError("titre de l'item piégé")

    [span] = recorded_traces.spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert span.attributes["error.type"] == "ItemTextError"
    assert span.events == ()


def test_an_exception_keeps_the_state_named_before(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with pytest.raises(ItemTextError), tracing.step("read_watch") as step:
        step.fail("data_api_timeout")
        raise ItemTextError("texte")

    [span] = recorded_traces.spans.get_finished_spans()
    assert span.attributes["error.type"] == "data_api_timeout"


def test_a_none_is_left_out_and_a_text_cut_in_bytes(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with tracing.step("chat replay") as step:
        step.set(
            {"k_b.failed_check": None, "k_b.subject": "é" * MAX_TRACE_ATTRIBUTE_BYTES}
        )

    [span] = recorded_traces.spans.get_finished_spans()
    assert "k_b.failed_check" not in span.attributes
    assert len(span.attributes["k_b.subject"].encode()) == MAX_TRACE_ATTRIBUTE_BYTES


def test_a_list_of_ids_is_cut_to_fit_and_says_it(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()
    ids = list(range(10_000, 11_000))

    with tracing.step("classify_batch") as step:
        step.set_ids("k_b.items.unanswered.ids", ids)
        step.set_ids("k_b.items.no_suitable_subject.ids", [1, 2])

    [span] = recorded_traces.spans.get_finished_spans()
    kept = span.attributes["k_b.items.unanswered.ids"]
    assert list(kept) == ids[: len(kept)]
    assert len(",".join(map(str, kept))) <= MAX_TRACE_ATTRIBUTE_BYTES
    assert span.attributes["k_b.items.unanswered.ids_truncated"] is True
    assert list(span.attributes["k_b.items.no_suitable_subject.ids"]) == [1, 2]
    assert "k_b.items.no_suitable_subject.ids_truncated" not in span.attributes


def test_cut_ids_keeps_what_fits_exactly():
    assert cut_ids([12, 345]) == [12, 345]
    assert len(",".join(map(str, cut_ids([7] * 2000)))) <= MAX_TRACE_ATTRIBUTE_BYTES
    assert cut_ids([7] * 2000) == [7] * 1024


def test_cut_text_never_cuts_inside_a_character():
    assert cut_text("é" * 1025) == "é" * 1024


def test_an_evaluation_is_a_log_record_tied_to_the_end_of_its_span(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()
    with tracing.step("chat replay", "client") as step:
        pass

    tracing.evaluate(step.ref, 3, ["out_of_bounds", "fact_not_found:0:17"])

    [span] = recorded_traces.spans.get_finished_spans()
    [record] = recorded_traces.log_records.get_finished_logs()
    log_record = record.log_record
    assert log_record.event_name == "gen_ai.evaluation.result"
    assert (log_record.trace_id, log_record.span_id) == (
        span.context.trace_id,
        span.context.span_id,
    )
    assert log_record.timestamp == span.end_time
    assert dict(log_record.attributes) == {
        "gen_ai.evaluation.name": "k_b.claim_checks",
        "gen_ai.evaluation.score.label": "fail",
        "gen_ai.evaluation.explanation": "out_of_bounds,fact_not_found:0:17",
        "k_b.claim.index": 3,
    }
    assert log_record.body == "out_of_bounds,fact_not_found:0:17"
    assert log_record.exception is None


def test_a_step_under_way_has_no_reference(recorded_traces):
    tracing = recorded_traces.trace_export.build_tracing()

    with tracing.step("chat replay") as step, pytest.raises(ValueError):
        _ = step.ref


def test_tracing_off_records_nothing_and_still_gives_a_reference():
    with TRACING_OFF.step("chat replay", "client") as step:
        step.set({"k_b.attempt": 1})
        step.set_ids("k_b.items.sent.ids", [1])
        step.fail("llm_timeout")

    TRACING_OFF.evaluate(step.ref, 0, ["disguised_text"])

    assert not step.ref.span_context.is_valid
