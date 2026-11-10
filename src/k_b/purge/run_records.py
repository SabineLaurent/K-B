"""Step 11 of the sorting: delete the records older than their duration, the logs of the runs and the
journals of the imports alike, by the day in their name."""

import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path

from k_b.core.config import (
    JOURNALS_DIR_NAME,
    LOG_FILE_NAMES,
    LOGS_DIR_NAME,
    RECORD_RETENTION_MONTHS,
)
from k_b.core.dates import subtract_months

logger = logging.getLogger(__name__)

LOG_NAMES_PATTERN = "|".join(re.escape(name) for name in LOG_FILE_NAMES)
# The day comes from the name: a copy or a restoration changes the time of a file. A log of a past
# day: kb.log.2026-10-05; a journal: import-journal-2026-10-05T093000Z.jsonl. Only the logs kb
# writes: a dated file the user left in logs/ stays.
DATED_NAME_BY_FOLDER = {
    LOGS_DIR_NAME: re.compile(
        rf"(?:{LOG_NAMES_PATTERN})\.([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})"
    ),
    JOURNALS_DIR_NAME: re.compile(
        r"import-journal-([0-9]{4}-[0-9]{2}-[0-9]{2})T[0-9]{6}Z\.jsonl"
    ),
}


def delete_expired_records(data_dir: Path, purged_at: datetime) -> int:
    """Delete the logs and the journals older than the duration and return how many; the log gives
    the number, never a name."""
    bound = subtract_months(purged_at.astimezone(UTC), RECORD_RETENTION_MONTHS).date()
    deleted_count = sum(
        delete_file(path)
        for folder_name, dated_name in DATED_NAME_BY_FOLDER.items()
        for path in list_files(data_dir / folder_name)
        if is_dated_before(path.name, dated_name, bound)
    )
    logger.info(
        "logs and journals purge: %d files older than %d months deleted",
        deleted_count,
        RECORD_RETENTION_MONTHS,
    )
    return deleted_count


def list_files(folder: Path) -> list[Path]:
    """The files of a folder, a link or a folder left out; none when it is absent or a link."""
    if not folder.is_dir() or folder.is_symlink():
        return []
    return [
        path for path in folder.iterdir() if path.is_file() and not path.is_symlink()
    ]


def is_dated_before(name: str, dated_name: re.Pattern[str], bound: date) -> bool:
    """Tell whether the day in a name is before the bound; another name never expires, as the
    current log of a run."""
    match = dated_name.fullmatch(name)
    if match is None:
        return False
    try:
        return date.fromisoformat(match[1]) < bound
    except ValueError:
        return False


def delete_file(path: Path) -> bool:
    """Delete a file; False when another run already did."""
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
