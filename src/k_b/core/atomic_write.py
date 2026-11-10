"""The one function that writes a file K-B writes itself (conventions.md, rule 2)."""

import contextlib
import errno
import itertools
import os
import tempfile
from pathlib import Path
from typing import IO

# The errors of a file system that does not support the sync of a folder: EINVAL (fsync(2)),
# EBADF on some systems. PostgreSQL tolerates the same two, EINVAL since bug #15636 on Linux
# CIFS (https://www.postgresql.org/message-id/E1gxrcU-0002A8-17%40gemulon.postgresql.org,
# read on 2026-10-16). Any other error is raised: the rename is not known to be on disk.
REFUSED_FOLDER_SYNC_ERRORS = (errno.EBADF, errno.EINVAL)
# The mode of a file written once, as tempfile gives the other: read and written by its owner only.
PRIVATE_FILE_MODE = 0o600


class TemporaryFileFoundError(Exception):
    """The temporary file of a file written once is there: another run writes it, or a run stopped
    before removing it left it. Not a FileExistsError, which says the file itself is there."""

    def __init__(self, temporary_path: Path) -> None:
        super().__init__(f"temporary_file_found: {temporary_path.name} is there")
        self.temporary_path = temporary_path


def write_file_atomically(path: Path, content: bytes, *, replace: bool = True) -> None:
    """Write to a hidden temporary file of the target folder, sync it, rename it, then sync the
    folders: a reader never sees a half-written file, and a power cut cannot keep a later file
    while losing this one (conventions.md, rule 2). With replace=False, a file listed just before
    the rename is never replaced (FileExistsError), nor one another run of kb writes meanwhile."""
    # The folder of the target, then each new parent up to the first that exists: each holds
    # the entry of a new file or folder.
    folders_to_sync = [path.parent]
    folders_to_sync += [
        folder.parent
        for folder in itertools.takewhile(
            lambda folder: not folder.exists(), path.parents
        )
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_temporary_file(path, replace=replace) as temporary_file:
        try:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_file.close()
            if not replace:
                refuse_listed_file(path)
            os.replace(temporary_file.name, path)
        except BaseException:
            # The original error is raised. A failed flush leaves data in the buffer: closed
            # here, the file does not fail again on leaving the with block. The temporary file
            # may already be renamed (Ctrl-C right after os.replace) or not removable; with
            # replace=False, its name may then be the claim of another run, which finds the
            # file and writes nothing.
            with contextlib.suppress(OSError):
                temporary_file.close()
            with contextlib.suppress(OSError):
                os.remove(temporary_file.name)
            raise
    for folder in folders_to_sync:
        folder_descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(folder_descriptor)
        except OSError as error:
            if error.errno not in REFUSED_FOLDER_SYNC_ERRORS:
                raise
        finally:
            os.close(folder_descriptor)


def open_temporary_file(path: Path, *, replace: bool) -> IO[bytes]:
    """A hidden temporary file of the target folder. For a file written once, its name is fixed
    and it is created only if absent (O_EXCL, FILE_CREATE on SMB): the claim that keeps two runs
    from writing the same file, as Azure Files has no hard link for os.link."""
    if replace:
        return tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        )
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        return open(temporary_path, "xb", opener=open_private_file)
    except FileExistsError as error:
        raise TemporaryFileFoundError(temporary_path) from error


def open_private_file(name: str, flags: int) -> int:
    """Open name with the flags of open(), created readable and writable by its owner only."""
    return os.open(name, flags, PRIVATE_FILE_MODE)


def refuse_listed_file(path: Path) -> None:
    """Raise FileExistsError when the folder lists path. Not by its status: the CIFS client of
    Linux answers one from its cache of absent names for up to a second (cifs_d_revalidate); it
    keeps a listing only under a lease of the folder, which Azure Files does not grant."""
    if path.name in os.listdir(path.parent):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path.name)
