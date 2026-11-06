"""The run of the steps of a job of Azure Container Apps (#413): in order, in the process of kb, a
step not run after some codes of another; the exit code is the worst of the steps.

In the same process, not by subprocess.run: kb is the PID 1 of the container and the only process
SIGTERM reaches; stopping_on_sigterm then covers every step, and the code of a step is the one its
command returns."""

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from time import monotonic

from k_b.commands.batch_summary import describe_duration, render_table
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

# From the best to the worst (decision of Sabine of 2026-11-06, #413): their values do not order
# them. A 2 can be harmless (kb digest on a second run of the day), a 1 is a step that ran and
# failed. A stop, 130 or 143, ends the routine at once: it is always its code (cli.py).
EXIT_CODES_FROM_BEST_TO_WORST = (
    ExitCode.SUCCEEDED,
    ExitCode.PARTIAL_FAILURE,
    ExitCode.NOT_STARTED,
    ExitCode.FAILED,
)
# The code of each value, as ExitCode(value) needs its meaning too.
EXIT_CODE_BY_VALUE = {int(code): code for code in ExitCode}
NOT_RUN = "not run"
SUMMARY_HEADER = ("step", "result")


@dataclass(frozen=True)
class NotRunAfter:
    """The rule of a step: not run when an earlier step exits with one of exit_codes."""

    step_name: str
    exit_codes: frozenset[int]


@dataclass(frozen=True)
class RoutineStep[Settings]:
    """A step of a routine: its name, what it runs with the settings of the routine, and its rule."""

    name: str
    run: Callable[[Settings], int]
    not_run_after: NotRunAfter | None = None


def run_routine[Settings](
    title: str, steps: Sequence[RoutineStep[Settings]], settings: Settings
) -> int:
    """Run each step in order, unless its rule stops it, then print the summary; a stop by a signal
    is not caught, and ends the routine."""
    logger.info("%s started: %d steps", title, len(steps))
    started = monotonic()
    codes: dict[str, int] = {}
    for position, step in enumerate(steps, start=1):
        where = f"{title}: step {position} of {len(steps)}, {step.name}"
        stopping_code = find_stopping_code(step, codes)
        if stopping_code is not None and step.not_run_after is not None:
            logger.info(
                "%s, not run: %s exited with %d",
                where,
                step.not_run_after.step_name,
                stopping_code,
            )
            continue
        logger.info("%s, started", where)
        codes[step.name] = run_step(step, settings)
        # Each end on its line: on SIGTERM, no summary is printed, and these lines say what was done.
        logger.info("%s, exited with %d", where, codes[step.name])
    exit_code = find_worst_exit_code(codes.values())
    logger.info(
        "%s finished in %s: exit code %d",
        title,
        describe_duration(monotonic() - started),
        exit_code,
    )
    print(render_routine_summary(title, steps, codes))
    # A blank line after the result, as for kb digest (decision of Sabine of 2026-10-29).
    print()
    return exit_code


def find_stopping_code[Settings](
    step: RoutineStep[Settings], codes: Mapping[str, int]
) -> int | None:
    """The code of the earlier step that stops this one by its rule, or None."""
    rule = step.not_run_after
    if rule is None:
        return None
    code = codes.get(rule.step_name)
    return code if code in rule.exit_codes else None


def run_step[Settings](step: RoutineStep[Settings], settings: Settings) -> int:
    """Run the step; an exception it does not handle is logged with its traceback and counts as 1,
    as for a command (cli.py); StoppedBySigtermError and KeyboardInterrupt are not Exceptions."""
    try:
        return step.run(settings)
    except Exception:
        logger.exception("%s stopped by an exception it does not handle", step.name)
        return ExitCode.FAILED


def find_worst_exit_code(codes: Iterable[int]) -> int:
    """The worst code in EXIT_CODES_FROM_BEST_TO_WORST; a code out of it, which no step returns,
    counts as the worst."""
    return max(codes, key=rank_exit_code, default=ExitCode.SUCCEEDED)


def rank_exit_code(code: int) -> int:
    """The rank of a code from the best, 0; a code out of the order comes last."""
    if code in EXIT_CODES_FROM_BEST_TO_WORST:
        return EXIT_CODES_FROM_BEST_TO_WORST.index(EXIT_CODE_BY_VALUE[code])
    return len(EXIT_CODES_FROM_BEST_TO_WORST)


def render_routine_summary[Settings](
    title: str, steps: Sequence[RoutineStep[Settings]], codes: Mapping[str, int]
) -> str:
    """A row per step: its code and its name, 2 (not started), or not run."""
    rows = [(step.name, describe_step_result(codes.get(step.name))) for step in steps]
    table = render_table([SUMMARY_HEADER, *rows])
    # Underlined, the title of the block, as for kb digest (decision of Sabine of 2026-10-29).
    return "\n".join(["", title, "-" * len(title), *table])


def describe_step_result(code: int | None) -> str:
    """4 (partial failure), 3, or not run."""
    if code is None:
        return NOT_RUN
    exit_code = EXIT_CODE_BY_VALUE.get(code)
    if exit_code is None:
        return str(code)
    return f"{code} ({exit_code.name.lower().replace('_', ' ')})"


def describe_routine[Settings](
    title: str, steps: Sequence[RoutineStep[Settings]]
) -> str:
    """The steps of the routine and their rules, for --dry-run: nothing is run."""
    lines = [f"{title}, dry run: {len(steps)} steps, none run"]
    for position, step in enumerate(steps, start=1):
        lines.append(f"  {position}. {step.name}{describe_rule(step.not_run_after)}")
    return "\n".join(lines)


def describe_rule(rule: NotRunAfter | None) -> str:
    """, not run when kb collect exits with 1 or 2; nothing without a rule."""
    if rule is None:
        return ""
    codes = " or ".join(str(code) for code in sorted(rule.exit_codes))
    return f", not run when {rule.step_name} exits with {codes}"
