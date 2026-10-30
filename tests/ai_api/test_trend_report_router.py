"""POST /trend-reports on a simulated data API that counts its requests, and on the data API of
the test base (docs/tendances.md)."""

import logging
import secrets
from datetime import date, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import SecretStr

from k_b.ai_api.app import create_app
from k_b.ai_api.connectors.data_api_settings import DataApiSettings
from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.dependencies import open_data_api_client, open_llm_client
from k_b.ai_api.observability.metric_instruments import ModelMetrics
from k_b.ai_api.routers import trend_report_router
from k_b.core.config import (
    GH_ARCHIVE_MAX_CATCH_UP_WINDOWS,
    GH_ARCHIVE_TOP_SIZE,
    LLM_REPLAY_BASE_URL,
    DigestSubject,
)
from k_b.data_api.app import create_app as create_data_app

# Made for the test: never a real key.
CLIENT_KEY = secrets.token_urlsafe(32)
AUTHORIZATION = {"Authorization": f"Bearer {CLIENT_KEY}"}
LATEST = date(2026, 10, 31)
FIRST_REPORT = {"after": None, "previous_first_window": None}
# The repository each test follows: 12, 7, 4 then 2 over the 4 windows of a first report.
RISING_ID = 4_242
RISING_NAME = "owner/rising-repository"
RISING_RANKS = {
    LATEST - timedelta(days=3): 12,
    LATEST - timedelta(days=2): 7,
    LATEST - timedelta(days=1): 4,
    LATEST: 2,
}


def day(offset):
    """The day offset days before LATEST."""
    return LATEST - timedelta(days=offset)


def text(value):
    return value.isoformat()


def build_window(window_end, ranks=None, extra=()):
    """The body of GET /trends: a full top by stars, and the repositories of ranks at their rank."""
    ranks = RISING_RANKS if ranks is None else ranks
    rows = [
        {
            "repository_id": 1_000 + k,
            "repository_name": f"filler/repo-{k}",
            "stars_gained": 1_000 - 10 * k,
            "forks_gained": 3,
        }
        for k in range(GH_ARCHIVE_TOP_SIZE)
    ]
    rank = ranks.get(window_end)
    if rank is not None:
        rows.insert(
            rank - 1,
            {
                "repository_id": RISING_ID,
                "repository_name": RISING_NAME,
                "stars_gained": 1_005 - 10 * (rank - 1),
                "forks_gained": 1,
            },
        )
    return {"window_end": text(window_end), "trends": [*rows, *extra]}


class SimulatedDataApi:
    """GET /trends over the windows given, keeping each request."""

    def __init__(self, windows):
        self.windows = windows
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        asked = request.url.params.get("window_end")
        if asked is None:
            asked = max(self.windows, default=None)
        else:
            asked = date.fromisoformat(asked)
        if asked not in self.windows:
            return httpx2.Response(404, json={"error": "trend_window_not_found"})
        return httpx2.Response(200, json=self.windows[asked])

    def client(self):
        return httpx2.Client(
            base_url="http://localhost", transport=httpx2.MockTransport(self.handle)
        )

    @property
    def days_asked(self):
        return [request.url.params.get("window_end") for request in self.requests]


def simulate(days, ranks=None, extra=()):
    return SimulatedDataApi({end: build_window(end, ranks, extra) for end in days})


def make_app(recorded_traces):
    app = create_app(
        {"TERMINAL": SecretStr(CLIENT_KEY)},
        LlmSettings(
            provider="replay",
            base_url=LLM_REPLAY_BASE_URL,
            model="replay",
            api_key=None,
            reasoning_effort=None,
            replay_steps=(),
        ),
        DataApiSettings(
            base_url="http://localhost", api_key=SecretStr(secrets.token_urlsafe(32))
        ),
        (DigestSubject("subject_of_the_test", "défini par le test"),),
        3,
        ModelMetrics(
            MeterProvider(
                metric_readers=[InMemoryMetricReader()], shutdown_on_exit=False
            )
        ),
        recorded_traces.trace_export,
    )

    def fail_the_test():
        raise AssertionError("a client of the model was opened")

    app.dependency_overrides[open_llm_client] = fail_the_test
    return app


@pytest.fixture
def make_ai_api(recorded_traces):
    """A client of the AI API reading this data API."""

    def make(data_api):
        app = make_app(recorded_traces)
        http_client = (
            data_api.client() if isinstance(data_api, SimulatedDataApi) else data_api
        )
        app.dependency_overrides[open_data_api_client] = lambda: http_client
        return TestClient(app, raise_server_exceptions=False)

    return make


def post_trend_reports(client, body=FIRST_REPORT, headers=AUTHORIZATION):
    return client.post("/trend-reports", json=body, headers=headers)


def find_rising(body):
    """The repository the test follows; the fillers, in every top, are durable."""
    [repository] = [r for r in body["repositories"] if r["repository_id"] == RISING_ID]
    return repository


def test_the_first_report_reads_the_last_four_windows_without_new(make_ai_api):
    data_api = simulate([day(offset) for offset in range(8)])

    response = post_trend_reports(make_ai_api(data_api))

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["model"] is None
    assert body["period"] == {
        "first_report": True,
        "windows": [text(day(offset)) for offset in (3, 2, 1, 0)],
        "missing_windows": [],
        "windows_capped": False,
        "new_evaluated": False,
        "latest_window": text(LATEST),
    }
    assert find_rising(body) == {
        "repository_id": RISING_ID,
        "repository_name": RISING_NAME,
        "criteria": ["durable", "accelerating"],
        "best_rank": 2,
        "trajectory": [
            {
                "window_end": text(end),
                "state": "top",
                "rank": rank,
                "stars_gained": 1_005 - 10 * (rank - 1),
            }
            for end, rank in RISING_RANKS.items()
        ],
    }
    assert body["repositories_dropped"] == 0
    # The latest, then the 2 windows before the period and the 3 others of the period, once each.
    assert data_api.days_asked == [
        None,
        *(text(day(offset)) for offset in (5, 4, 3, 2, 1)),
    ]


def test_a_report_reads_the_windows_after_the_previous_one(make_ai_api):
    data_api = simulate([day(offset) for offset in range(10)])
    previous = {"after": text(day(2)), "previous_first_window": text(day(5))}

    body = post_trend_reports(make_ai_api(data_api), previous).json()

    assert body["period"]["windows"] == [text(day(1)), text(day(0))]
    assert body["period"]["first_report"] is False
    assert body["period"]["new_evaluated"] is True
    # The previous report and the 2 windows before the period, which it holds, read once.
    assert data_api.days_asked == [
        None,
        *(text(day(offset)) for offset in (5, 4, 3, 2, 1)),
    ]


def test_new_is_a_repository_in_no_top_of_the_previous_report(make_ai_api):
    ranks = {day(1): 9, day(0): 3}
    data_api = simulate([day(offset) for offset in range(6)], ranks)
    previous = {"after": text(day(2)), "previous_first_window": text(day(5))}

    body = post_trend_reports(make_ai_api(data_api), previous).json()

    assert find_rising(body)["criteria"] == ["new", "accelerating"]


def test_without_any_window_of_the_previous_report_new_is_not_evaluated(make_ai_api):
    ranks = {day(1): 9, day(0): 3}
    data_api = simulate([day(1), day(0)], ranks)
    previous = {"after": text(day(2)), "previous_first_window": text(day(5))}

    body = post_trend_reports(make_ai_api(data_api), previous).json()

    assert body["period"]["new_evaluated"] is False
    assert find_rising(body)["criteria"] == ["accelerating"]


def test_beyond_the_cap_the_most_recent_windows_are_kept(make_ai_api):
    data_api = simulate([day(offset) for offset in range(25)])
    after = day(GH_ARCHIVE_MAX_CATCH_UP_WINDOWS + 1)
    previous = {"after": text(after), "previous_first_window": text(after)}

    period = post_trend_reports(make_ai_api(data_api), previous).json()["period"]

    assert period["windows_capped"] is True
    assert len(period["windows"]) == GH_ARCHIVE_MAX_CATCH_UP_WINDOWS
    assert period["windows"][0] == text(day(GH_ARCHIVE_MAX_CATCH_UP_WINDOWS - 1))


def test_up_to_the_cap_no_window_is_left_out(make_ai_api):
    data_api = simulate([day(offset) for offset in range(25)])
    after = day(GH_ARCHIVE_MAX_CATCH_UP_WINDOWS)
    previous = {"after": text(after), "previous_first_window": text(after)}

    period = post_trend_reports(make_ai_api(data_api), previous).json()["period"]

    assert period["windows_capped"] is False
    assert len(period["windows"]) == GH_ARCHIVE_MAX_CATCH_UP_WINDOWS


@pytest.mark.parametrize(
    "after", [LATEST, LATEST + timedelta(days=4)], ids=["latest", "later"]
)
def test_no_window_after_the_previous_report_reads_nothing_more(make_ai_api, after):
    data_api = simulate([day(offset) for offset in range(4)])
    previous = {"after": text(after), "previous_first_window": text(after)}

    body = post_trend_reports(make_ai_api(data_api), previous).json()

    assert body["period"]["windows"] == []
    assert body["period"]["latest_window"] == text(LATEST)
    assert body["repositories"] == []
    assert data_api.days_asked == [None]


def test_a_base_without_any_window_gives_an_empty_period(make_ai_api):
    data_api = SimulatedDataApi({})

    body = post_trend_reports(make_ai_api(data_api)).json()

    assert body["period"]["windows"] == []
    assert body["period"]["latest_window"] is None
    assert data_api.days_asked == [None]


def test_a_missing_window_is_listed_and_shown_in_the_trajectory(make_ai_api):
    data_api = simulate([day(3), day(1), day(0)])

    body = post_trend_reports(make_ai_api(data_api)).json()

    assert body["period"]["missing_windows"] == [text(day(2))]
    assert [point["state"] for point in find_rising(body)["trajectory"]] == [
        "top",
        "missing",
        "top",
        "top",
    ]


def test_a_repository_whose_name_would_go_up_a_path_is_dropped_and_counted(
    make_ai_api,
):
    unsafe = {
        "repository_id": 99,
        "repository_name": "owner/..",
        "stars_gained": 5_000,
        "forks_gained": 0,
    }
    data_api = simulate([day(offset) for offset in range(4)], extra=[unsafe])

    body = post_trend_reports(make_ai_api(data_api)).json()

    reported = [r["repository_id"] for r in body["repositories"]]
    assert RISING_ID in reported
    assert 99 not in reported
    assert body["repositories_dropped"] == 1


def test_the_report_of_the_test_base_reads_its_two_windows(make_ai_api, items_database):
    key = secrets.token_urlsafe(32)
    with TestClient(
        create_data_app(items_database, {"AI_DIGEST": SecretStr(key)}),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {key}"},
    ) as data_api:
        body = post_trend_reports(make_ai_api(data_api)).json()

    assert body["period"]["windows"] == [
        "2026-10-07",
        "2026-10-08",
        "2026-10-09",
        "2026-10-10",
    ]
    assert body["period"]["missing_windows"] == ["2026-10-07", "2026-10-08"]
    # Ranks 1 and 2 on both windows, which share a day: no criterion.
    assert body["repositories"] == []


@pytest.mark.parametrize(
    "content",
    [
        {"after": "2026-10-30", "previous_first_window": None},
        {"after": None, "previous_first_window": "2026-10-30"},
        {"after": "2026-10-27", "previous_first_window": "2026-10-30"},
        {"after": "2026-10-30", "previous_first_window": "2026-10-15"},
        {**FIRST_REPORT, "field\nof the client": 1},
        {"after": None},
        {},
        [None, None],
        None,
    ],
    ids=[
        "previous-first-window-null",
        "after-null",
        "inverted",
        "sixteen-windows",
        "extra-field",
        "missing-field",
        "empty",
        "not-an-object",
        "no-body",
    ],
)
def test_a_malformed_request_is_refused_422_on_its_body_before_any_reading(
    make_ai_api, content
):
    data_api = simulate([LATEST])

    response = make_ai_api(data_api).post(
        "/trend-reports",
        headers=AUTHORIZATION,
        **({} if content is None else {"json": content}),
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_parameter"
    assert data_api.requests == []


@pytest.mark.parametrize(
    "after",
    ["2026-10-30T00:00:00Z", "30/10/2026", "2026-02-30", 1_761_782_400, True],
)
def test_a_day_not_written_yyyy_mm_dd_is_refused_422_by_its_name(make_ai_api, after):
    data_api = simulate([LATEST])

    response = post_trend_reports(
        make_ai_api(data_api), {"after": after, "previous_first_window": "2026-10-29"}
    )

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_parameter", "parameters": ["after"]}
    assert data_api.requests == []


def test_a_previous_report_of_the_most_windows_is_accepted(make_ai_api):
    first = LATEST - timedelta(days=GH_ARCHIVE_MAX_CATCH_UP_WINDOWS - 1)
    previous = {"after": text(LATEST), "previous_first_window": text(first)}

    response = post_trend_reports(make_ai_api(simulate([LATEST])), previous)

    assert response.status_code == 200


def test_a_request_without_a_valid_key_is_refused_before_any_reading(make_ai_api):
    data_api = simulate([LATEST])

    response = post_trend_reports(make_ai_api(data_api), headers={})

    assert response.status_code == 401
    assert data_api.requests == []


def raise_timeout(request):
    raise httpx2.ReadTimeout("timeout of the test", request=request)


def answer_on_the_second(response):
    """The latest window, then this response."""
    data_api = simulate([day(offset) for offset in range(4)])

    def handle(request):
        if data_api.requests:
            data_api.requests.append(request)
            return response(request)
        return data_api.handle(request)

    return httpx2.Client(
        base_url="http://localhost", transport=httpx2.MockTransport(handle)
    )


@pytest.mark.parametrize(
    ("data_api_client", "status", "state"),
    [
        (
            httpx2.Client(
                base_url="http://localhost",
                transport=httpx2.MockTransport(raise_timeout),
            ),
            504,
            "data_api_timeout",
        ),
        (
            httpx2.Client(
                base_url="http://localhost",
                transport=httpx2.MockTransport(lambda request: httpx2.Response(401)),
            ),
            502,
            "data_api_unauthorized",
        ),
        (
            answer_on_the_second(
                lambda request: httpx2.Response(404, json={"error": "route_not_found"})
            ),
            502,
            "data_api_invalid_response",
        ),
    ],
    ids=["timeout", "key-refused", "route-not-found-after-the-latest"],
)
def test_a_reading_that_fails_fails_the_request_with_its_state_logged_once(
    make_ai_api, caplog, recorded_traces, data_api_client, status, state
):
    with caplog.at_level(logging.DEBUG, logger="k_b"):
        response = post_trend_reports(make_ai_api(data_api_client))

    assert response.status_code == status
    assert response.json() == {"error": state}
    request_id = response.headers["X-Request-ID"]
    [failure] = [
        r.getMessage() for r in caplog.records if r.name.startswith("k_b.ai_api")
    ]
    assert failure.startswith(f"reading of the trend windows failed: {state}")
    assert failure.endswith(f", request_id={request_id}")
    assert RISING_NAME not in caplog.text
    [step] = recorded_traces.find_spans("read_trend_windows")
    assert step.status.status_code == StatusCode.ERROR
    assert step.attributes["error.type"] == state
    [root] = recorded_traces.find_spans("POST /trend-reports")
    assert root.attributes["http.response.status_code"] == status


def test_a_report_is_a_trace_of_counts(make_ai_api, recorded_traces):
    data_api = simulate([day(offset) for offset in (5, 4, 3, 1, 0)])

    response = post_trend_reports(make_ai_api(data_api))

    reported = len(response.json()["repositories"])
    [root] = recorded_traces.find_spans("POST /trend-reports")
    assert root.kind == SpanKind.SERVER
    assert root.attributes["k_b.request_id"] == response.headers["X-Request-ID"]
    assert root.attributes["http.route"] == "/trend-reports"
    assert root.attributes["http.response.status_code"] == 200
    [step] = recorded_traces.find_spans("read_trend_windows")
    assert step.parent.span_id == root.context.span_id
    assert {
        name: value
        for name, value in step.attributes.items()
        if name.startswith("k_b.")
    } == {
        "k_b.windows.period": 4,
        "k_b.windows.read": 6,
        "k_b.windows.missing": 1,
        "k_b.windows.capped": False,
        "k_b.repositories.reported": reported,
        "k_b.repositories.dropped": 0,
    }


def list_values(recorded_traces):
    """Every value of every attribute of the spans and log records, and every body."""
    values = []
    for span in recorded_traces.spans.get_finished_spans():
        values.extend(span.attributes.values())
    for record in recorded_traces.log_records.get_finished_logs():
        values.extend(record.log_record.attributes.values())
        values.append(record.log_record.body)
    return values


def test_neither_the_traces_nor_the_logs_hold_a_repository(
    make_ai_api, recorded_traces, caplog
):
    data_api = simulate([day(offset) for offset in range(6)])

    with caplog.at_level(logging.DEBUG):
        body = post_trend_reports(make_ai_api(data_api)).json()

    assert body["repositories"]
    rows = [row for window in data_api.windows.values() for row in window["trends"]]
    names = {row["repository_name"] for row in rows}
    ids = {row["repository_id"] for row in rows}
    values = list_values(recorded_traces)
    assert values
    for value in values:
        elements = value if isinstance(value, tuple) else (value,)
        assert not any(name in str(element) for element in elements for name in names)
        # An identifier would be an attribute or an element of its own.
        assert not any(
            element in ids or element in {str(i) for i in ids} for element in elements
        ), value
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert not any(name in messages for name in names)


def test_a_response_that_fails_to_be_built_is_traced_as_a_500(
    make_ai_api, recorded_traces, monkeypatch
):
    def fail(request_id, report):
        raise ValueError("a fault of the test")

    monkeypatch.setattr(trend_report_router, "to_trend_report_schema", fail)

    response = post_trend_reports(make_ai_api(simulate([LATEST])))

    assert response.status_code == 500
    [root] = recorded_traces.find_spans("POST /trend-reports")
    assert root.attributes["http.response.status_code"] == 500
    assert root.status.status_code == StatusCode.ERROR
    assert root.attributes["error.type"] == "ValueError"
