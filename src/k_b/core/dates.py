"""The dates of the items database: their format, and the bounds of the purge."""

import calendar
from datetime import UTC, date, datetime

# The date format the CHECK constraints of schema.sql accept.
DATABASE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The dates of the base are compared as text: the format of its CHECK constraints keeps the
# order of the text the order of time.


def format_date(moment: datetime | None) -> str | None:
    """Format a moment as a UTC date for the database, or keep None."""
    return (
        None
        if moment is None
        else moment.astimezone(UTC).strftime(DATABASE_DATE_FORMAT)
    )


def format_day(day: date) -> str:
    """A day at midnight UTC, in the format of the base; isoformat, as strftime leaves the width
    of the year to the C library."""
    return f"{day.isoformat()}T00:00:00Z"


def subtract_months(moment: datetime, months: int) -> datetime:
    """The same time, months earlier on the calendar; a day the month lacks becomes its last one
    (2028-02-29 less 36 months is 2025-02-28)."""
    month_index = moment.year * 12 + moment.month - 1 - months
    year, month_offset = divmod(month_index, 12)
    month = month_offset + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)
