"""The client of the trend reports: its request, and the response it accepts, each 200 made by the
schema of the AI API, which ties the client to the contract, then changed to break one check."""

import json
from datetime import date

import httpx2
import pytest
from post.test_ai_api_client import (
    OTHER_REQUEST_ID,
    REQUEST_ID,
    SETTINGS,
    TEST_API_KEY,
    answer,
)

from k_b.ai_api.schemas.trend_report_schema import (
    TrajectoryPointSchema,
    TrendPeriodSchema,
    TrendReportSchema,
    TrendRepositorySchema,
)
from k_b.post.ai_api_client import (
    AiApiError,
    build_ai_api_client,
    read_ai_api_client_settings_or_refusal,
)
from k_b.post.trend_report_client import (
    TREND_REPORT_KEY_VARIABLE,
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
)


def make_report(**changes):
    """A response of POST /trend-reports after a previous report, as JSON to change."""
    report = TrendReportSchema(
        request_id=REQUEST_ID,
        model=None,
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
