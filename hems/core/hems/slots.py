"""Shared quarter-hour time grid for planner, forecast and price helpers.

Why a UTC timeline: a local-time grid breaks on DST days (23 or 25 hours); stepping in UTC and converting
each slot to local time afterwards keeps every consumer consistent.
"""
from datetime import datetime, timedelta, timezone

SLOT_MINUTES = 15
SLOT_H = SLOT_MINUTES / 60


def slot_starts(start: datetime, n_slots: int) -> list[datetime]:
    """UTC start of `n_slots` consecutive quarter-hour slots beginning at `start` (timezone-aware)."""
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    start_utc = start.astimezone(timezone.utc)
    return [start_utc + timedelta(minutes=SLOT_MINUTES * i) for i in range(n_slots)]
