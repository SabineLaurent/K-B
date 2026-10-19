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
        "the command ran and failed; kb collect: no source collected, or state not written",
    )
    NOT_STARTED = 2, "nothing was run: a setting, a file or the command line is refused"
    # Not returned by kb: uvicorn exits with it (STARTUP_FAILURE, uvicorn/config.py). Named here
    # so that no other code takes its value.
    SERVER_NOT_STARTED = 3, "kb serve: the server did not start"
    # 4: the first value after the one of uvicorn.
    PARTIAL_FAILURE = (
        4,
        "kb collect: at least one source collected, at least one failed, state written",
    )
    # 128 + 15, the code of a process stopped by SIGTERM.
    STOPPED_BY_SIGTERM = (
        143,
        "kb collect, kb import, kb write-tops: stopped by SIGTERM; what was done before it is kept",
    )
