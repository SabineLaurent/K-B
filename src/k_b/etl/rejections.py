"""The one path of every rejection, from the stage that finds it to the log of the import
(conventions.md, rule 1): an entry its reader refused, a page that cannot be read, a release of a
repository out of the tracked list, an item the base refuses.

A rejection is a named state, not an error: it is logged once, here, and returned to the stage,
which goes on reading or writing. The caller gives the reason, with the field, the measure and,
when there is one, the value already quoted (core/quoting.py); the type of a rejection stays in
the vocabulary the stages share (etl/raw_files.py).
"""

import logging

from k_b.etl.raw_files import Rejection

logger = logging.getLogger(__name__)


def reject(raw_file_path: str, reason: str) -> Rejection:
    logger.warning("rejected from %s: %s", raw_file_path, reason)
    return Rejection(raw_file_path, reason)
