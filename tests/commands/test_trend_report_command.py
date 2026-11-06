"""kb trend-report: the checks before the request, the report written, then its entry in the
register; never a name of a repository in the log nor in the summary."""

import json
import re
import secrets
import signal
from datetime import UTC, datetime
from functools import partial

import httpx2
import pytest
from commands.cli_helpers import LOG_LINE_DATE, list_hidden_files, list_sheets
from post.test_ai_api_client import (
    REQUEST_ID,
    TEST_API_KEY,
    TEST_MAX_ANSWER_BYTES,
    answer_beyond_the_bound,
    bound_answers,
)
from post.test_trend_report_client import (
    RISING_NAME,
    STEADY,
    change_period,
    make_report,
)

from k_b import cli
from k_b.commands import trend_report_command
from k_b.post import trend_report_registry, vault_files
from k_b.post.ai_api_client import build_ai_api_client

# The instant of the run: its day names the report.
GENERATED = datetime(2026, 11, 1, 10, 0, 5, tzinfo=UTC)
SHEET = "veille/tendances/2026-11-01.md"
PREVIOUS_ENTRY = {
    "first_window": "2026-10-24",
    "last_window": "2026-10-27",
    "file": "veille/tendances/2026-10-28.md",
    "written_at": "2026-10-28T09:30:00Z",
    "request_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
    "model": None,
    "choice_made": False,
}
NAMES = (RISING_NAME, "steady/tool")


def first_report(**changes):
    return change_period(
        make_report(repositories=[STEADY.model_dump(mode="json")]),
        first_report=True,
        new_evaluated=False,
        **changes,
    )


@pytest.fixture
def trend_environment(monkeypatch, data_and_vault_dirs):
    """kb trend-report with its key and the instant of the run."""
    monkeypatch.setenv("KB_AI_API_KEY_KB_TREND_REPORT", TEST_API_KEY)
    monkeypatch.setattr(trend_report_command, "read_now", lambda: GENERATED)
    return data_and_vault_dirs


def answer_trend_report(monkeypatch, handle):
    """The AI API of kb trend-report: handle answers each request, kept in the list returned."""
    requests = []

    def keep_and_handle(request):
        requests.append(request)
        return handle(request)

    monkeypatch.setattr(
        trend_report_command,
        "build_ai_api_client",
        partial(build_ai_api_client, transport=httpx2.MockTransport(keep_and_handle)),
    )
    return requests


def answer_with(report, status=200):
    def handle(request):
        return httpx2.Response(status, content=json.dumps(report).encode())

    return handle


def write_register(data_dir, entries):
    (data_dir / "trend_reports.json").write_text(json.dumps(entries), "utf-8")


def read_register(data_dir):
    return json.loads((data_dir / "trend_reports.json").read_text("utf-8"))


def read_kb_log(data_dir):
    return (data_dir / "logs" / "kb.log").read_text("utf-8")


def test_the_first_report_is_written_then_added_to_the_register(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    requests = answer_trend_report(monkeypatch, answer_with(first_report()))

    exit_code = cli.main(["trend-report"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    [request] = requests
    assert (request.method, request.url.path) == ("POST", "/trend-reports")
    assert json.loads(request.content) == {
        "after": None,
        "previous_first_window": None,
    }
    assert list_sheets(vault_dir) == [SHEET]
    assert read_register(data_dir) == [
        {
            "first_window": "2026-10-28",
            "last_window": "2026-10-31",
            "file": SHEET,
            "written_at": "2026-11-01T10:00:05Z",
            "request_id": REQUEST_ID,
            "model": "gpt-6-luna",
            "choice_made": True,
        }
    ]
    assert capsys.readouterr().out == (
        "\n"
        "Trend report summary\n"
        "--------------------\n"
        "Period: 2026-10-28 → 2026-10-31, 4 windows, 0 missing\n"
        "Repositories: 1 meeting a criterion, 0 dropped\n"
        f"Sheet: {SHEET}\n"
        "\n"
        "Model: gpt-6-luna\n"
        f"Request id: {REQUEST_ID}\n"
        "\n"
    )


def test_the_next_report_asks_the_windows_after_the_last_entry(
    monkeypatch, trend_environment
):
    data_dir, _ = trend_environment
    older = PREVIOUS_ENTRY | {"first_window": "2026-10-20", "last_window": "2026-10-23"}
    write_register(data_dir, [older, PREVIOUS_ENTRY])
    requests = answer_trend_report(monkeypatch, answer_with(make_report()))

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED
    assert json.loads(requests[0].content) == {
        "after": "2026-10-27",
        "previous_first_window": "2026-10-24",
    }
    register = read_register(data_dir)
    assert register[:2] == [older, PREVIOUS_ENTRY]
    assert (register[2]["first_window"], register[2]["last_window"]) == (
        "2026-10-28",
        "2026-10-31",
    )


def test_the_log_says_the_start_the_sheet_and_the_end_never_a_name(
    monkeypatch, trend_environment, capsys
):
    data_dir, _ = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    answer_trend_report(monkeypatch, answer_with(make_report()))

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED
    log = read_kb_log(data_dir)
    for line in (
        rf"^{LOG_LINE_DATE} INFO k_b\.cli: trend report started: windows after 2026-10-27$",
        rf"^{LOG_LINE_DATE} INFO k_b\.cli: sheet written: veille/tendances/2026-11-01\.md$",
        rf"^{LOG_LINE_DATE} INFO k_b\.cli: trend report finished in \d+ s$",
    ):
        assert re.search(line, log, re.MULTILINE)
    output = capsys.readouterr()
    for name in NAMES:
        assert name not in log
        assert name not in output.out
        assert name not in output.err


@pytest.mark.parametrize(
    ("content", "logged"),
    [
        (b"not json", "trend_reports.json invalid: input (json_invalid)"),
        (
            json.dumps(
                [
                    PREVIOUS_ENTRY
                    | {"first_window": "2026-10-12", "last_window": "2026-10-27"}
                ]
            ).encode(),
            "trend_reports.json invalid: 0 (value_error)",
        ),
        (
            json.dumps([PREVIOUS_ENTRY | {"windows": 4}]).encode(),
            "trend_reports.json invalid: 0.windows (extra_forbidden)",
        ),
    ],
)
def test_a_register_refused_asks_nothing_and_exits_2(
    monkeypatch, trend_environment, content, logged
):
    data_dir, vault_dir = trend_environment
    (data_dir / "trend_reports.json").write_bytes(content)
    requests = answer_trend_report(monkeypatch, answer_with(make_report()))

    assert cli.main(["trend-report"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert (data_dir / "trend_reports.json").read_bytes() == content
    assert list_sheets(vault_dir) == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: no trend report asked: {re.escape(logged)}$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )


def test_a_previous_report_of_fifteen_windows_is_asked(monkeypatch, trend_environment):
    data_dir, _ = trend_environment
    write_register(
        data_dir,
        [PREVIOUS_ENTRY | {"first_window": "2026-10-13", "last_window": "2026-10-27"}],
    )
    requests = answer_trend_report(monkeypatch, answer_with(make_report()))

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED
    assert len(requests) == 1


def test_a_report_of_the_day_asks_nothing_and_exits_2(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    requests = answer_trend_report(monkeypatch, answer_with(first_report()))
    sheet = vault_dir / SHEET
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"read by Sabine\n")

    assert cli.main(["trend-report"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert sheet.read_bytes() == b"read by Sabine\n"
    assert not (data_dir / "trend_reports.json").exists()
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: no trend report asked: sheet_exists:"
        r" veille/tendances/2026-11-01\.md is there; kb trend-report never rewrites a report$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )
    assert str(vault_dir) not in capsys.readouterr().err


def test_a_folder_linked_elsewhere_asks_nothing_and_exits_2(
    monkeypatch, trend_environment, tmp_path
):
    _, vault_dir = trend_environment
    requests = answer_trend_report(monkeypatch, answer_with(first_report()))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille").symlink_to(elsewhere, target_is_directory=True)

    assert cli.main(["trend-report"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert list(elsewhere.iterdir()) == []


def test_a_file_in_place_of_a_folder_asks_nothing_and_exits_1(
    monkeypatch, trend_environment, capsys
):
    _, vault_dir = trend_environment
    requests = answer_trend_report(monkeypatch, answer_with(first_report()))
    (vault_dir / "veille").write_bytes(b"a file\n")

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    assert requests == []
    error_output = capsys.readouterr().err
    assert "no trend report asked: NotADirectoryError (Not a directory)" in error_output
    assert str(vault_dir) not in error_output


@pytest.mark.parametrize(
    ("variable", "value", "logged"),
    [
        (
            "KB_VAULT_DIR",
            None,
            "KB_VAULT_DIR not set; the trend report is written in the vault",
        ),
        (
            "KB_AI_API_KEY_KB_TREND_REPORT",
            None,
            "KB_AI_API_KEY_KB_TREND_REPORT: not set",
        ),
        (
            "KB_AI_API_KEY_KB_TREND_REPORT",
            "short",
            "'KB_AI_API_KEY_KB_TREND_REPORT': key of 5 characters, minimum 32",
        ),
    ],
)
def test_a_setting_refused_asks_nothing_and_exits_2(
    monkeypatch, trend_environment, variable, value, logged
):
    data_dir, _ = trend_environment
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)
    requests = answer_trend_report(monkeypatch, answer_with(first_report()))

    assert cli.main(["trend-report"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: {re.escape(logged)}$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )


def test_a_vault_that_does_not_exist_creates_nothing_and_exits_2(
    monkeypatch, trend_environment, tmp_path
):
    data_dir, _ = trend_environment
    absent_vault = tmp_path / "typo"
    monkeypatch.setenv("KB_VAULT_DIR", str(absent_vault))
    requests = answer_trend_report(monkeypatch, answer_with(first_report()))

    assert cli.main(["trend-report"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert not absent_vault.exists()
    assert not (data_dir / "trend_reports.json").exists()


def test_no_new_window_writes_nothing_says_so_and_succeeds(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    empty = change_period(
        make_report(repositories=[]), windows=[], latest_window="2026-10-27"
    )
    answer_trend_report(monkeypatch, answer_with(empty))

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED
    assert list_sheets(vault_dir) == []
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    output = capsys.readouterr()
    assert output.out == (
        "\n"
        "No new window after 2026-10-27; nothing written\n"
        f"Request id: {REQUEST_ID}\n"
        "\n"
    )
    assert re.search(
        rf"^{LOG_LINE_DATE} INFO k_b\.cli: no window after 2026-10-27; nothing written$",
        output.err,
        re.MULTILINE,
    )


def test_a_base_older_than_the_register_is_a_warning_with_both_days(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    restored = change_period(
        make_report(repositories=[]), windows=[], latest_window="2026-10-25"
    )
    answer_trend_report(monkeypatch, answer_with(restored))

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED
    assert list_sheets(vault_dir) == []
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    assert re.search(
        rf"^{LOG_LINE_DATE} WARNING k_b\.cli: the latest window in the base, 2026-10-25, is"
        " before the last window of trend_reports.json, 2026-10-27; nothing written$",
        capsys.readouterr().err,
        re.MULTILINE,
    )


def test_a_base_without_any_window_writes_nothing_and_succeeds(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    empty = change_period(
        make_report(repositories=[]),
        first_report=True,
        new_evaluated=False,
        windows=[],
        latest_window=None,
    )
    answer_trend_report(monkeypatch, answer_with(empty))

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED
    assert list_sheets(vault_dir) == []
    assert not (data_dir / "trend_reports.json").exists()
    output = capsys.readouterr()
    assert "\nNo GH Archive window in the base; nothing written\n" in output.out
    assert re.search(
        rf"^{LOG_LINE_DATE} WARNING k_b\.cli: no GH Archive window in the base;"
        " nothing written$",
        output.err,
        re.MULTILINE,
    )


def test_a_report_not_written_leaves_the_register_and_exits_1(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    answer_trend_report(monkeypatch, answer_with(make_report()))

    def refuse(path, content):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(vault_files, "write_file_atomically", refuse)

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    output = capsys.readouterr()
    assert output.out == ""
    assert (
        "trend report not written: PermissionError (Permission denied),"
        f" request_id {REQUEST_ID}"
    ) in output.err
    assert str(vault_dir) not in output.err


def test_a_register_not_updated_keeps_the_report_and_exits_1(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    answer_trend_report(monkeypatch, answer_with(make_report()))

    def refuse(path, content):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(trend_report_registry, "write_file_atomically", refuse)

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == [SHEET]
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    error_output = capsys.readouterr().err
    assert (
        "sheet written, trend_reports.json not updated: PermissionError (Permission"
        f" denied), request_id {REQUEST_ID}; the next report covers these windows again"
    ) in error_output
    assert str(data_dir) not in error_output


def test_an_entry_the_register_would_refuse_writes_nothing_and_exits_1(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    # No register to read: the check refuses the new entry alone.
    answer_trend_report(monkeypatch, answer_with(first_report()))
    monkeypatch.setattr(
        trend_report_registry, "has_too_many_windows", lambda first, last: True
    )

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []
    assert not (data_dir / "trend_reports.json").exists()
    error_output = capsys.readouterr().err
    assert (
        "trend report not written: its entry of trend_reports.json is invalid: input"
        f" (value_error), request_id {REQUEST_ID}"
    ) in error_output
    assert "Traceback" not in error_output
    assert "2026-10-28" not in error_output


def test_a_sigterm_after_the_report_keeps_it_and_leaves_the_register(
    monkeypatch, trend_environment, sigterm_handler_of_the_test
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    answer_trend_report(monkeypatch, answer_with(make_report()))

    def receive_sigterm(*arguments):
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(trend_report_command, "append_trend_report", receive_sigterm)

    assert cli.main(["trend-report"]) == cli.ExitCode.STOPPED_BY_SIGTERM
    assert list_sheets(vault_dir) == [SHEET]
    assert list_hidden_files(vault_dir) == []
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def test_a_refused_key_names_its_variable_never_the_key(
    monkeypatch, trend_environment, capsys
):
    data_dir, _ = trend_environment
    answer_trend_report(
        monkeypatch,
        lambda request: httpx2.Response(401, content=b'{"error": "invalid_api_key"}'),
    )

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    error_output = capsys.readouterr().err
    assert (
        "trend report not received: ai_api_unauthorized, HTTP 401, error invalid_api_key;"
        " the AI API refused the key of KB_AI_API_KEY_KB_TREND_REPORT"
    ) in error_output
    assert TEST_API_KEY not in error_output
    assert not (data_dir / "trend_reports.json").exists()


def test_a_response_refused_writes_nothing_and_never_quotes_a_name(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    # RISING meets new, which is not evaluated here.
    answer_trend_report(
        monkeypatch, answer_with(change_period(make_report(), new_evaluated=False))
    )

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    output = capsys.readouterr()
    assert "repositories.0.criteria (new_not_evaluated)" in output.err
    for name in NAMES:
        assert name not in output.err
        assert name not in read_kb_log(data_dir)


def test_an_answer_beyond_its_bound_writes_nothing_never_shows_nor_logs_it(
    monkeypatch, trend_environment, capsys
):
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    bound_answers(monkeypatch)
    marker = secrets.token_hex(16)
    answer_trend_report(monkeypatch, answer_beyond_the_bound(marker))

    assert cli.main(["trend-report"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []
    assert read_register(data_dir) == [PREVIOUS_ENTRY]
    output = capsys.readouterr()
    assert (
        "trend report not received: ai_api_invalid_response, HTTP 200,"
        f" response larger than {TEST_MAX_ANSWER_BYTES} bytes\n"
    ) in output.err
    for shown in (output.out, output.err, read_kb_log(data_dir)):
        assert marker not in shown


def test_a_choice_that_failed_writes_the_factual_report_and_the_register_notes_it(
    monkeypatch, trend_environment, capsys
):
    """The period moves on (decision of Sabine, 2026-10-29); the failure is a warning in the
    log, the standard output unchanged."""
    data_dir, vault_dir = trend_environment
    write_register(data_dir, [PREVIOUS_ENTRY])
    answer_trend_report(
        monkeypatch,
        answer_with(make_report(model=None, choice_failure="llm_unavailable")),
    )

    assert cli.main(["trend-report"]) == cli.ExitCode.SUCCEEDED

    assert list_sheets(vault_dir) == [SHEET]
    sheet = (vault_dir / SHEET).read_text("utf-8")
    assert "Choix non fait : le modèle est indisponible." in sheet
    [_, entry] = read_register(data_dir)
    assert (entry["model"], entry["choice_made"]) == (None, False)
    assert entry["last_window"] == "2026-10-31"
    log = read_kb_log(data_dir)
    assert re.search(
        rf"^{LOG_LINE_DATE} WARNING k_b\.cli: choice of the model not made:"
        rf" llm_unavailable, request_id {REQUEST_ID}$",
        log,
        re.MULTILINE,
    )
    assert "Model: none\n" in capsys.readouterr().out
    for name in NAMES:
        assert name not in log
