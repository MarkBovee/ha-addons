"""Consumption forecast baseline: local hour-of-day profile over the last N days.

Deliberately simple; replace later with a regression once weeks of data exist. The input must be the
uncontrollable base load (house minus EV, hot-water heating and other loads HEMS schedules itself), otherwise
the plan counts those loads twice. Weather scaling is not implemented yet.

History is keyed by timezone-aware datetimes, not row counts: a DST day has 23 or 25 hours, so counting rows
would shift the window and mislabel hours.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from hems.slots import SLOT_H, slot_starts

LOCAL_TZ = ZoneInfo("Europe/Amsterdam")


def hourly_profile(history: list[tuple[datetime, float]], days: int = 7, tz: ZoneInfo = LOCAL_TZ) -> list[float]:
    """24 values (W): median per local hour of day over the `days` days before the newest sample.

    history: (hour start, mean watts) with timezone-aware datetimes. The median keeps one-off peaks
    (washer, EV left in the series) from dominating."""
    if not history:
        return [0.0] * 24
    cutoff = max(ts for ts, _ in history) - timedelta(days=days)
    by_hour: dict[int, list[float]] = defaultdict(list)
    for ts, watts in history:
        if ts > cutoff:
            by_hour[ts.astimezone(tz).hour].append(watts)
    return [median(by_hour[h]) if by_hour[h] else 0.0 for h in range(24)]


def to_slots_kwh(profile_w: list[float], start: datetime, n_slots: int, tz: ZoneInfo = LOCAL_TZ) -> list[float]:
    """kWh per quarter-hour slot for `n_slots` slots from `start` (any quarter, timezone-aware).

    Each slot takes the profile value of its own local hour; the timeline steps in UTC so a 25-hour day
    yields the repeated hour twice instead of drifting."""
    return [profile_w[slot.astimezone(tz).hour] / 1000 * SLOT_H for slot in slot_starts(start, n_slots)]
