"""kb digest: the digests asked of the AI API, the sheet of each subject written."""

import json
import logging
import os
import re
import secrets
import signal
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from functools import partial

import httpx2
import pytest
from commands.cli_helpers import (
    LOG_LINE_DATE,
    WaitLineSeen,
    list_hidden_files,
    list_sheets,
)
from post.test_ai_api_client import (
    AGENT_DIGEST,
    REQUEST_ID,
    SINCE,
    SUBJECT_NAMES,
    TEST_API_KEY,
    TEST_MAX_ANSWER_BYTES,
    UNTIL,
    answer_beyond_the_bound,
    bound_answers,
    make_response,
    to_body,
)
from post.test_digest_sheets import FIXED_WINDOW_SHEET

from k_b import cli
from k_b.ai_api.schemas.digest_schema import FailedSubjectSchema, WindowSchema
from k_b.commands import (
    digest_command,
    wait_display,
)
from k_b.commands.run_log import LOGGER_NAME
from k_b.core.config import DigestSubject
from k_b.post import vault_files
from k_b.post.ai_api_client import build_ai_api_client

# The subjects of the tests, never the real ones, as in tests/ai_api/test_digest_router.py.
TEST_DIGEST_SUBJECTS = (
    DigestSubject("security_alerts", "failles et alertes de sécurité"),
    DigestSubject("agent_tools", "outils et cadres d'agents"),
    DigestSubject("research", "articles de recherche"),
)


# The UTC day of the run, the one of the end of the window of make_response.
DIGEST_DAY = date(2026, 10, 21)


RESEARCH_DIGEST = AGENT_DIGEST.model_copy(update={"subject": "research"})


RESEARCH_FAILED = FailedSubjectSchema(
    subject="research", stage="write", error="llm_timeout"
)


@pytest.fixture
def digest_environment(monkeypatch, data_and_vault_dirs):
    """kb digest with its key, the subjects of the tests and the day of the run."""
    monkeypatch.setenv("KB_AI_API_KEY_KB_DIGEST", TEST_API_KEY)
    monkeypatch.setattr(digest_command, "DIGEST_SUBJECTS", TEST_DIGEST_SUBJECTS)
    monkeypatch.setattr(digest_command, "read_today", lambda: DIGEST_DAY)
    return data_and_vault_dirs


def answer_digests(monkeypatch, handle):
    """The AI API of kb digest: handle answers each request, kept in the list returned."""
    requests = []

    def keep_and_handle(request):
        requests.append(request)
        return handle(request)

    monkeypatch.setattr(
        digest_command,
        "build_ai_api_client",
        partial(build_ai_api_client, transport=httpx2.MockTransport(keep_and_handle)),
    )
    return requests


def answer_with(response=None, status=200, content=None, headers=None):
    def handle(request):
        body = to_body(response or make_response()) if content is None else content
        return httpx2.Response(status, content=body, headers=headers)

    return handle


def read_kb_log(data_dir):
    return (data_dir / "logs" / "kb.log").read_text("utf-8")


def test_digest_writes_the_sheet_of_each_subject_and_says_so(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    requests = answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )

    exit_code = cli.main(["digest"])

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert [(r.method, r.url.path) for r in requests] == [("POST", "/digests")]
    assert list_sheets(vault_dir) == [
        "veille/agent_tools/2026-10-21.md",
        "veille/research/2026-10-21.md",
        "veille/security_alerts/2026-10-21.md",
    ]
    assert capsys.readouterr().out == (
        "\n"
        "Digest summary\n"
        "--------------\n"
        "Window: 2026-10-18 → 2026-10-21, 4 items read\n"
        "\n"
        "subject          status                  sheet\n"
        "agent_tools      sheet written           veille/agent_tools/2026-10-21.md\n"
        "research         sheet written           veille/research/2026-10-21.md\n"
        "security_alerts  no item, sheet written  veille/security_alerts/2026-10-21.md\n"
        f"{'-' * 77}\n"
        "total            written 3, failed 0\n"
        "\n"
        "Model: gpt-6-luna\n"
        f"Request id: {REQUEST_ID}\n"
        "\n"
    )


def answer_in_turn(*responses):
    """Each request answered by the next response."""
    waiting = list(responses)

    def handle(request):
        return httpx2.Response(200, content=to_body(waiting.pop(0)))

    return handle


def sent_starts(request):
    return json.loads(request.content)["since_by_subject"]


def response_until(until, digests, since=UNTIL, **changes):
    """A response whose window ends at until, each subject starting at since, the until of
    make_response by default."""
    window = WindowSchema(
        days=3, since=since, until=until, capped_kind=None, covered_after=None
    )
    return make_response(
        digests,
        **{"window": window, "since_by_subject": dict.fromkeys(SUBJECT_NAMES, since)}
        | changes,
    )


def write_previous_sheet(vault_dir, subject, until):
    """A sheet of subject written by a run before the tests, with a fixed window."""
    sheet = vault_dir / "veille" / subject / f"{until.date().isoformat()}.md"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(
        FIXED_WINDOW_SHEET.replace(
            "2026-11-11T16:02:41Z", until.strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
        "utf-8",
    )


def test_a_first_digest_gives_no_start(monkeypatch, digest_environment):
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.SUCCEEDED
    assert sent_starts(requests[0]) == {}


def test_two_digests_follow_each_other_without_a_gap(monkeypatch, digest_environment):
    _, vault_dir = digest_environment
    next_until = UNTIL + timedelta(days=3)
    requests = answer_digests(
        monkeypatch,
        answer_in_turn(
            make_response([AGENT_DIGEST, RESEARCH_DIGEST]),
            response_until(next_until, [AGENT_DIGEST]),
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.SUCCEEDED
    monkeypatch.setattr(digest_command, "read_today", lambda: next_until.date())
    assert cli.main(["digest"]) == cli.ExitCode.SUCCEEDED

    # Each subject starts at the until of its sheet, the sheet of security_alerts, which had no
    # item, included.
    assert sent_starts(requests[1]) == {
        "security_alerts": "2026-10-21T16:30:00Z",
        "agent_tools": "2026-10-21T16:30:00Z",
        "research": "2026-10-21T16:30:00Z",
    }
    assert "veille/security_alerts/2026-10-21.md" in list_sheets(vault_dir)


def test_a_sheet_written_with_a_fixed_window_gives_the_start_of_its_subject(
    monkeypatch, digest_environment
):
    _, vault_dir = digest_environment
    write_previous_sheet(
        vault_dir, "research", datetime(2026, 10, 18, 10, 0, 7, tzinfo=UTC)
    )
    requests = answer_digests(monkeypatch, answer_with(status=503))

    cli.main(["digest"])

    assert sent_starts(requests[0]) == {"research": "2026-10-18T10:00:07Z"}


def test_a_failed_subject_keeps_its_start_for_the_next_digest(
    monkeypatch, digest_environment
):
    _, vault_dir = digest_environment
    before = datetime(2026, 10, 18, 10, 0, 7, tzinfo=UTC)
    write_previous_sheet(vault_dir, "research", before)
    next_until = UNTIL + timedelta(days=3)
    requests = answer_digests(
        monkeypatch,
        answer_in_turn(
            make_response(
                [AGENT_DIGEST],
                [RESEARCH_FAILED],
                since_by_subject=dict.fromkeys(SUBJECT_NAMES, SINCE)
                | {"research": before},
            ),
            response_until(
                next_until,
                [AGENT_DIGEST, RESEARCH_DIGEST],
                since=before,
                since_by_subject=dict.fromkeys(SUBJECT_NAMES, UNTIL)
                | {"research": before},
            ),
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.PARTIAL_FAILURE
    monkeypatch.setattr(digest_command, "read_today", lambda: next_until.date())
    cli.main(["digest"])

    assert sent_starts(requests[1])["research"] == "2026-10-18T10:00:07Z"
    assert sent_starts(requests[1])["agent_tools"] == "2026-10-21T16:30:00Z"


@pytest.mark.parametrize(
    "content",
    [
        FIXED_WINDOW_SHEET.replace("until: 2026-11-11T16:02:41Z\n", ""),
        FIXED_WINDOW_SHEET.replace("2026-11-11T16:02:41Z", "2099-01-01T00:00:00Z"),
    ],
    ids=["no-until", "until-in-the-future"],
)
def test_a_previous_sheet_without_a_valid_until_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, content
):
    data_dir, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    sheet = vault_dir / "veille" / "research" / "2026-10-18.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_text(content, "utf-8")

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: no digest asked: previous_sheet_invalid:"
        r" veille/research/2026-10-18\.md",
        read_kb_log(data_dir),
        re.MULTILINE,
    )


def test_a_start_brought_to_the_bound_is_logged_with_its_subject(
    monkeypatch, digest_environment
):
    data_dir, vault_dir = digest_environment
    write_previous_sheet(
        vault_dir, "research", datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    )
    answer_digests(monkeypatch, answer_with(make_response()))

    cli.main(["digest"])

    assert re.search(
        rf"^{LOG_LINE_DATE} WARNING k_b\.cli: research: start 2026-09-01T10:00:00Z"
        r" brought to 2026-10-18T16:30:00Z, the bound of 14 days$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )


def test_a_response_whose_start_precedes_the_start_sent_writes_no_sheet(
    monkeypatch, digest_environment
):
    _, vault_dir = digest_environment
    write_previous_sheet(
        vault_dir, "research", datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)
    )
    answer_digests(monkeypatch, answer_with(make_response()))

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == ["veille/research/2026-10-19.md"]


def test_digest_logs_its_start_and_its_end_with_the_duration(
    monkeypatch, digest_environment, capsys
):
    data_dir, _ = digest_environment
    answer_digests(monkeypatch, answer_with(make_response([AGENT_DIGEST])))

    assert cli.main(["digest"]) == cli.ExitCode.SUCCEEDED
    started = rf"^{LOG_LINE_DATE} INFO k_b\.cli: digest started: 3 subjects asked$"
    finished = rf"^{LOG_LINE_DATE} INFO k_b\.cli: digest finished in \d+ s$"
    err = capsys.readouterr().err
    for line in (started, finished):
        assert re.search(line, err, re.MULTILINE)
        assert re.search(line, read_kb_log(data_dir), re.MULTILINE)


def test_digest_without_items_writes_the_sheet_of_each_subject_and_succeeds(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(monkeypatch, answer_with(make_response([])))

    assert cli.main(["digest"]) == cli.ExitCode.SUCCEEDED
    output = capsys.readouterr().out
    assert (
        "research         no item, sheet written  veille/research/2026-10-21.md\n"
        in (output)
    )
    assert "total            written 3, failed 0\n" in output
    assert list_sheets(vault_dir) == [
        "veille/agent_tools/2026-10-21.md",
        "veille/research/2026-10-21.md",
        "veille/security_alerts/2026-10-21.md",
    ]


def test_digest_with_a_sheet_of_the_day_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys
):
    data_dir, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    sheet = vault_dir / "veille" / "research" / "2026-10-21.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"read by Sabine\n")

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert sheet.read_bytes() == b"read by Sabine\n"
    assert list_sheets(vault_dir) == ["veille/research/2026-10-21.md"]
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: no digest asked: sheet_exists:"
        r" veille/research/2026-10-21\.md is there; kb digest never rewrites a sheet$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert str(vault_dir) not in output.err


def test_digest_with_a_folder_linked_elsewhere_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, tmp_path
):
    _, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (vault_dir / "veille").symlink_to(elsewhere, target_is_directory=True)

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert list(elsewhere.iterdir()) == []


def test_digest_with_a_file_in_place_of_a_folder_asks_nothing_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    requests = answer_digests(monkeypatch, answer_with())
    (vault_dir / "veille").write_bytes(b"a file\n")

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert requests == []
    error_output = capsys.readouterr().err
    assert "no digest asked: NotADirectoryError (Not a directory)" in error_output
    assert str(vault_dir) not in error_output


@pytest.mark.parametrize("vault_dir_variable", [None, ""])
def test_digest_without_kb_vault_dir_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys, vault_dir_variable
):
    data_dir, _ = digest_environment
    if vault_dir_variable is None:
        monkeypatch.delenv("KB_VAULT_DIR")
    else:
        monkeypatch.setenv("KB_VAULT_DIR", vault_dir_variable)
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: KB_VAULT_DIR not set; the digests are written"
        " in the vault$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )


def test_digest_with_a_vault_that_does_not_exist_creates_no_folder_and_exits_2(
    monkeypatch, digest_environment, tmp_path, capsys
):
    absent_vault = tmp_path / "typo"
    monkeypatch.setenv("KB_VAULT_DIR", str(absent_vault))
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert not absent_vault.exists()
    error_output = capsys.readouterr().err
    assert "KB_VAULT_DIR is not an existing directory; no folder is created" in (
        error_output
    )
    assert str(absent_vault) not in error_output


def test_digest_without_its_key_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys
):
    monkeypatch.delenv("KB_AI_API_KEY_KB_DIGEST")
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert "ERROR k_b.cli: KB_AI_API_KEY_KB_DIGEST: not set" in capsys.readouterr().err


def test_digest_with_the_ai_api_in_http_outside_the_machine_asks_nothing_and_exits_2(
    monkeypatch, digest_environment, capsys
):
    monkeypatch.setenv("KB_AI_API_URL", "http://api-ia:8001")
    requests = answer_digests(monkeypatch, answer_with())

    assert cli.main(["digest"]) == cli.ExitCode.NOT_STARTED
    assert requests == []
    assert (
        "ERROR k_b.cli: KB_AI_API_URL: https required; http only to the machine (127.0.0.1 or localhost) or, in the sandbox, a compose service (api-donnees or api-ia)"
        in capsys.readouterr().err
    )


def test_digest_without_the_ai_api_writes_nothing_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    data_dir, vault_dir = digest_environment

    def refuse_the_connection(request):
        raise httpx2.ConnectError("refused", request=request)

    answer_digests(monkeypatch, refuse_the_connection)

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    assert re.search(
        rf"^{LOG_LINE_DATE} ERROR k_b\.cli: digests not received: ai_api_unavailable$",
        read_kb_log(data_dir),
        re.MULTILINE,
    )
    assert capsys.readouterr().out == ""


def test_digest_with_a_refused_key_writes_nothing_names_its_variable_never_the_key(
    monkeypatch, digest_environment, capsys
):
    """The request went out: 1, as a source that answers 401 to kb collect."""
    data_dir, vault_dir = digest_environment
    answer_digests(
        monkeypatch,
        answer_with(
            status=401,
            content=b'{"error": "invalid_api_key"}',
            headers={"X-Request-ID": REQUEST_ID, "WWW-Authenticate": "Bearer"},
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    output = capsys.readouterr()
    assert (
        "digests not received: ai_api_unauthorized, HTTP 401, error invalid_api_key,"
        f" X-Request-ID {REQUEST_ID}; the AI API refused the key of KB_AI_API_KEY_KB_DIGEST"
    ) in output.err
    log = read_kb_log(data_dir)
    for text in (output.out, output.err, log):
        assert TEST_API_KEY not in text


def test_digest_refused_on_its_route_names_the_variable_of_its_key_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch,
        answer_with(
            status=403,
            content=b'{"error": "client_not_allowed"}',
            headers={"X-Request-ID": REQUEST_ID},
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    assert (
        "digests not received: ai_api_forbidden, HTTP 403, error client_not_allowed,"
        f" X-Request-ID {REQUEST_ID}; the AI API does not open this route to the client"
        " of KB_AI_API_KEY_KB_DIGEST"
    ) in capsys.readouterr().err


def test_digest_while_another_runs_exits_1_with_the_wait_and_no_remedy(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch,
        answer_with(
            status=429,
            content=b'{"error": "request_already_running"}',
            headers={"X-Request-ID": REQUEST_ID, "Retry-After": "200"},
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    error_output = capsys.readouterr().err
    assert (
        "digests not received: ai_api_rate_limited, HTTP 429, error request_already_running,"
        f" X-Request-ID {REQUEST_ID}, Retry-After 200"
    ) in error_output
    assert "KB_AI_API_KEY_KB_DIGEST" not in error_output


def test_digest_on_a_failure_of_the_ai_api_exits_1_at_once_with_its_retry_after(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    requests = answer_digests(
        monkeypatch,
        answer_with(
            status=503,
            content=b'{"error": "llm_rate_limited"}',
            headers={"X-Request-ID": REQUEST_ID, "Retry-After": "20"},
        ),
    )

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert len(requests) == 1
    assert list(vault_dir.iterdir()) == []
    assert (
        "digests not received: ai_api_failed, HTTP 503, error llm_rate_limited,"
        f" X-Request-ID {REQUEST_ID}, Retry-After 20\n"
    ) in capsys.readouterr().err


def test_digest_on_a_response_out_of_the_schema_writes_nothing_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    response = make_response([AGENT_DIGEST.model_copy(update={"subject": "tops"})])
    answer_digests(monkeypatch, answer_with(response))

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    assert (
        "digests not received: ai_api_invalid_response, HTTP 200,"
        f" digests.0.subject (subject_not_listed), request_id {REQUEST_ID}\n"
    ) in capsys.readouterr().err


def test_digest_on_an_answer_beyond_its_bound_never_shows_nor_logs_it_and_exits_1(
    monkeypatch, digest_environment, capsys
):
    data_dir, vault_dir = digest_environment
    bound_answers(monkeypatch)
    marker = secrets.token_hex(16)
    answer_digests(monkeypatch, answer_beyond_the_bound(marker))

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list(vault_dir.iterdir()) == []
    output = capsys.readouterr()
    assert (
        "digests not received: ai_api_invalid_response, HTTP 200,"
        f" response larger than {TEST_MAX_ANSWER_BYTES} bytes\n"
    ) in output.err
    for shown in (output.out, output.err, read_kb_log(data_dir)):
        assert marker not in shown


def test_digest_with_failed_subjects_writes_the_others_names_them_and_exits_4(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST], [RESEARCH_FAILED]))
    )

    assert cli.main(["digest"]) == cli.ExitCode.PARTIAL_FAILURE
    assert list_sheets(vault_dir) == [
        "veille/agent_tools/2026-10-21.md",
        "veille/security_alerts/2026-10-21.md",
    ]
    output = capsys.readouterr()
    assert "ERROR k_b.cli: research: digest failed: llm_timeout at the stage write" in (
        output.err
    )
    assert (
        "subject          status                  sheet\n"
        "agent_tools      sheet written           veille/agent_tools/2026-10-21.md\n"
        "security_alerts  no item, sheet written  veille/security_alerts/2026-10-21.md\n"
        "research         digest failed\n"
    ) in output.out
    assert "total            written 2, failed 1\n" in output.out


def test_digest_with_failed_subjects_only_exits_1(monkeypatch, digest_environment):
    _, vault_dir = digest_environment
    each_failed = [
        RESEARCH_FAILED.model_copy(update={"subject": subject})
        for subject in SUBJECT_NAMES
    ]
    answer_digests(monkeypatch, answer_with(make_response([], each_failed)))

    assert cli.main(["digest"]) == cli.ExitCode.FAILED
    assert list_sheets(vault_dir) == []


def test_a_sheet_not_written_exits_4_and_the_other_sheet_is_written(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )
    write_file_atomically = vault_files.write_file_atomically

    def refuse_the_agent_tools(path, content, **options):
        if "agent_tools" in path.parts:
            raise PermissionError(13, "Permission denied", str(path))
        write_file_atomically(path, content, **options)

    monkeypatch.setattr(vault_files, "write_file_atomically", refuse_the_agent_tools)

    assert cli.main(["digest"]) == cli.ExitCode.PARTIAL_FAILURE
    assert list_sheets(vault_dir) == [
        "veille/research/2026-10-21.md",
        "veille/security_alerts/2026-10-21.md",
    ]
    error_output = capsys.readouterr().err
    assert (
        "agent_tools: sheet not written: PermissionError (Permission denied)"
    ) in error_output
    assert str(vault_dir) not in error_output


def test_a_temporary_file_left_of_a_sheet_fails_its_subject_and_digest_exits_4(
    monkeypatch, digest_environment, capsys
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )
    sheets_dir = vault_dir / "veille" / "agent_tools"
    sheets_dir.mkdir(parents=True)
    claim = sheets_dir / ".2026-10-21.md.tmp"
    claim.write_text("another run\n", "utf-8")

    assert cli.main(["digest"]) == cli.ExitCode.PARTIAL_FAILURE
    assert list_sheets(vault_dir) == [
        "veille/research/2026-10-21.md",
        "veille/security_alerts/2026-10-21.md",
    ]
    assert claim.read_text("utf-8") == "another run\n"
    assert (
        "agent_tools: sheet not written: temporary_file_found:"
        " veille/agent_tools/.2026-10-21.md.tmp is there\n"
    ) in capsys.readouterr().err


def test_a_sigterm_while_a_sheet_is_written_stops_digest_and_keeps_the_sheet(
    monkeypatch, digest_environment, sigterm_handler_of_the_test
):
    _, vault_dir = digest_environment
    answer_digests(
        monkeypatch, answer_with(make_response([AGENT_DIGEST, RESEARCH_DIGEST]))
    )
    write_file_atomically = vault_files.write_file_atomically

    def write_then_receive_sigterm(path, content, **options):
        write_file_atomically(path, content, **options)
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(
        vault_files, "write_file_atomically", write_then_receive_sigterm
    )

    exit_code = cli.main(["digest"])

    assert exit_code == cli.ExitCode.STOPPED_BY_SIGTERM
    assert list_sheets(vault_dir) == ["veille/agent_tools/2026-10-21.md"]
    assert list_hidden_files(vault_dir) == []
    assert signal.getsignal(signal.SIGTERM) is sigterm_handler_of_the_test


def test_a_slow_request_logs_that_the_digests_are_still_awaited(
    monkeypatch, digest_environment, capsys
):
    data_dir, _ = digest_environment
    monkeypatch.setattr(wait_display, "WAIT_LOG_INTERVAL_SECONDS", 0.001)
    wait_line = WaitLineSeen()
    seen_in_time = []

    def answer_once_the_wait_is_logged(request):
        seen_in_time.append(wait_line.seen.wait(5))
        return answer_with(make_response([AGENT_DIGEST]))(request)

    answer_digests(monkeypatch, answer_once_the_wait_is_logged)
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(wait_line)
    try:
        exit_code = cli.main(["digest"])
    finally:
        logger.removeHandler(wait_line)

    assert exit_code == cli.ExitCode.SUCCEEDED
    assert seen_in_time == [True]
    wait_line_logged = (
        rf"^{LOG_LINE_DATE} INFO k_b\.cli: still waiting for the digests:"
        r" \d+ seconds, read timeout 240 seconds$"
    )
    assert re.search(wait_line_logged, capsys.readouterr().err, re.MULTILINE)
    assert re.search(wait_line_logged, read_kb_log(data_dir), re.MULTILINE)


# kb digest run as the kb script runs it, sys.exit(main()), with an AI API that says the request
# has arrived, then never answers: the wait is shown by its thread while SIGTERM comes.
DIGEST_WAITING_FOR_SIGTERM = """
import sys
import time
from functools import partial

import httpx2

from k_b import cli
from k_b.commands import digest_command
from k_b.post.ai_api_client import build_ai_api_client


def wait_for_sigterm(request):
    print("ready", flush=True)
    time.sleep(60)
    return httpx2.Response(500)


digest_command.build_ai_api_client = partial(
    build_ai_api_client, transport=httpx2.MockTransport(wait_for_sigterm)
)
sys.exit(cli.main(["digest"]))
"""


def test_kb_digest_sent_sigterm_while_it_waits_exits_with_143(digest_environment):
    process = subprocess.Popen(  # noqa: S603 — runs this interpreter on a fixed script
        [sys.executable, "-c", DIGEST_WAITING_FOR_SIGTERM],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ),
    )
    try:
        assert process.stdout.readline() == "ready\n"
        process.send_signal(signal.SIGTERM)
        _, error_output = process.communicate(timeout=30)
    finally:
        process.kill()
        process.wait()

    assert process.returncode == cli.ExitCode.STOPPED_BY_SIGTERM
    assert "ERROR k_b.cli: kb stopped by SIGTERM" in error_output


def test_kb_help_lists_digest(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])

    assert re.search(
        r"^    digest +ask the AI API for the digests of the watch",
        capsys.readouterr().out,
        re.MULTILINE,
    )
