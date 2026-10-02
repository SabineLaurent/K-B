"""Dates of the GitHub API."""

from datetime import datetime


def parse_github_date(stored_date: object, label: str) -> datetime:
    """Refuse a date without a time zone: GitHub dates are UTC, written with a final Z.

    label names the date in error messages, such as "release 0: published_at".
    """
    if not isinstance(stored_date, str):
        raise ValueError(f"{label} is not a date")
    try:
        parsed_date = datetime.fromisoformat(stored_date)
    except ValueError as error:
        raise ValueError(f"{label} is invalid: {stored_date!r}") from error
    if parsed_date.tzinfo is None:
        raise ValueError(f"{label} has no time zone")
    return parsed_date
