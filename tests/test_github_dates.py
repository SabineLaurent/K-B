from datetime import UTC, datetime

import pytest

from k_b.github_dates import parse_github_date


def test_a_github_date_is_read_in_utc():
    assert parse_github_date(
        "2026-10-01T18:00:22Z", "release 0: published_at"
    ) == datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)


@pytest.mark.parametrize("stored_date", [None, 42, "yesterday", "2026-10-01T18:00:22"])
def test_anything_but_a_date_with_a_time_zone_is_refused_with_its_label(stored_date):
    with pytest.raises(ValueError, match="release 0: published_at"):
        parse_github_date(stored_date, "release 0: published_at")
