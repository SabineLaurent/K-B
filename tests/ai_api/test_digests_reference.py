"""The reference set of POST /digests replays through the route, on the items it was recorded on."""

import json
import re
from itertools import pairwise

import httpx2
import pytest
from digests_reference import (
    README_PATH,
    REFERENCE_PATH,
    RecordingTransport,
    build_ai_api,
    build_reference_base,
    describe_transport_error,
    find_recording_refusal,
    open_data_api,
    order_as_replayed,
    post_digests,
    read_reference,
    read_reference_items,
    read_stage,
    read_subject,
    replay_settings,
)

from k_b.ai_api.connectors.llm_replay import ReplayTransport
from k_b.ai_api.connectors.llm_settings import REPLAY_MODEL

# What the set is recorded on (decision of Sabine of 2026-11-20, #520): the model of production
# (parameter llmModel) and the effort set in infra/main.bicep, and the prompts of production; a
# change of bicep does not fail this test. Values, not the constants of the code: a new
# prompt_version leaves the set to its expiry (#482), not to this test.
PRODUCTION_MODEL = re.compile(r"gpt-6\.1-sol(-\d{4}-\d{2}-\d{2})?")
PRODUCTION_REASONING_EFFORT = "low"
RECORDED_PROMPT_VERSION_BY_STAGE = {"classify": "classify-2", "write": "write-1"}


def read_licenses():
    """The column "Licence" of the table "Contenus de tiers" of the README, by the file named."""
    rows = [
        line.split("|")
        for line in README_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `tests/")
    ]
    return {cells[1].strip(" `"): cells[3] for cells in rows}


def replay_reference(reference, data_dir):
    """The answer of POST /digests on the items of the set, its model replaying the set, and the
    requests the model was sent."""
    steps = [call.step for call in reference.calls]
    transport = ReplayTransport(steps)
    with open_data_api(build_reference_base(data_dir)) as data_api:
        items = read_reference_items(
            data_api, reference.request_time, reference.window_days
        )
        assert items == reference.items
        ai_api = build_ai_api(
            replay_settings(steps),
            reference.subjects,
            reference.request_time,
            data_api,
            transport,
        )
        response = post_digests(ai_api, reference.window_days)
    return response, transport.requests


def test_each_recorded_output_replays_through_post_digests(tmp_path):
    reference = read_reference(REFERENCE_PATH)
    licenses = read_licenses()
    assert reference.calls
    assert all(call.model != REPLAY_MODEL for call in reference.calls)
    assert all(item.license in licenses[item.source_file] for item in reference.items)

    response, requests = replay_reference(reference, tmp_path)

    assert response.status_code == 200
    # Each writing of the set answered at its first attempt: one digest each.
    assert response.json()["failed_subjects"] == []
    assert len(response.json()["digests"]) == sum(
        call.stage == "write" for call in reference.calls
    )
    assert [read_stage(request) for request in requests] == [
        call.stage for call in reference.calls
    ]


def test_the_set_is_recorded_on_the_model_of_production():
    """Each call of the set was answered by gpt-6.1-sol at effort low, with the prompt of its stage
    in production."""
    calls = read_reference(REFERENCE_PATH).calls

    assert [
        call.response_model
        for call in calls
        if not PRODUCTION_MODEL.fullmatch(call.response_model or "")
    ] == []
    assert {call.reasoning_effort for call in calls} == {PRODUCTION_REASONING_EFFORT}
    assert {(call.stage, call.prompt_version) for call in calls} == set(
        RECORDED_PROMPT_VERSION_BY_STAGE.items()
    )


def test_the_facts_of_the_set_are_all_in_their_item_and_in_their_text(tmp_path, capsys):
    """None of the 26 facts of the set is missing from its item or from the text of its claim."""
    replay_reference(read_reference(REFERENCE_PATH), tmp_path)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    writes = [line for line in lines if line["stage"] == "write"]
    assert [
        sum(line[field] for line in writes)
        for field in (
            "facts_checked",
            "facts_found_in_item",
            "facts_found_in_text",
            "facts_found",
        )
    ] == [26, 26, 26, 26]


def test_the_calls_recorded_in_parallel_are_kept_in_the_order_the_replay_sends_them():
    """The writings of a provider end in any order; the replay sends the classification, then
    each subject in the order of the list, its attempts one after the other."""
    recorded = [
        (None, "classify 1"),
        (None, "classify 2"),
        ("research", "research"),
        ("agent_tools", "agent_tools 1"),
        ("security_alerts", "security_alerts"),
        ("agent_tools", "agent_tools 2"),
    ]

    assert order_as_replayed(
        recorded, ["security_alerts", "agent_tools", "research"]
    ) == [
        "classify 1",
        "classify 2",
        "security_alerts",
        "agent_tools 1",
        "agent_tools 2",
        "research",
    ]


def test_the_subject_of_a_writing_is_read_in_its_user_message():
    def request(schema_name, user_data):
        body = {
            "response_format": {"json_schema": {"name": schema_name}},
            "messages": [
                {"role": "system", "content": "a prompt"},
                {"role": "user", "content": json.dumps(user_data)},
            ],
        }
        return httpx2.Request("POST", "https://models.example", json=body)

    writing = request("digest", {"subject": {"name": "research"}})
    classification = request("classification", {"items": []})

    assert read_subject(writing) == "research"
    assert read_subject(classification) is None


class FailingStream(httpx2.SyncByteStream):
    """A body whose reading fails once its status is received."""

    def __iter__(self):
        raise httpx2.ReadError("read failed on https://spotted.example/v1")
        yield b""


class FailingProvider(httpx2.BaseTransport):
    """A provider whose first request fails to connect, and whose second fails in its body."""

    def __init__(self):
        self.requests = 0

    def handle_request(self, request):
        self.requests += 1
        if self.requests == 1:
            try:
                raise ConnectionRefusedError("refused by https://spotted.example")
            except ConnectionRefusedError as error:
                raise httpx2.ConnectError("https://spotted.example/v1") from error
        return httpx2.Response(200, stream=FailingStream())


def test_a_transport_error_is_refused_by_its_classes_and_its_status_never_its_message():
    transport = RecordingTransport(replay_settings([]), ["research"])
    transport.provider.close()
    transport.provider = FailingProvider()
    request = httpx2.Request("POST", "https://models.example/v1/chat/completions")
    for _ in range(2):
        with pytest.raises(httpx2.TransportError):
            transport.handle_request(request)

    refusal = find_recording_refusal(httpx2.Response(200), transport)

    assert refusal == (
        "transport errors: 2 (httpx2.ConnectError from ConnectionRefusedError,"
        " httpx2.ReadError after status 200)"
    )


def test_a_chain_of_causes_is_named_through_its_contexts_and_cut_after_five_links():
    errors = [
        httpx2.ReadError("https://spotted.example"),
        OSError(),
        ValueError(),
        TypeError(),
        KeyError(),
        IndexError(),
    ]
    for error, context in pairwise(errors):
        error.__context__ = context

    assert describe_transport_error(errors[1], None) == (
        "OSError from ValueError from TypeError from KeyError from IndexError"
    )
    assert describe_transport_error(errors[0], None) == (
        "httpx2.ReadError from OSError from ValueError from TypeError from KeyError"
        " from \u2026"
    )
