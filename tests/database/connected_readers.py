"""The readers of a test base, the PostgreSQL pool connected before the test reads."""

from contextlib import contextmanager
from pathlib import Path

from k_b.database.engine import open_readers


@contextmanager
def open_connected_readers(location, query_timeout_seconds):
    """The readers of open_readers, the pool waited for until it holds its first connection.

    The pool connects in the background, and a request waits for a connection at most
    READING_POOL_WAIT_SECONDS: without the wait, a slow runner fails the first request of a test
    with PoolTimeout, before it reaches the base."""
    with open_readers(location, query_timeout_seconds) as readers:
        if not isinstance(readers, Path):
            readers.wait()
        yield readers
