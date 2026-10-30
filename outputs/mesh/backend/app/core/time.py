"""Normalize database timestamps without changing the instant they represent."""

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    # SQLite drops offsets; application-written naive timestamps are UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
