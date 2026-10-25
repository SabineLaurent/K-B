"""The helpers several test files of the kb commands use."""

from k_b.etl.source_contract import SourceKind


def collected_kinds(*sources):
    """One kind without a reader: the collection tests only need its sources."""
    return (SourceKind("test", sources, None),)


# The date of a log line, in the format of the dates of the base: ISO 8601, UTC, its zone Z.
LOG_LINE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


class SigtermNotHandledByKbError(Exception):
    """Raised by the handler of the test: kb did not set its own."""


def list_hidden_files(directory):
    return [path for path in directory.rglob(".*") if path.is_file()]


def list_sheets(vault_dir):
    return sorted(
        path.relative_to(vault_dir).as_posix() for path in vault_dir.rglob("*.md")
    )
