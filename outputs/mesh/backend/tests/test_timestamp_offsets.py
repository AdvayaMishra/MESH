from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.core.time import as_utc


@pytest.mark.parametrize(
    "offset", [timedelta(hours=5, minutes=30), timedelta(hours=-7), timedelta(hours=14)]
)
def test_utc_conversion_preserves_the_instant_for_database_offsets(offset):
    instant = datetime(2030, 1, 1, 12, 30, tzinfo=UTC)
    database_value = instant.astimezone(timezone(offset))
    assert as_utc(database_value) == instant
    assert as_utc(database_value).timestamp() == database_value.timestamp()
    assert as_utc(database_value).tzinfo is UTC


def test_naive_sqlite_timestamps_follow_the_application_utc_convention():
    assert as_utc(datetime(2030, 1, 1)) == datetime(2030, 1, 1, tzinfo=UTC)
