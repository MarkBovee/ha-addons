"""Consumption forecast baseline: hour-of-day profile over the last N days.

Optionally scaled by outdoor temperature (heating) via a simple linear factor.
Deliberately simple; replace later with a regression once weeks of data exist.
"""
from collections import defaultdict
from statistics import median


def hourly_profile(history: list[tuple[int, float]], days: int = 7) -> list[float]:
    """history: (hour_of_day, avg_watts) rows, newest last; ~24*days rows.
    Returns 24 values (W) using the median per hour (robust against EV/washer peaks)."""
    rows = history[-24 * days:]
    by_hour: dict[int, list[float]] = defaultdict(list)
    for h, w in rows:
        by_hour[h].append(w)
    return [median(by_hour[h]) if by_hour[h] else 0.0 for h in range(24)]


def to_slots_kwh(profile_w: list[float], start_hour: int, n_slots: int) -> list[float]:
    """Expand an hourly W profile to quarter-hour kWh slots starting at start_hour."""
    return [profile_w[((start_hour * 4 + i) // 4) % 24] / 1000 * 0.25 for i in range(n_slots)]
