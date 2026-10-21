"""The exit codes of kb, the same for every command."""

from enum import IntEnum
from typing import Self


class ExitCode(IntEnum):
    """The code kb exits with, for who runs it: by hand, or as a job in a container, where the
    code is the only way to know what kb did without reading its log. Listed by kb --help."""

    meaning: str

    def __new__(cls, value: int, meaning: str) -> Self:
        member = int.__new__(cls, value)
        member._value_ = value
        member.meaning = meaning
        return member

    SUCCEEDED = 0, "the command succeeded"
    FAILED = (
        1,
        (
            "the command ran and failed; kb collect, kb write-tops, kb digest: no part done,"
            " or kb collect: state not written"
        ),
    )
    NOT_STARTED = 2, "nothing was run: a setting, a file or the command line is refused"
    # Not returned by kb: uvicorn exits with it (STARTUP_FAILURE, uvicorn/config.py). Named here
    # so that no other code takes its value.
    SERVER_NOT_STARTED = 3, "kb serve, kb serve-ai: the server did not start"
    # 4: the first value after the one of uvicorn. A part is a source, a top or a subject
    # (README).
    PARTIAL_FAILURE = (
        4,
        (
            "kb collect, kb write-tops, kb digest: a part failed, another is done and kept;"
            " kb collect: state written"
        ),
    )
    # 128 + 15, the code of a process stopped by SIGTERM. kb serve and kb serve-ai exit with it
    # through uvicorn, which sends the signal again once stopped (uvicorn/server.py): a shell
    # reads 143, a parent process -15.
    STOPPED_BY_SIGTERM = (
        143,
        (
            "kb collect, kb import, kb write-tops, kb digest: stopped by SIGTERM; what was done"
            " before it is kept; kb serve, kb serve-ai: stopped by SIGTERM, outside PID 1"
        ),
    )


def find_exit_code(*, has_failed: bool, has_done: bool) -> ExitCode:
    """The code of a command made of parts (the sources of kb collect, the tops of kb write-tops,
    the subjects of kb digest): the same result, the same code (rule of Sabine of 2026-10-21).
    A part failed: 4 when another is done and kept, 1 when none is."""
    if not has_failed:
        return ExitCode.SUCCEEDED
    return ExitCode.PARTIAL_FAILURE if has_done else ExitCode.FAILED
