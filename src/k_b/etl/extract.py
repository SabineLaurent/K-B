"""Run every source and store its raw output; a failing source never stops the others."""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from k_b.core.quoting import quote_value
from k_b.etl.raw_files import COLLECTION_NAME_FORMAT
from k_b.etl.raw_store import (
    COLLECTION_STATE_FILENAME,
    RAW_DIR_NAMES,
    load_last_collection_dates,
    save_last_collection_dates,
    write_new_raw_file,
)
from k_b.etl.source_contract import Source

logger = logging.getLogger(__name__)

SAFE_PATH_SEGMENT = re.compile(r"[a-z0-9_]+")
# A page name is a file name under the collection folder: a date such as 2026-09-30.
SAFE_PAGE_NAME = re.compile(r"[a-z0-9_-]+")


class CollectionOutcome(NamedTuple):
    errors_by_source: dict[str, Exception | None]
    # The raw files are written even when the state is not: the next run collects again.
    state_error: OSError | None


def collect_all_sources(
    sources: list[Source], raw_dir: Path, data_dir: Path, now: datetime
) -> CollectionOutcome:
    """Collect each source; return each source's error (None: success) and the state's error."""
    if now.utcoffset() != timedelta(0):
        raise ValueError(f"collection time must be in UTC, got {now!r}")
    last_collection_dates = load_last_collection_dates(data_dir)
    errors_by_source: dict[str, Exception | None] = {}
    for source in sources:
        try:
            collect_one_source(
                source, raw_dir, now, last_collection_dates.get(source.name)
            )
        except Exception as error:
            # The error and the notes of a source (the day and url of a page) go on the dated
            # line, quoted: any source may raise any text. The traceback follows it.
            notes = "".join(
                f"; {quote_value(note)}" for note in getattr(error, "__notes__", [])
            )
            logger.exception(
                "collection failed for source %r: %s %s%s",
                source.name,
                type(error).__name__,
                # On the dated line, quoted; the traceback gives it again with its stack.
                quote_value(str(error)),  # noqa: TRY401
                notes,
            )
            errors_by_source[source.name] = error
        else:
            last_collection_dates[source.name] = now
            errors_by_source[source.name] = None
    try:
        save_last_collection_dates(data_dir, last_collection_dates)
    except OSError as error:
        logger.exception(
            "collection state not written to %s", data_dir / COLLECTION_STATE_FILENAME
        )
        return CollectionOutcome(errors_by_source, error)
    return CollectionOutcome(errors_by_source, None)


def collect_one_source(
    source: Source, raw_dir: Path, now: datetime, last_collected_at: datetime | None
) -> None:
    """Collect one source and write what it gives under raw/: one raw file named by now, or a
    folder of that name holding one file per page; nothing if the source says nothing changed."""
    if source.acquisition_dir_name not in RAW_DIR_NAMES:
        raise ValueError(f"not a folder of raw/: {source.acquisition_dir_name!r}")
    for path_segment in (source.name, source.extension):
        if not SAFE_PATH_SEGMENT.fullmatch(path_segment):
            raise ValueError(f"not a safe path segment: {path_segment!r}")
    raw_content = source.fetch(last_collected_at)
    if raw_content is None:
        return
    source_dir = raw_dir / source.acquisition_dir_name / source.name
    collection_name = now.strftime(COLLECTION_NAME_FORMAT)
    if isinstance(raw_content, bytes):
        write_new_raw_file(
            source_dir / f"{collection_name}.{source.extension}", raw_content
        )
        return
    # Every name is checked before the first write: a refused name leaves no partial collection.
    # A write that fails midway (disk full) does leave the pages already written.
    for page_name in raw_content:
        if not SAFE_PAGE_NAME.fullmatch(page_name):
            raise ValueError(f"not a safe page name: {page_name!r}")
    for page_name, page in raw_content.items():
        write_new_raw_file(
            source_dir / collection_name / f"{page_name}.{source.extension}", page
        )
