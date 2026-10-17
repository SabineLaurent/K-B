"""The digests of a request on the replay provider: the items of the test base read by the data
API, classified by subject, then each subject written; one test per case of the criterion of #205
(docs/fiches-veille.md, "Contrôles", "Réponse" and "États nommés")."""

import json
import secrets
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from k_b.ai_api import classification, watch_items
from k_b.ai_api.classification import CLASSIFICATION_SYSTEM_PROMPT
from k_b.ai_api.data_api_client import read_watch
from k_b.ai_api.deadline import Deadline
from k_b.ai_api.digests import (
    ClassificationFailure,
    DigestsResult,
    FailedSubject,
    build_digests,
)
from k_b.ai_api.llm_client import build_http_client
from k_b.ai_api.llm_replay import ReplayTransport
from k_b.ai_api.llm_settings import LlmSettings
from k_b.ai_api.watch_items import WatchReading
from k_b.ai_api.writing import WRITING_SYSTEM_PROMPT
from k_b.core.config import (
    LLM_REPLAY_BASE_URL,
    MIN_SECONDS_FOR_LLM_REQUEST,
    DigestSubject,
)
from k_b.data_api.app import create_app

# The subjects of the tests, never the real ones: a change of the real list breaks no test.
TEST_SUBJECTS = (
    DigestSubject("security_alerts", "failles et alertes de sécurité"),
    DigestSubject("agent_tools", "outils et cadres d'agents"),
    DigestSubject("research", "articles de recherche"),
)
REPLAY_SETTINGS = LlmSettings(
    provider="replay",
    base_url=LLM_REPLAY_BASE_URL,
    model="replay",
    api_key=None,
    reasoning_effort=None,
    replay_steps=None,
)
# The items of the test base, in the order of the reading (test_data_api_client.py): the
# vulnerabilities 3 and 4, the advisories 9, 10 and 17, the papers 2 and 1, the releases 6, 7 and
# 8, the newsletter articles 12, 11 and 13.
SECURITY_ITEMS = [3, 4, 9, 10, 17]
AGENT_ITEMS = [6, 7, 8]
RESEARCH_ITEMS = [2, 1]
NOT_RETAINED = [12, 11, 13]
# Facts copied from the items of the test base: the GHSA of advisory 9, the tag of release 6.
SECURITY_CLAIM = {
    "text": "L'alerte GHSA-fjqc-hq36-qh5p touche langgraph-checkpoint.",
    "item_ids": ["i9"],
    "facts": [{"value": "GHSA-fjqc-hq36-qh5p", "item_id": "i9"}],
}
AGENT_CLAIM = {
    "text": "Claude Code publie la version v2.1.287.",
    "item_ids": ["i6"],
    "facts": [{"value": "v2.1.287", "item_id": "i6"}],
}


@pytest.fixture(scope="module")
def reading(items_database):
    """The watch of the test base, read by the data API with the key of its client AI_DIGEST."""
    key = secrets.token_urlsafe(32)
    with TestClient(
        create_app(items_database, {"AI_DIGEST": SecretStr(key)}),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {key}"},
    ) as data_api:
        return read_watch(
            data_api,
            datetime(2020, 1, 1, tzinfo=UTC),
            deadline=Deadline.after(3600),
        )


class Clock:
    """A clock set by the test: never the time of the machine."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class SlowTransport(ReplayTransport):
    """The replay, each answer taking the given seconds on the clock of the test."""

    def __init__(self, steps, clock, seconds_per_answer):
        super().__init__(steps)
        self.clock = clock
        self.seconds_per_answer = seconds_per_answer

    def answer(self, request):
        self.clock.now += self.seconds_per_answer
        return super().answer(request)


def completion(output):
    content = output if isinstance(output, str) else json.dumps(output)
    return {"kind": "completion", "content": content}


def classified(
    security=SECURITY_ITEMS,
    agent=AGENT_ITEMS,
    research=RESEARCH_ITEMS,
    not_retained=NOT_RETAINED,
):
    assignments = [
        {"item_id": f"i{item_id}", "subject": subject}
        for subject, item_ids in (
            ("security_alerts", security),
            ("agent_tools", agent),
            ("research", research),
        )
        for item_id in item_ids
    ]
    return completion(
        {
            "assignments": assignments,
            "not_retained": [f"i{item_id}" for item_id in not_retained],
        }
    )


def written(*claims):
    return completion({"claims": list(claims)})


# A valid request: the classification, then the writing of each subject, in the order of the list.
VALID_STEPS = [
    classified(),
    written(SECURITY_CLAIM),
    written(AGENT_CLAIM),
    written(),
]


def digest_of(reading, steps, deadline=None, transport=None, subjects=TEST_SUBJECTS):
    """The result of build_digests on the replay with these steps, and its transport."""
    transport = transport or ReplayTransport(steps)
    with build_http_client(REPLAY_SETTINGS, transport=transport) as http_client:
        result = build_digests(
            http_client,
            REPLAY_SETTINGS,
            reading,
            subjects,
            deadline or Deadline.after(3600),
        )
    return result, transport


def sent_bodies(transport):
    return [json.loads(request.content) for request in transport.requests]


def messages_of(body, role):
    return [m["content"] for m in body["messages"] if m["role"] == role]


def test_a_valid_output_gives_a_digest_per_subject_with_its_sources(reading):
    result, transport = digest_of(reading, VALID_STEPS)

    assert isinstance(result, DigestsResult)
    assert [digest.subject for digest in result.digests] == [
        "security_alerts",
        "agent_tools",
        "research",
    ]
    security = result.digests[0]
    assert [claim.text for claim in security.claims] == [SECURITY_CLAIM["text"]]
    assert security.claims[0].item_ids == (9,)
    advisory = next(item for item in reading.items if item.item_id == 9)
    assert [
        (source.item_id, source.kind, source.title, source.url)
        for source in security.sources
    ] == [(9, "advisory", advisory.source_title, advisory.url)]
    # Sent and not cited.
    assert sorted(security.not_retained) == [3, 4, 10, 17]
    assert security.claims_removed == 0
    assert security.items_uncited == ()
    # A subject written without claim: a digest without claim, its items not retained.
    assert result.digests[2].claims == ()
    assert sorted(result.digests[2].not_retained) == [1, 2]
    assert result.failed_subjects == ()
    assert result.not_retained == tuple(NOT_RETAINED)
    assert result.items_in == len(reading.items)
    assert result.items_dropped == reading.items_dropped
    assert result.items_capped is False
    assert [(call.stage, call.subject) for call in result.stage_calls] == [
        ("classify", None),
        ("write", "security_alerts"),
        ("write", "agent_tools"),
        ("write", "research"),
    ]
    assert len(transport.requests) == 4


def test_the_stage_calls_carry_their_prompt_version_and_counts(reading):
    result, _ = digest_of(reading, VALID_STEPS)

    classify_call, security_call = result.stage_calls[:2]
    assert classify_call.prompt_version == "classify-1"
    assert classify_call.items_in == len(reading.items)
    assert classify_call.claims_removed is None
    assert classify_call.llm_call.outcome == "ok"
    assert security_call.prompt_version == "write-1"
    assert security_call.items_in == len(SECURITY_ITEMS)
    assert security_call.claims_removed == 0
    assert security_call.items_uncited == 0


def test_a_subject_out_of_the_list_is_refused(reading):
    out_of_list = completion(
        {"assignments": [{"item_id": "i3", "subject": "admin"}], "not_retained": []}
    )

    result, transport = digest_of(reading, [out_of_list, out_of_list])

    assert isinstance(result, ClassificationFailure)
    assert result.state == "llm_invalid_output"
    assert result.stage_calls[0].llm_call.failed_check == "subject"
    # The schema sent holds the subjects of the list only.
    schema = sent_bodies(transport)[0]["response_format"]["json_schema"]["schema"]
    subject_schema = schema["properties"]["assignments"]["items"]["properties"][
        "subject"
    ]
    assert subject_schema["enum"] == [subject.name for subject in TEST_SUBJECTS]


def test_an_unknown_item_id_is_refused_at_the_classification(reading):
    unknown = classified(security=[*SECURITY_ITEMS, 99999])

    result, _ = digest_of(reading, [unknown, unknown])

    assert isinstance(result, ClassificationFailure)
    assert result.stage_calls[0].llm_call.failed_check == "item_id"


def test_an_unknown_item_id_is_refused_at_the_writing_and_the_others_are_returned(
    reading,
):
    invented = {**AGENT_CLAIM, "item_ids": ["i6", "i99999"]}

    result, _ = digest_of(
        reading,
        [
            classified(),
            written(SECURITY_CLAIM),
            written(invented),
            written(invented),
            written(),
        ],
    )

    assert isinstance(result, DigestsResult)
    assert result.failed_subjects == (
        FailedSubject(subject="agent_tools", stage="write", error="llm_invalid_output"),
    )
    assert [digest.subject for digest in result.digests] == [
        "security_alerts",
        "research",
    ]
    assert result.stage_calls[2].llm_call.failed_check == "item_id"


def test_a_fact_of_an_item_its_claim_does_not_cite_is_refused(reading):
    misplaced = {**AGENT_CLAIM, "facts": [{"value": "v2.1.287", "item_id": "i7"}]}

    result, _ = digest_of(
        reading,
        [
            classified(),
            written(SECURITY_CLAIM),
            written(misplaced),
            written(misplaced),
            written(),
        ],
    )

    assert result.failed_subjects[0].subject == "agent_tools"
    assert result.stage_calls[2].llm_call.failed_check == "item_id"


def test_an_item_forgotten_by_the_model_is_not_retained_without_failure(reading):
    result, _ = digest_of(
        reading,
        [classified(not_retained=[12, 11]), *VALID_STEPS[1:]],
    )

    assert isinstance(result, DigestsResult)
    assert result.not_retained == (12, 11, 13)


def test_an_item_twice_at_the_classification_is_llm_invalid_output(reading):
    twice = classified(not_retained=[*NOT_RETAINED, 9])

    result, _ = digest_of(reading, [twice, twice])

    assert isinstance(result, ClassificationFailure)
    assert result.state == "llm_invalid_output"
    assert result.stage_calls[0].llm_call.failed_check == "completeness"


def test_a_claim_too_long_is_removed_and_counted(reading):
    too_long = {**AGENT_CLAIM, "text": "v2.1.287 " + "x" * 400}

    result, _ = digest_of(
        reading,
        [classified(), written(SECURITY_CLAIM), written(too_long), written()],
    )

    agent = result.digests[1]
    assert agent.subject == "agent_tools"
    assert agent.claims == ()
    assert agent.claims_removed == 1
    # Cited by the model, no longer cited once the claim is removed.
    assert agent.items_uncited == (6,)
    assert 6 not in agent.not_retained
    assert agent.sources == ()
    assert result.stage_calls[2].claims_removed == 1
    assert result.stage_calls[2].items_uncited == 1


@pytest.mark.parametrize(
    "claim_change",
    [
        {"text": ""},
        {"facts": [{"value": "v2", "item_id": "i6"}]},
        {"facts": [{"value": "v" * 121, "item_id": "i6"}]},
        {"facts": []},
        {"facts": [{"value": "v2.1.287", "item_id": "i6"}] * 11},
    ],
)
def test_a_claim_out_of_its_bounds_is_removed(reading, claim_change):
    result, _ = digest_of(
        reading,
        [
            classified(),
            written(SECURITY_CLAIM),
            written({**AGENT_CLAIM, **claim_change}),
            written(),
        ],
    )

    assert result.digests[1].claims_removed == 1


def test_more_claims_than_the_structure_allows_is_a_schema_failure(reading):
    thirteen = written(*[AGENT_CLAIM] * 13)

    result, _ = digest_of(
        reading, [classified(), written(SECURITY_CLAIM), thirteen, thirteen, written()]
    )

    assert result.failed_subjects[0].subject == "agent_tools"
    assert result.stage_calls[2].llm_call.failed_check == "schema"


def test_a_subject_in_failure_is_named_and_the_others_are_returned(reading):
    result, _ = digest_of(
        reading,
        [
            classified(),
            written(SECURITY_CLAIM),
            {"kind": "response", "status": 503},
            {"kind": "response", "status": 503},
            written(),
        ],
    )

    assert result.failed_subjects == (
        FailedSubject(subject="agent_tools", stage="write", error="llm_unavailable"),
    )
    assert [digest.subject for digest in result.digests] == [
        "security_alerts",
        "research",
    ]


def test_a_failed_classification_carries_its_retry_after(reading):
    result, _ = digest_of(
        reading,
        [
            {"kind": "response", "status": 429, "retry_after": "1"},
            {"kind": "response", "status": 429, "retry_after": "3"},
        ],
    )

    assert isinstance(result, ClassificationFailure)
    assert result.state == "llm_rate_limited"
    assert result.retry_after_seconds == 3


def test_the_subjects_not_written_by_the_deadline_are_llm_timeout(reading):
    clock = Clock()
    # The classification and one writing fit; the second writing would start with too little time.
    deadline = Deadline.after(2 * 30 + MIN_SECONDS_FOR_LLM_REQUEST - 1, clock)
    transport = SlowTransport(VALID_STEPS, clock, seconds_per_answer=30)

    result, _ = digest_of(reading, VALID_STEPS, deadline=deadline, transport=transport)

    assert [digest.subject for digest in result.digests] == ["security_alerts"]
    assert result.failed_subjects == (
        FailedSubject(subject="agent_tools", stage="write", error="llm_timeout"),
        FailedSubject(subject="research", stage="write", error="llm_timeout"),
    )
    # Nothing is sent for a subject past the deadline: its items stay home.
    assert len(transport.requests) == 2
    assert len(result.stage_calls) == 2


def test_a_classification_not_finished_by_the_deadline_is_llm_timeout(
    reading, monkeypatch
):
    monkeypatch.setattr(classification, "MAX_ITEMS_PER_CLASSIFICATION_CALL", 10)
    clock = Clock()
    deadline = Deadline.after(30 + MIN_SECONDS_FOR_LLM_REQUEST - 1, clock)
    # A valid output for the first batch: the deadline, not a refusal, stops the second.
    steps = [
        classified(
            security=[3, 4, 9, 10, 17],
            agent=[6, 7, 8],
            research=[2, 1],
            not_retained=[],
        )
    ]
    transport = SlowTransport(steps, clock, seconds_per_answer=30)

    result, _ = digest_of(reading, steps, deadline=deadline, transport=transport)

    assert isinstance(result, ClassificationFailure)
    assert result.state == "llm_timeout"
    assert len(transport.requests) == 1


def test_the_classification_is_split_in_batches_each_checked_against_its_items(
    reading, monkeypatch
):
    monkeypatch.setattr(classification, "MAX_ITEMS_PER_CLASSIFICATION_CALL", 10)
    first_batch = classified(
        security=SECURITY_ITEMS,
        agent=AGENT_ITEMS,
        research=RESEARCH_ITEMS,
        not_retained=[],
    )
    second_batch = classified(
        security=[], agent=[], research=[], not_retained=NOT_RETAINED
    )

    result, transport = digest_of(
        reading, [first_batch, second_batch, *VALID_STEPS[1:]]
    )

    assert isinstance(result, DigestsResult)
    first, second = sent_bodies(transport)[:2]
    assert len(json.loads(messages_of(first, "user")[0])["items"]) == 10
    assert len(json.loads(messages_of(second, "user")[0])["items"]) == 3
    assert result.not_retained == tuple(NOT_RETAINED)


def test_an_item_of_another_batch_is_refused(reading, monkeypatch):
    monkeypatch.setattr(classification, "MAX_ITEMS_PER_CLASSIFICATION_CALL", 10)
    # Item 13 is in the second batch, not in the first.
    wrong_batch = classified(not_retained=[13])

    result, _ = digest_of(reading, [wrong_batch, wrong_batch])

    assert isinstance(result, ClassificationFailure)
    assert result.stage_calls[0].llm_call.failed_check == "item_id"


def test_an_empty_window_calls_no_model():
    empty = WatchReading(
        items=(), items_dropped=2, capped_kind=None, covered_after=None
    )

    result, transport = digest_of(empty, [])

    assert result == DigestsResult(
        digests=(),
        failed_subjects=(),
        not_retained=(),
        items_in=0,
        items_truncated=0,
        items_dropped=2,
        items_capped=False,
        stage_calls=(),
    )
    assert transport.requests == []


def test_a_subject_without_item_is_not_written(reading):
    result, transport = digest_of(
        reading,
        [
            classified(research=[], not_retained=[*NOT_RETAINED, 2, 1]),
            *VALID_STEPS[1:3],
        ],
    )

    assert [digest.subject for digest in result.digests] == [
        "security_alerts",
        "agent_tools",
    ]
    assert len(transport.requests) == 3


def test_the_items_beyond_the_digest_cap_are_dropped_and_counted(reading, monkeypatch):
    monkeypatch.setattr(watch_items, "MAX_ITEMS_PER_DIGEST", 2)

    result, transport = digest_of(
        reading, [classified(), written(), written(), written()]
    )

    security_body = sent_bodies(transport)[1]
    assert len(json.loads(messages_of(security_body, "user")[0])["items"]) == 2
    # 3 security items and 1 agent item beyond 2, added to those of the reading.
    assert result.items_dropped == reading.items_dropped + 3 + 1


def test_a_source_url_without_http_scheme_is_returned_null(reading):
    trapped = WatchReading(
        items=tuple(
            replace(item, url="javascript:alert(1)") if item.item_id == 9 else item
            for item in reading.items
        ),
        items_dropped=reading.items_dropped,
        capped_kind=None,
        covered_after=None,
    )

    result, _ = digest_of(trapped, VALID_STEPS)

    assert result.digests[0].sources[0].url is None


def test_the_items_go_in_the_user_message_never_in_a_system_message(reading):
    """Rule 8 of poc.md: the text of a source is data; the retry adds a constant reminder."""
    result, transport = digest_of(
        reading,
        [completion("not json"), *VALID_STEPS],
    )

    assert isinstance(result, DigestsResult)
    bodies = sent_bodies(transport)
    titles = [item.fields.title for item in reading.items]
    for body in bodies:
        system_text = "\n".join(messages_of(body, "system"))
        assert not any(title in system_text for title in titles)
    assert messages_of(bodies[0], "system") == [CLASSIFICATION_SYSTEM_PROMPT]
    assert messages_of(bodies[1], "system")[0].startswith(CLASSIFICATION_SYSTEM_PROMPT)
    assert messages_of(bodies[2], "system") == [WRITING_SYSTEM_PROMPT]
    user_data = json.loads(messages_of(bodies[0], "user")[0])
    assert {item["item_id"] for item in user_data["items"]} == {
        f"i{item.item_id}" for item in reading.items
    }
    assert user_data["subjects"] == [
        {"name": subject.name, "definition": subject.definition}
        for subject in TEST_SUBJECTS
    ]


def test_the_retry_of_a_stage_sends_its_reminder(reading):
    result, transport = digest_of(
        reading,
        [
            classified(),
            written(SECURITY_CLAIM),
            written({**AGENT_CLAIM, "item_ids": ["i99999"]}),
            written(AGENT_CLAIM),
            written(),
        ],
    )

    assert isinstance(result, DigestsResult)
    retry = sent_bodies(transport)[3]
    assert messages_of(retry, "system")[0] != WRITING_SYSTEM_PROMPT
    assert messages_of(retry, "system")[0].startswith(WRITING_SYSTEM_PROMPT)
    assert result.stage_calls[2].llm_call.first_failed_check == "item_id"


def schema_sent(body):
    return body["response_format"]["json_schema"]["schema"]


def test_the_schema_of_each_call_holds_the_items_of_this_call_only(reading):
    _, transport = digest_of(reading, VALID_STEPS)

    classification_body, security_body = sent_bodies(transport)[:2]
    assignment = schema_sent(classification_body)["properties"]["assignments"]
    assert assignment["items"]["properties"]["item_id"]["enum"] == [
        f"i{item.item_id}" for item in reading.items
    ]
    claim = schema_sent(security_body)["properties"]["claims"]["items"]
    sent_refs = [
        item["item_id"]
        for item in json.loads(messages_of(security_body, "user")[0])["items"]
    ]
    assert sorted(claim["properties"]["item_ids"]["items"]["enum"]) == sorted(sent_refs)
    assert sorted(sent_refs) == sorted(f"i{item_id}" for item_id in SECURITY_ITEMS)


def test_every_call_of_the_request_waits_no_longer_than_its_deadline(reading):
    _, transport = digest_of(reading, VALID_STEPS, deadline=Deadline.after(50, Clock()))

    assert [
        request.extensions["timeout"]["read"] for request in transport.requests
    ] == [50] * len(VALID_STEPS)


@pytest.mark.parametrize("item_ids", [[], ["i3", "i4", "i9", "i10", "i17", "i3"]])
def test_a_claim_citing_no_item_or_more_than_five_is_a_schema_failure(
    reading, item_ids
):
    out_of_structure = written({**SECURITY_CLAIM, "item_ids": item_ids})

    result, _ = digest_of(
        reading,
        [
            classified(),
            out_of_structure,
            out_of_structure,
            written(AGENT_CLAIM),
            written(),
        ],
    )

    assert result.failed_subjects[0].subject == "security_alerts"
    assert result.stage_calls[1].llm_call.failed_check == "schema"


def test_an_item_cited_twice_in_a_claim_is_refused(reading):
    twice = written({**SECURITY_CLAIM, "item_ids": ["i9", "i9"]})

    result, _ = digest_of(
        reading, [classified(), twice, twice, written(AGENT_CLAIM), written()]
    )

    assert result.failed_subjects[0].subject == "security_alerts"
    assert result.stage_calls[1].llm_call.failed_check == "item_id"


@pytest.mark.parametrize(
    "rate_limited_steps",
    [
        # A Retry-After above the maximum: no retry.
        [{"kind": "response", "status": 429, "retry_after": "60"}],
        # A 429 again after the retry.
        [
            {"kind": "response", "status": 429, "retry_after": "1"},
            {"kind": "response", "status": 429, "retry_after": "1"},
        ],
    ],
)
def test_after_a_writing_rate_limited_nothing_more_is_sent(reading, rate_limited_steps):
    result, transport = digest_of(
        reading, [classified(), written(SECURITY_CLAIM), *rate_limited_steps]
    )

    assert [digest.subject for digest in result.digests] == ["security_alerts"]
    assert result.failed_subjects == (
        FailedSubject(subject="agent_tools", stage="write", error="llm_rate_limited"),
        FailedSubject(subject="research", stage="write", error="llm_rate_limited"),
    )
    # The items of research never left.
    assert len(transport.requests) == 2 + len(rate_limited_steps)
    assert [call.subject for call in result.stage_calls] == [
        None,
        "security_alerts",
        "agent_tools",
    ]


def test_after_a_429_whose_retry_the_deadline_cuts_nothing_more_is_sent(reading):
    # 25 s left: the retry after 20 s would leave 5, under the minimum; the next subject would
    # still have 25.
    deadline = Deadline.after(25, Clock())

    result, transport = digest_of(
        reading,
        [
            classified(),
            written(SECURITY_CLAIM),
            {"kind": "response", "status": 429, "retry_after": "20"},
        ],
        deadline=deadline,
    )

    assert result.failed_subjects == (
        FailedSubject(subject="agent_tools", stage="write", error="llm_timeout"),
        FailedSubject(subject="research", stage="write", error="llm_rate_limited"),
    )
    assert len(transport.requests) == 3


def test_a_classification_whose_retry_the_deadline_cuts_gives_no_retry_after(reading):
    deadline = Deadline.after(20, Clock())

    result, _ = digest_of(
        reading,
        [{"kind": "response", "status": 429, "retry_after": "15"}],
        deadline=deadline,
    )

    assert isinstance(result, ClassificationFailure)
    assert result.state == "llm_timeout"
    assert result.retry_after_seconds is None
    # What was observed stays in the call, for the metric.
    assert result.stage_calls[0].llm_call.retry_after_seconds == 15


def test_an_item_cut_for_the_writing_is_counted(reading):
    long_summary = WatchReading(
        items=tuple(
            replace(item, fields=item.fields.model_copy(update={"summary": "s" * 2500}))
            if item.item_id == 2
            else item
            for item in reading.items
        ),
        items_dropped=reading.items_dropped,
        capped_kind=None,
        covered_after=None,
    )

    result, _ = digest_of(long_summary, VALID_STEPS)

    assert result.items_truncated == 1
    assert result.stage_calls[3].items_truncated == 1
