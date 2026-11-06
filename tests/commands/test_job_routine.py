"""The run of the steps of a job: in order, a step not run after some codes of another, the worst
code in the order 0, 4, 2, 1, an exception of a step counted as 1, a stop never caught."""

import logging

import pytest

from k_b.commands.exit_codes import ExitCode
from k_b.commands.job_routine import (
    NotRunAfter,
    RoutineStep,
    describe_routine,
    find_worst_exit_code,
    run_routine,
)
from k_b.commands.sigterm import StoppedBySigtermError

SUCCEEDED, FAILED, NOT_STARTED, PARTIAL_FAILURE = (
    ExitCode.SUCCEEDED,
    ExitCode.FAILED,
    ExitCode.NOT_STARTED,
    ExitCode.PARTIAL_FAILURE,
)


def make_steps(codes, ran, not_run_after=None):
    """A step per name of codes, which records its name in ran and returns its code."""

    def make_run(name, code):
        def run(settings):
            ran.append(name)
            if isinstance(code, BaseException):
                raise code
            return code

        return run

    return [
        RoutineStep(name, make_run(name, code), (not_run_after or {}).get(name))
        for name, code in codes.items()
    ]


def test_every_step_runs_in_order_and_the_routine_succeeds(capsys):
    ran = []
    steps = make_steps({"first": SUCCEEDED, "second": SUCCEEDED}, ran)

    assert run_routine("kb test-routine", steps, settings=None) == SUCCEEDED
    assert ran == ["first", "second"]


def test_a_step_is_not_run_after_the_codes_named_by_its_rule(capsys, caplog):
    ran = []
    steps = make_steps(
        {"kb collect": FAILED, "kb import": SUCCEEDED, "kb write-tops": SUCCEEDED},
        ran,
        {"kb import": NotRunAfter("kb collect", frozenset({FAILED, NOT_STARTED}))},
    )

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = run_routine("kb test-routine", steps, settings=None)

    assert ran == ["kb collect", "kb write-tops"]
    assert exit_code == FAILED
    assert "step 2 of 3, kb import, not run: kb collect exited with 1" in caplog.text


@pytest.mark.parametrize(
    ("codes", "worst"),
    [
        ([SUCCEEDED, SUCCEEDED], SUCCEEDED),
        ([SUCCEEDED, PARTIAL_FAILURE], PARTIAL_FAILURE),
        ([PARTIAL_FAILURE, NOT_STARTED], NOT_STARTED),
        ([NOT_STARTED, FAILED], FAILED),
        ([FAILED, PARTIAL_FAILURE, SUCCEEDED], FAILED),
        ([FAILED, NOT_STARTED], FAILED),
        # No step returns another code; one would count as the worst.
        ([FAILED, 3], 3),
    ],
)
def test_the_exit_code_is_the_worst_in_the_order_0_4_2_1(codes, worst):
    assert find_worst_exit_code(codes) == worst


def test_an_exception_of_a_step_counts_as_1_and_the_next_steps_run(capsys, caplog):
    ran = []
    steps = make_steps({"first": ValueError("a bug"), "second": SUCCEEDED}, ran)

    with caplog.at_level(logging.INFO, logger="k_b"):
        exit_code = run_routine("kb test-routine", steps, settings=None)

    assert exit_code == FAILED
    assert ran == ["first", "second"]
    assert "first stopped by an exception it does not handle" in caplog.text
    assert "ValueError: a bug" in caplog.text


@pytest.mark.parametrize("stop", [StoppedBySigtermError(), KeyboardInterrupt()])
def test_a_stop_is_never_caught_and_no_later_step_runs(capsys, stop):
    ran = []
    steps = make_steps({"first": stop, "second": SUCCEEDED}, ran)

    with pytest.raises(type(stop)):
        run_routine("kb test-routine", steps, settings=None)

    assert ran == ["first"]


def test_the_end_of_each_step_is_logged_with_its_code(capsys, caplog):
    steps = make_steps({"first": SUCCEEDED, "second": PARTIAL_FAILURE}, [])

    with caplog.at_level(logging.INFO, logger="k_b"):
        run_routine("kb test-routine", steps, settings=None)

    assert "kb test-routine: step 1 of 2, first, exited with 0" in caplog.text
    assert "kb test-routine: step 2 of 2, second, exited with 4" in caplog.text
    assert "kb test-routine finished in" in caplog.text
    assert "exit code 4" in caplog.text


def test_the_summary_gives_each_step_its_code_or_not_run(capsys):
    steps = make_steps(
        {"kb collect": NOT_STARTED, "kb import": SUCCEEDED},
        [],
        {"kb import": NotRunAfter("kb collect", frozenset({FAILED, NOT_STARTED}))},
    )

    run_routine("kb test-routine", steps, settings=None)

    output = capsys.readouterr().out
    assert "kb collect  2 (not started)" in output
    assert "kb import   not run" in output


def test_the_dry_run_lists_the_steps_and_their_rule():
    steps = make_steps(
        {"kb collect": SUCCEEDED, "kb import": SUCCEEDED},
        [],
        {"kb import": NotRunAfter("kb collect", frozenset({FAILED, NOT_STARTED}))},
    )

    assert describe_routine("kb test-routine", steps) == (
        "kb test-routine, dry run: 2 steps, none run\n"
        "  1. kb collect\n"
        "  2. kb import, not run when kb collect exits with 1 or 2"
    )
