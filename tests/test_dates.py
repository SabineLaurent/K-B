"""subtract_months: the bounds of the purge, months back on the calendar."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from k_b.core.dates import subtract_months


@pytest.mark.parametrize(
    ("moment", "months", "expected"),
    [
        # Three years of the watch in the base.
        (
            datetime(2029, 10, 8, 9, 30, tzinfo=UTC),
            36,
            datetime(2026, 10, 8, 9, 30, tzinfo=UTC),
        ),
        # Six months of the raw, to the second.
        (
            datetime(2027, 4, 5, 9, 30, 1, tzinfo=UTC),
            6,
            datetime(2026, 10, 5, 9, 30, 1, tzinfo=UTC),
        ),
        # Across a year.
        (datetime(2027, 1, 15, tzinfo=UTC), 6, datetime(2026, 7, 15, tzinfo=UTC)),
        # A day the month does not have becomes its last one.
        (
            datetime(2028, 2, 29, 12, tzinfo=UTC),
            36,
            datetime(2025, 2, 28, 12, tzinfo=UTC),
        ),
        (datetime(2027, 8, 31, tzinfo=UTC), 6, datetime(2027, 2, 28, tzinfo=UTC)),
        (datetime(2028, 8, 31, tzinfo=UTC), 6, datetime(2028, 2, 29, tzinfo=UTC)),
    ],
)
def test_subtract_months_goes_back_on_the_calendar(moment, months, expected):
    assert subtract_months(moment, months) == expected


def test_subtract_months_keeps_the_time_and_the_time_zone():
    paris = timezone(timedelta(hours=1))

    earlier = subtract_months(datetime(2027, 3, 1, 8, 15, 42, tzinfo=paris), 6)

    assert earlier == datetime(2026, 9, 1, 8, 15, 42, tzinfo=paris)
    assert earlier.tzinfo is paris
