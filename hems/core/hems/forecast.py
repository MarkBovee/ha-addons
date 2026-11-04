"""Consumption forecast baseline: local hour-of-day profile over the last N days.

Deliberately simple; replace later with a regression once weeks of data exist. The input must be the
uncontrollable base load (house minus EV, hot-water heating and other loads HEMS schedules itself), otherwise
the plan counts those loads twice. A temperature correction (`temperature_slope`, `with_temperature`) scales the profile for
a house heated by a heat pump: colder than in the history means more load, warmer means less.

History is keyed by timezone-aware datetimes, not row counts: a DST day has 23 or 25 hours, so counting rows
would shift the window and mislabel hours.
"""
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta
from statistics import mean, median
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


TEMP_MIN_HOURS = 48            # history hours with a temperature before a slope is trusted (two days)
TEMP_MIN_SPREAD_C = 2.0        # the temperatures must differ this much (standard deviation) around their hourly means
TEMP_MAX_SLOPE_W = 600.0       # a steeper fit than this many W per degree is noise, not the house


def _hour_temperature(outdoor_c: Mapping[datetime, float], hour: datetime) -> float | None:
    """The mean outdoor temperature over the four quarters of one hour; None when the hour has none."""
    values = [v for q in range(4) if (v := outdoor_c.get(hour + timedelta(minutes=15 * q))) is not None]
    return sum(values) / len(values) if values else None


def temperature_slope(history: list[tuple[datetime, float]], outdoor_c: Mapping[datetime, float], profile_w: list[float],
                      tz: ZoneInfo = LOCAL_TZ) -> tuple[float, list[float]] | None:
    """How much the load rises per degree colder (W per °C, zero or negative), fitted on the history, plus the mean history temperature per local hour.

    Each history hour is compared with the profile value of its local hour (what the hour usually takes) and with the mean temperature of
    that local hour; the least-squares slope of the load difference against the temperature difference is the house's temperature response.
    None when the history has too few hours with a temperature, too little temperature spread, or a fit that says warmer means more load
    (cooling or noise): then the profile is used as it is."""
    by_hour: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for ts, watts in history:
        temp = _hour_temperature(outdoor_c, ts)
        if temp is not None:
            by_hour[ts.astimezone(tz).hour].append((watts, temp))
    pairs = [(watts - profile_w[h], temp - mean(t for _, t in rows)) for h, rows in by_hour.items() for watts, temp in rows]
    if len(pairs) < TEMP_MIN_HOURS:
        return None
    spread = sum(dt * dt for _, dt in pairs)
    if (spread / len(pairs)) ** 0.5 < TEMP_MIN_SPREAD_C:
        return None
    slope = sum(dw * dt for dw, dt in pairs) / spread
    if slope >= 0:
        return None
    hour_means = [mean(t for _, t in by_hour[h]) if by_hour[h] else None for h in range(24)]
    return max(slope, -TEMP_MAX_SLOPE_W), hour_means


def with_temperature(load_kwh: Mapping[datetime, float], profile_w: list[float], slope_w_per_c: float, hour_means: list[float | None],
                     outdoor_c: Mapping[datetime, float], tz: ZoneInfo = LOCAL_TZ) -> dict[datetime, float]:
    """The quarter forecast moved by the temperature: slope × (forecast temperature − the hour's mean in the history).

    A quarter without a forecast temperature, or an hour the history had no temperature for, keeps its value; the result never drops
    below a quarter of the profile, so a warm spell cannot forecast an empty house."""
    out = dict(load_kwh)
    for quarter, kwh in load_kwh.items():
        hour = quarter.astimezone(tz).hour
        temp, usual = outdoor_c.get(quarter), hour_means[hour]
        if temp is None or usual is None:
            continue
        watts = profile_w[hour] + slope_w_per_c * (temp - usual)
        out[quarter] = max(watts, profile_w[hour] / 4) / 1000 * SLOT_H
    return out
