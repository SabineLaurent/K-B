"""The stop of kb collect, kb import, kb write-tops and kb digest on Ctrl-C (SIGINT)."""

import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from types import FrameType

from k_b.commands.sigterm import COMMANDS_STOPPED_BY_SIGTERM

# The same commands as for SIGTERM; kb serve-data and kb serve-ai keep the handler of uvicorn,
# which sends SIGINT again once stopped (uvicorn/server.py).
COMMANDS_STOPPED_BY_SIGINT = COMMANDS_STOPPED_BY_SIGTERM


@contextmanager
def stopping_on_sigint(command: str) -> Iterator[None]:
    """Turn the first Ctrl-C into KeyboardInterrupt, which the command undoes its work on, and
    ignore the next ones, which would cut that undoing; the handler found is set back on exit,
    unless Ctrl-C stopped the command."""
    # SIGINT ignored from the start, as for kb run in the background of a script: Ctrl-C is not
    # meant for it, and stays ignored.
    if (
        command not in COMMANDS_STOPPED_BY_SIGINT
        or signal.getsignal(signal.SIGINT) is signal.SIG_IGN
    ):
        yield
        return
    previous_handler = signal.signal(signal.SIGINT, raise_keyboard_interrupt_once)
    stopped_by_ctrl_c = False
    try:
        yield
    except KeyboardInterrupt:
        stopped_by_ctrl_c = True
        raise
    finally:
        if stopped_by_ctrl_c:
            # Ignored until kb dies by it (cli.py): a second Ctrl-C would cut the line of the
            # log, or its closing.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        else:
            # None: a handler not set from Python, which signal.signal refuses.
            signal.signal(
                signal.SIGINT,
                signal.SIG_DFL if previous_handler is None else previous_handler,
            )


def raise_keyboard_interrupt_once(signal_number: int, frame: FrameType | None) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise KeyboardInterrupt


def die_by_sigint() -> None:
    """Die by SIGINT, as Python does on a Ctrl-C nothing catches: a shell running kb in a loop
    then stops the loop instead of going on."""
    for stream in (sys.stdout, sys.stderr):
        # A stream already closed, or a pipe whose reader is gone: nothing more to say.
        with suppress(OSError, ValueError):
            stream.flush()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.raise_signal(signal.SIGINT)
