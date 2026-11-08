"""The client of the trend reports: its request, and the response it accepts, each 200 made by the
schema of the AI API, which ties the client to the contract, then changed to break one check."""

import json
from datetime import UTC, date, datetime
from typing import get_args

import httpx2
import pytest
from post.test_ai_api_client import (
    OTHER_REQUEST_ID,
    REQUEST_ID,
    SETTINGS,
    TEST_API_KEY,
    answer,
)

from k_b.ai_api.connectors.github_client import GithubState
from k_b.ai_api.connectors.llm_client import LlmFailure
from k_b.ai_api.schemas.trend_report_schema import (
    CandidatesSchema,
    ChosenRepositorySchema,
    DroppedCandidatesSchema,
    RepositoryFactsSchema,
    TrajectoryPointSchema,
    TrendPeriodSchema,
    TrendReportSchema,
    TrendRepositorySchema,
    TrendTextsSchema,
)
from k_b.core.config import TREND_SECTOR_MAX_CHARS
from k_b.post.ai_api_client import (
    AiApiError,
    build_ai_api_client,
    read_ai_api_client_settings_or_refusal,
)
from k_b.post.trend_report_client import (
    TREND_REPORT_KEY_VARIABLE,
    GithubFailure,
    ModelFailure,
    request_trend_report,
)

# The day of the run; the latest window of the base ends the day before.
TODAY = date(2026, 11, 1)
WINDOWS = [date(2026, 10, day) for day in (28, 29, 30, 31)]
PREVIOUS_FIRST = date(2026, 10, 24)
AFTER = date(2026, 10, 27)
RISING_NAME = "owner/rising-repository"


def point(window_end, rank=None, state=None):
    state = state or ("top" if rank else "out_of_top")
    return TrajectoryPointSchema(
        window_end=window_end,
        state=state,
        rank=rank,
        stars_gained=None if rank is None else 60 - rank,
    )


RISING = TrendRepositorySchema(
    repository_id=4_242,
    repository_name=RISING_NAME,
    criteria=["new", "accelerating"],
    best_rank=2,
    trajectory=[
        point(day, rank) for day, rank in zip(WINDOWS, (12, 7, 4, 2), strict=True)
    ],
    # Read on GitHub.
    facts=RepositoryFactsSchema(
        license=None,
        created_at=datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
        language="Rust",
        topics=["cli", "llm"],
        stars_total=1_250,
        cautions=["created_recently", "no_license"],
    ),
)
STEADY = TrendRepositorySchema(
    repository_id=17,
    repository_name="steady/tool",
    criteria=["durable"],
    best_rank=3,
    trajectory=[
        point(WINDOWS[0], 3),
        point(WINDOWS[1], None),
        point(WINDOWS[2], 5),
        point(WINDOWS[3], 9),
    ],
    # Beyond the candidates.
    facts=None,
)
NO_CANDIDATE_DROPPED = DroppedCandidatesSchema(
    not_found=0, unavailable_for_legal_reasons=0, moved=0, id_mismatch=0, forbidden=0
)


MODEL = "gpt-6-luna"


def choose(repository, criteria=None, watch_subjects=()):
    """A repository of the response as the model chose it, by its criteria by default."""
    facts = repository.facts or RISING.facts
    return ChosenRepositorySchema(
        repository_id=repository.repository_id,
        repository_name=repository.repository_name,
        criteria=list(repository.criteria) if criteria is None else criteria,
        watch_subjects=list(watch_subjects),
        best_rank=repository.best_rank,
        trajectory=repository.trajectory,
        facts=facts,
        readme="read",
        texts=TrendTextsSchema(
            sector=None, watch_link=None, readme_summary=None, promise=None
        ),
        texts_removed=[],
        writing_failure=None,
    ).model_dump(mode="json")


def make_report(**changes):
    """A response of POST /trend-reports after a previous report, as JSON to change: its one
    candidate read, the model chose none."""
    report = TrendReportSchema(
        request_id=REQUEST_ID,
        model=MODEL,
        choice_failure=None,
        chosen=[],
        period=TrendPeriodSchema(
            first_report=False,
            windows=WINDOWS,
            missing_windows=[],
            windows_capped=False,
            new_evaluated=True,
            latest_window=WINDOWS[-1],
        ),
        repositories=[RISING, STEADY],
        repositories_dropped=0,
        candidates=CandidatesSchema(selected=1, read=1, dropped=NO_CANDIDATE_DROPPED),
    ).model_dump(mode="json")
    return report | changes


def change_period(report, **changes):
    report["period"] |= changes
    return report


def ask(handle, after=AFTER, previous_first_window=PREVIOUS_FIRST, today=TODAY):
    requests = []

    def keep_and_handle(request):
        requests.append(request)
        return handle(request)

    with build_ai_api_client(
        SETTINGS, transport=httpx2.MockTransport(keep_and_handle)
    ) as http_client:
        response = request_trend_report(
            http_client, after, previous_first_window, today
        )
    return response, requests


def ask_and_fail(handle, **request):
    with pytest.raises(AiApiError) as raised:
        ask(handle, **request)
    return raised.value


def body(report):
    return json.dumps(report).encode()


def test_the_client_reads_its_own_key_variable():
    settings = read_ai_api_client_settings_or_refusal(
        {"KB_AI_API_KEY_KB_TREND_REPORT": TEST_API_KEY}, TREND_REPORT_KEY_VARIABLE
    )

    assert settings == SETTINGS
    assert read_ai_api_client_settings_or_refusal(
        {"KB_AI_API_KEY_KB_DIGEST": TEST_API_KEY}, TREND_REPORT_KEY_VARIABLE
    ) == ("KB_AI_API_KEY_KB_TREND_REPORT: not set")


def test_the_request_gives_the_windows_of_the_previous_report_with_the_key():
    response, requests = ask(answer(content=body(make_report())))

    [request] = requests
    assert (request.method, str(request.url)) == (
        "POST",
        "http://127.0.0.1:8001/trend-reports",
    )
    assert json.loads(request.content) == {
        "after": "2026-10-27",
        "previous_first_window": "2026-10-24",
    }
    assert request.headers["Authorization"] == f"Bearer {TEST_API_KEY}"
    assert response.period.windows == WINDOWS
    assert [r.repository_name for r in response.repositories] == [
        RISING_NAME,
        "steady/tool",
    ]


def test_the_first_report_sends_both_fields_null():
    report = change_period(
        make_report(repositories=[]), first_report=True, new_evaluated=False
    )

    _, [request] = ask(
        answer(content=body(report)), after=None, previous_first_window=None
    )

    assert json.loads(request.content) == {"after": None, "previous_first_window": None}


@pytest.mark.parametrize(
    ("report", "after", "detail"),
    [
        (
            change_period(make_report(), first_report=True, new_evaluated=False),
            AFTER,
            "period.first_report (not_the_request)",
        ),
        (
            change_period(
                make_report(repositories=[]), first_report=True, new_evaluated=True
            ),
            None,
            "period.new_evaluated (first_report)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=[],
                latest_window="2026-11-02",
            ),
            date(2026, 11, 2),
            "period.latest_window (after_today)",
        ),
        (
            change_period(
                make_report(repositories=[]), windows=[], latest_window="2026-10-31"
            ),
            AFTER,
            "period.windows (empty_with_a_new_window)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=["2026-10-28", "2026-10-30", "2026-10-31"],
            ),
            AFTER,
            "period.windows (not_consecutive)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=["2026-10-31", "2026-10-30"],
                latest_window="2026-10-30",
            ),
            AFTER,
            "period.windows (not_consecutive)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=[f"2026-10-{day:02}" for day in range(16, 32)],
            ),
            date(2026, 10, 15),
            "period.windows (too_many_windows)",
        ),
        (
            make_report(repositories=[]),
            date(2026, 10, 28),
            "period.windows (not_following_the_previous_report)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=["2026-10-29", "2026-10-30", "2026-10-31"],
            ),
            AFTER,
            "period.windows (not_following_the_previous_report)",
        ),
        (
            change_period(make_report(repositories=[]), windows_capped=True),
            AFTER,
            "period.windows (not_following_the_previous_report)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=["2026-10-29", "2026-10-30", "2026-10-31"],
                windows_capped=True,
            ),
            AFTER,
            "period.windows (not_following_the_previous_report)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                windows=[f"2026-10-{day:02}" for day in range(17, 32)],
                windows_capped=True,
            ),
            date(2026, 10, 16),
            "period.windows (not_following_the_previous_report)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                first_report=True,
                new_evaluated=False,
                windows_capped=True,
            ),
            None,
            "period.windows (not_following_the_previous_report)",
        ),
        (
            change_period(make_report(repositories=[]), latest_window="2026-11-01"),
            AFTER,
            "period.windows (not_up_to_the_latest_window)",
        ),
        (
            change_period(make_report(repositories=[]), missing_windows=["2026-10-27"]),
            AFTER,
            "period.missing_windows (not_among_the_windows)",
        ),
        (
            change_period(
                make_report(repositories=[]),
                missing_windows=["2026-10-29", "2026-10-29"],
            ),
            AFTER,
            "period.missing_windows (not_among_the_windows)",
        ),
    ],
)
def test_a_period_the_request_or_the_register_cannot_hold_is_refused(
    report, after, detail
):
    failure = ask_and_fail(
        answer(content=body(report)),
        after=after,
        previous_first_window=None if after is None else PREVIOUS_FIRST,
    )

    assert failure.state == "ai_api_invalid_response"
    assert str(failure) == (
        f"ai_api_invalid_response, HTTP 200, {detail}, request_id {REQUEST_ID}"
    )


def test_fifteen_consecutive_windows_are_accepted():
    windows = [f"2026-10-{day:02}" for day in range(17, 32)]
    report = change_period(make_report(repositories=[]), windows=windows)

    response, _ = ask(answer(content=body(report)), after=date(2026, 10, 16))

    assert len(response.period.windows) == 15


def test_fifteen_windows_capped_after_older_ones_are_accepted():
    windows = [f"2026-10-{day:02}" for day in range(17, 32)]
    report = change_period(
        make_report(repositories=[]), windows=windows, windows_capped=True
    )

    response, _ = ask(answer(content=body(report)), after=date(2026, 10, 10))

    assert response.period.windows_capped


def test_an_empty_period_up_to_the_previous_report_is_accepted():
    report = change_period(
        make_report(repositories=[]), windows=[], latest_window="2026-10-27"
    )

    response, _ = ask(answer(content=body(report)))

    assert (response.period.windows, response.period.latest_window) == (
        [],
        AFTER,
    )


def repository(**changes):
    return RISING.model_dump(mode="json") | changes


def with_point(number, **changes):
    trajectory = [p.model_dump(mode="json") for p in RISING.trajectory]
    trajectory[number] |= changes
    return trajectory


@pytest.mark.parametrize(
    ("repositories", "period_changes", "detail"),
    [
        (
            [repository(), repository(repository_name="other/name")],
            {},
            "repositories.1 (repository_twice)",
        ),
        (
            [repository(trajectory=with_point(0, window_end="2026-10-27"))],
            {},
            "repositories.0.trajectory (not_the_windows)",
        ),
        (
            [repository(trajectory=with_point(1, state="missing", rank=None))],
            {},
            "repositories.0.trajectory.1 (not_the_missing_windows)",
        ),
        (
            [repository()],
            {"missing_windows": ["2026-10-29"]},
            "repositories.0.trajectory.1 (not_the_missing_windows)",
        ),
        (
            [repository(trajectory=with_point(2, state="out_of_top"))],
            {},
            "repositories.0.trajectory.2 (rank_out_of_the_top)",
        ),
        (
            [repository(trajectory=with_point(2, rank=None))],
            {},
            "repositories.0.trajectory.2 (rank_out_of_the_top)",
        ),
        (
            [repository(best_rank=4)],
            {},
            "repositories.0.best_rank (not_the_best_rank)",
        ),
        (
            [
                repository(
                    trajectory=[
                        point(day, None).model_dump(mode="json") for day in WINDOWS
                    ]
                )
            ],
            {},
            "repositories.0.best_rank (not_the_best_rank)",
        ),
        (
            [repository(criteria=["accelerating", "new"])],
            {},
            "repositories.0.criteria (not_in_order_once)",
        ),
        (
            [repository(criteria=["new", "new"])],
            {},
            "repositories.0.criteria (not_in_order_once)",
        ),
        (
            [repository()],
            {"new_evaluated": False},
            "repositories.0.criteria (new_not_evaluated)",
        ),
    ],
)
def test_a_repository_out_of_its_period_is_refused_by_its_place(
    repositories, period_changes, detail
):
    report = change_period(make_report(repositories=repositories), **period_changes)

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure) == (
        f"ai_api_invalid_response, HTTP 200, {detail}, request_id {REQUEST_ID}"
    )
    assert RISING_NAME not in str(failure)


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        (
            {"repository_name": "owner/.."},
            "repositories.0.repository_name (value_error)",
        ),
        ({"repository_name": "./repo"}, "repositories.0.repository_name (value_error)"),
        (
            {"repository_name": "owner/repo/../../etc"},
            "repositories.0.repository_name (value_error)",
        ),
        (
            {"repository_name": "owner/<b>"},
            "repositories.0.repository_name (value_error)",
        ),
        ({"criteria": []}, "repositories.0.criteria (too_short)"),
        ({"criteria": ["watch_subject"]}, "repositories.0.criteria.0 (literal_error)"),
        ({"best_rank": 31}, "repositories.0.best_rank (less_than_equal)"),
        ({"repository_id": "4242"}, "repositories.0.repository_id (int_type)"),
    ],
)
def test_a_repository_out_of_the_schema_is_refused_never_quoted(changes, detail):
    report = make_report(repositories=[repository(**changes)])

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")
    for value in ("owner/..", "./repo", "etc", "<b>", "4242"):
        assert value not in str(failure)


@pytest.mark.parametrize(
    ("facts", "detail"),
    [
        (
            {"license": "MIT <b>"},
            "repositories.0.facts.license (string_pattern_mismatch)",
        ),
        (
            {"topics": ["<b>"]},
            "repositories.0.facts.topics.0 (string_pattern_mismatch)",
        ),
        ({"language": ""}, "repositories.0.facts.language (string_pattern_mismatch)"),
        (
            {"language": "x" * 101},
            "repositories.0.facts.language (string_pattern_mismatch)",
        ),
        (
            {"language": "C\u200b"},
            "repositories.0.facts.language (string_pattern_mismatch)",
        ),
        (
            {"created_at": "0001-01-01T00:00:00+14:00"},
            "repositories.0.facts.created_at (value_error)",
        ),
        (
            {"created_at": "2026-10-27T09:00:00"},
            "repositories.0.facts.created_at (timezone_aware)",
        ),
        ({"stars_total": -1}, "repositories.0.facts.stars_total (greater_than_equal)"),
        (
            {"stars_total": 2**63},
            "repositories.0.facts.stars_total (less_than_equal)",
        ),
        ({"cautions": ["<b>"]}, "repositories.0.facts.cautions.0 (literal_error)"),
    ],
)
def test_facts_out_of_the_schema_are_refused_never_quoted(facts, detail):
    report = make_report()
    report["repositories"][0]["facts"] |= facts

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")
    assert "<b>" not in str(failure)


@pytest.mark.parametrize(
    ("facts", "detail"),
    [
        (
            {"license": "MIT", "cautions": ["no_license"]},
            "repositories.0.facts.cautions (not_the_license)",
        ),
        (
            {"license": None, "cautions": []},
            "repositories.0.facts.cautions (not_the_license)",
        ),
        (
            {"cautions": ["no_license", "created_recently"]},
            "repositories.0.facts.cautions (not_in_order_once)",
        ),
        (
            {"cautions": ["no_license", "no_license"]},
            "repositories.0.facts.cautions (not_in_order_once)",
        ),
    ],
)
def test_facts_that_contradict_themselves_are_refused(facts, detail):
    report = make_report()
    report["repositories"][0]["facts"] |= facts

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")


def test_a_repository_chosen_has_facts_in_the_table_when_it_is_there():
    report = make_report(chosen=[choose(STEADY)])

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(
        "ai_api_invalid_response, HTTP 200, chosen.0.facts (not_those_of_the_table)"
    )


def test_the_facts_of_a_repository_chosen_are_those_of_the_table():
    report = make_report(chosen=[choose(RISING)])
    report["chosen"][0]["facts"]["stars_total"] = 99

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(
        "ai_api_invalid_response, HTTP 200, chosen.0.facts (not_those_of_the_table)"
    )


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"request_id": "not-a-uuid"}, "request_id (value_error)"),
        ({"model": "gpt 6"}, "model (value_error)"),
        ({"repositories_dropped": -1}, "repositories_dropped (greater_than_equal)"),
        (
            {"period": {"windows": ["2026-10-28T00:00:00Z"]}},
            "period.first_report (missing)",
        ),
    ],
)
def test_a_response_out_of_the_schema_is_refused_by_its_place(changes, detail):
    failure = ask_and_fail(answer(content=body(make_report(**changes))))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")


@pytest.mark.parametrize(
    "day", ["2026-10-28T00:00:00Z", "28/10/2026", 1761609600, "2026-13-01"]
)
def test_a_day_not_written_yyyy_mm_dd_is_refused(day):
    report = make_report(repositories=[])
    report["period"]["windows"][0] = day

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(
        "ai_api_invalid_response, HTTP 200, period.windows.0 ("
    )


def test_a_model_once_one_chooses_is_read():
    report = make_report(model="gpt-6-luna", request_id=OTHER_REQUEST_ID)

    response, _ = ask(answer(content=body(report)))

    assert (response.model, response.request_id) == ("gpt-6-luna", OTHER_REQUEST_ID)


def test_a_refused_key_is_ai_api_unauthorized():
    failure = ask_and_fail(answer(401, b'{"error": "invalid_api_key"}'))

    assert failure.state == "ai_api_unauthorized"
    assert TEST_API_KEY not in str(failure)


def test_the_counts_of_the_candidates_are_read():
    dropped = NO_CANDIDATE_DROPPED.model_dump() | {"not_found": 1, "moved": 2}
    report = make_report(candidates={"selected": 9, "read": 6, "dropped": dropped})

    response, _ = ask(answer(content=body(report)))

    assert response.candidates.selected == 9
    assert response.candidates.read == 6
    assert response.candidates.dropped.not_found == 1
    assert response.candidates.dropped.moved == 2


@pytest.mark.parametrize(
    ("candidates", "detail"),
    [
        (
            {"read": 2},
            "candidates (not_the_sum)",
        ),
        ({"selected": 0, "read": -1}, "candidates.read (greater_than_equal)"),
        (
            {"dropped": NO_CANDIDATE_DROPPED.model_dump() | {"forbidden": -1}},
            "candidates.dropped.forbidden (greater_than_equal)",
        ),
        (
            {"dropped": {"not_found": 0}},
            "candidates.dropped.unavailable_for_legal_reasons",
        ),
    ],
    ids=["not-the-sum", "read-negative", "dropped-negative", "reason-missing"],
)
def test_counts_of_candidates_that_do_not_add_up_are_refused(candidates, detail):
    report = make_report()
    report["candidates"] |= candidates

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")


# The choice of the model (#368, docs/tendances.md, "Choix").
CANDIDATE_READ = {
    "selected": 1,
    "read": 1,
    "dropped": NO_CANDIDATE_DROPPED.model_dump(),
}
NO_CANDIDATE_READ = {
    "selected": 1,
    "read": 0,
    "dropped": NO_CANDIDATE_DROPPED.model_dump() | {"not_found": 1},
}


def test_the_failures_of_the_choice_are_those_of_the_model():
    """post does not import ai_api: its Literal is a copy, kept equal here."""
    assert get_args(ModelFailure.__value__) == get_args(LlmFailure.__value__)


def test_the_repositories_chosen_are_read_with_their_criteria_and_subjects():
    steady_read = STEADY.model_copy(update={"facts": RISING.facts})
    report = make_report(
        repositories=[
            RISING.model_dump(mode="json"),
            steady_read.model_dump(mode="json"),
        ],
        chosen=[
            choose(
                RISING, ["new", "watch_subject"], ["llm_security", "coding_assistants"]
            ),
            choose(steady_read, ["durable"]),
        ],
    )

    response, _ = ask(answer(content=body(report)))

    [rising, steady] = response.chosen
    assert (rising.repository_id, rising.repository_name) == (4_242, RISING_NAME)
    assert rising.criteria == ["new", "watch_subject"]
    assert rising.watch_subjects == ["llm_security", "coding_assistants"]
    assert steady.criteria == ["durable"]
    assert response.choice_failure is None


def test_a_repository_chosen_by_its_subject_alone_may_be_out_of_the_repositories():
    alone = STEADY.model_copy(
        update={"repository_id": 99, "repository_name": "only/subject", "criteria": []}
    )
    report = make_report(
        chosen=[choose(alone, ["watch_subject"], ["coding_assistants"])]
    )

    response, _ = ask(answer(content=body(report)))

    assert response.chosen[0].repository_name == "only/subject"


def test_a_choice_that_failed_is_read_with_its_state():
    report = make_report(model=None, choice_failure="llm_rate_limited")

    response, _ = ask(answer(content=body(report)))

    assert (response.model, response.choice_failure) == (None, "llm_rate_limited")


def test_without_any_candidate_read_neither_a_model_nor_a_failure_is_read():
    report = make_report(model=None, candidates=NO_CANDIDATE_READ)

    response, _ = ask(answer(content=body(report)))

    assert (response.model, response.choice_failure, response.chosen) == (
        None,
        None,
        [],
    )


SUBJECT_ALONE = STEADY.model_copy(
    update={"repository_id": 99, "repository_name": "only/subject", "criteria": []}
)


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        (
            {
                "chosen": [
                    choose(SUBJECT_ALONE, ["watch_subject"], ["coding_assistants"])
                ]
                * 6
            },
            "chosen (too_long)",
        ),
        ({"choice_failure": "llm_tired"}, "choice_failure (literal_error)"),
        ({"choice_failure": "llm_timeout"}, "choice_failure (with_a_model)"),
        (
            {
                "model": None,
                "choice_failure": "llm_timeout",
                "chosen": [choose(STEADY)],
            },
            "chosen (with_a_choice_failure)",
        ),
        ({"model": None, "chosen": [choose(STEADY)]}, "chosen (without_a_model)"),
        ({"model": None}, "model (no_choice_with_candidates_read)"),
        (
            {"candidates": NO_CANDIDATE_READ},
            "model (choice_without_candidate_read)",
        ),
        (
            {
                "model": None,
                "choice_failure": "llm_timeout",
                "candidates": NO_CANDIDATE_READ,
            },
            "choice_failure (choice_without_candidate_read)",
        ),
        (
            {"chosen": [choose(RISING), choose(RISING)]},
            "chosen.1 (repository_twice)",
        ),
        ({"chosen": [choose(STEADY, [])]}, "chosen.0.criteria (too_short)"),
        (
            {"chosen": [choose(STEADY) | {"criteria": ["popular"]}]},
            "chosen.0.criteria.0 (literal_error)",
        ),
        (
            {"chosen": [choose(RISING, ["accelerating", "new"])]},
            "chosen.0.criteria (not_in_order_once)",
        ),
        (
            {"chosen": [choose(STEADY, ["durable", "watch_subject"])]},
            "chosen.0.watch_subjects (not_with_watch_subject)",
        ),
        (
            {"chosen": [choose(STEADY, ["durable"], ["coding_assistants"])]},
            "chosen.0.watch_subjects (not_with_watch_subject)",
        ),
        (
            {"chosen": [choose(STEADY, ["watch_subject"], ["cooking"])]},
            "chosen.0.watch_subjects (not_in_order_once)",
        ),
        (
            {
                "chosen": [
                    choose(
                        STEADY, ["watch_subject"], ["coding_assistants", "llm_security"]
                    )
                ]
            },
            "chosen.0.watch_subjects (not_in_order_once)",
        ),
        (
            {"chosen": [choose(STEADY, ["accelerating"])]},
            "chosen.0.criteria (not_met_in_the_repositories)",
        ),
        (
            {"chosen": [choose(SUBJECT_ALONE, ["durable"])]},
            "chosen.0.criteria (not_met_in_the_repositories)",
        ),
    ],
    ids=[
        "six-chosen",
        "failure-unknown",
        "failure-with-a-model",
        "failure-with-chosen",
        "chosen-without-model",
        "candidates-read-without-choice",
        "model-without-candidate",
        "failure-without-candidate",
        "repository-twice",
        "no-criterion",
        "criterion-unknown",
        "criteria-out-of-order",
        "watch-subject-without-subject",
        "subject-without-watch-subject",
        "subject-out-of-the-list",
        "subjects-out-of-order",
        "criterion-not-met",
        "criterion-of-a-repository-not-reported",
    ],
)
def test_a_choice_the_response_contradicts_is_refused_by_its_place(changes, detail):
    report = make_report(**changes)

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")


def test_new_chosen_while_not_evaluated_is_refused():
    first = make_report(
        repositories=[STEADY.model_dump(mode="json")],
        chosen=[choose(RISING, ["new"])],
    )
    first["period"] |= {"first_report": True, "new_evaluated": False}

    failure = ask_and_fail(
        answer(content=body(first)), after=None, previous_first_window=None
    )

    assert str(failure).startswith(
        "ai_api_invalid_response, HTTP 200, chosen.0.criteria (new_not_evaluated)"
    )


def test_a_name_chosen_that_cannot_make_a_url_is_refused_never_quoted():
    report = make_report(chosen=[choose(STEADY) | {"repository_name": "owner/.."}])

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(
        "ai_api_invalid_response, HTTP 200, chosen.0.repository_name (value_error)"
    )
    assert "owner/.." not in str(failure)


# The texts of the repositories chosen (#369, docs/tendances.md, "Ce que rend #369").
TEXTS = {
    "sector": "Outil en ligne de commande.",
    "watch_link": None,
    "readme_summary": "Selon son auteur, un outil pour les LLM.",
    "promise": "Il promet la rapidité.",
}
WRITTEN = {
    "readme": "cut",
    "texts": TEXTS,
    "texts_removed": ["watch_link"],
    "writing_failure": None,
}
WRITING_FAILURES = (*get_args(LlmFailure.__value__), *get_args(GithubState.__value__))
NOT_WRITTEN = {"readme": None, "texts": None, "texts_removed": []}


def report_with_writing(**writing):
    return make_report(chosen=[choose(RISING) | WRITTEN | writing])


def test_the_failures_of_a_writing_are_those_of_the_model_and_of_github():
    """post does not import ai_api: its Literals are copies, kept equal here."""
    assert get_args(GithubFailure.__value__) == get_args(GithubState.__value__)


def test_the_texts_of_a_repository_chosen_are_read():
    response, _ = ask(answer(content=body(report_with_writing())))

    [chosen] = response.chosen
    assert chosen.readme == "cut"
    assert chosen.texts.sector == TEXTS["sector"]
    assert chosen.texts.watch_link is None
    assert chosen.texts_removed == ["watch_link"]
    assert chosen.writing_failure is None


@pytest.mark.parametrize("state", WRITING_FAILURES)
def test_a_writing_that_failed_is_read_with_its_state(state):
    response, _ = ask(
        answer(content=body(report_with_writing(**NOT_WRITTEN, writing_failure=state)))
    )

    [chosen] = response.chosen
    assert chosen.writing_failure == state
    assert chosen.texts is None


@pytest.mark.parametrize(
    ("writing", "detail"),
    [
        ({"texts": None}, "chosen.0.texts (not_written_without_a_failure)"),
        (
            {"writing_failure": "llm_timeout"},
            "chosen.0.texts (written_with_a_failure)",
        ),
        (
            {
                **NOT_WRITTEN,
                "writing_failure": "github_timeout",
                "texts_removed": ["sector"],
            },
            "chosen.0.texts_removed (with_a_writing_failure)",
        ),
        (
            {
                "texts_removed": ["promise", "watch_link"],
                "texts": TEXTS | {"promise": None},
            },
            "chosen.0.texts_removed (not_in_order_once)",
        ),
        (
            {"texts_removed": ["watch_link", "watch_link"]},
            "chosen.0.texts_removed (not_in_order_once)",
        ),
        ({"texts_removed": ["sector"]}, "chosen.0.texts.sector (removed_but_written)"),
        ({"readme": None}, "chosen.0.readme (not_read_without_a_failure)"),
        ({"readme": "absent"}, "chosen.0.texts.readme_summary (without_a_readme)"),
        ({"readme": "refused"}, "chosen.0.texts.readme_summary (without_a_readme)"),
        (
            {
                "texts": TEXTS | {"watch_link": "Lié à la sécurité."},
                "texts_removed": [],
            },
            "chosen.0.texts.watch_link (without_a_subject)",
        ),
    ],
    ids=[
        "not-written-without-a-failure",
        "written-with-a-failure",
        "removed-with-a-failure",
        "removed-out-of-order",
        "removed-twice",
        "removed-but-written",
        "readme-not-read-without-a-failure",
        "summary-without-readme",
        "summary-of-a-readme-refused",
        "watch-link-without-a-subject",
    ],
)
def test_texts_that_contradict_the_writing_are_refused(writing, detail):
    failure = ask_and_fail(answer(content=body(report_with_writing(**writing))))

    assert str(failure).startswith(f"ai_api_invalid_response, HTTP 200, {detail}")


def test_a_sector_without_a_topic_is_refused():
    report = report_with_writing()
    report["chosen"][0]["facts"]["topics"] = []
    report["repositories"][0]["facts"]["topics"] = []

    failure = ask_and_fail(answer(content=body(report)))

    assert str(failure).startswith(
        "ai_api_invalid_response, HTTP 200, chosen.0.texts.sector (without_a_topic)"
    )


@pytest.mark.parametrize(
    ("sector", "detail"),
    [
        ("trop long " * 20, "too_long"),
        ("", "string_too_short"),
        ("Outil" + chr(0x200B) + "secret", "value_error"),
        ("Outil" + chr(0xE000) + "secret", "value_error"),
        ("Outil" + chr(0x0378) + "secret", "value_error"),
        ("Outil" + chr(0xE0041) + "secret", "value_error"),
    ],
    ids=["too-long", "empty", "zero-width-space", "private-use", "unassigned", "tag"],
)
def test_a_text_beyond_its_bound_or_with_a_hidden_character_is_refused_never_quoted(
    sector, detail
):
    assert len("trop long " * 20) > TREND_SECTOR_MAX_CHARS
    failure = ask_and_fail(
        answer(content=body(report_with_writing(texts=TEXTS | {"sector": sector})))
    )

    assert str(failure).startswith(
        f"ai_api_invalid_response, HTTP 200, chosen.0.texts.sector ({detail})"
    )
    assert "secret" not in str(failure)
    assert "trop long" not in str(failure)


def test_the_joiner_of_an_emoji_is_read():
    developer = chr(0x1F469) + chr(0x200D) + chr(0x1F4BB)
    response, _ = ask(
        answer(
            content=body(
                report_with_writing(texts=TEXTS | {"sector": f"Outil {developer}."})
            )
        )
    )

    assert response.chosen[0].texts.sector == f"Outil {developer}."
