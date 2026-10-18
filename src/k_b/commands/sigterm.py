"""The stop of kb collect and kb import on SIGTERM."""

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

from k_b.commands.exit_codes import ExitCode


class StoppedBySigtermError(SystemExit):
    """SIGTERM received by kb collect or kb import: docker stop sends it before SIGKILL."""

    def __init__(self) -> None:
        super().__init__(ExitCode.STOPPED_BY_SIGTERM)


# The commands that stop on SIGTERM; kb serve keeps the handler of uvicorn.
COMMANDS_STOPPED_BY_SIGTERM = frozenset({"collect", "import"})


@contextmanager
def stopping_on_sigterm(command: str) -> Iterator[None]:
    """For kb collect and kb import, turn SIGTERM into StoppedBySigtermError, a SystemExit: the
    import is undone and its log removed, the temporary files are removed, as on any exception.
    A SIGTERM received during the commit of the import is raised once the commit has returned:
    the import and its log are kept (etl/load.py, commit_with_log). The handler found is set
    back on exit.
    Called from the main thread only: Python sets a signal handler nowhere else."""
    if command not in COMMANDS_STOPPED_BY_SIGTERM:
        yield
        return
    previous_handler = signal.signal(signal.SIGTERM, raise_stopped_by_sigterm)
    try:
        yield
    finally:
        # None: a handler not set from Python, which signal.signal refuses.
        signal.signal(
            signal.SIGTERM,
            signal.SIG_DFL if previous_handler is None else previous_handler,
        )


def raise_stopped_by_sigterm(signal_number: int, frame: FrameType | None) -> None:
    # A second SIGTERM would stop the clean-up; Docker sends SIGKILL after its delay anyway.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise StoppedBySigtermError
