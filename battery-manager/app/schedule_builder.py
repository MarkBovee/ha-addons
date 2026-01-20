"""Helpers to build battery charge/discharge schedules."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Sequence

from dateutil.parser import isoparse


def build_charge_schedule(
    charge_periods: Iterable[dict],
    power: int,
    duration_minutes: int,
) -> List[dict]:
    """Build charge schedule entries from periods."""

    schedule = []
    for period in charge_periods:
        start = _normalize_start_time(period.get("start"))
        duration = period.get("duration", duration_minutes)
        if not start:
            continue
        schedule.append({"start": start, "power": power, "duration": duration})
    return schedule


def build_discharge_schedule(
    discharge_periods: Sequence[dict],
    power_ranks: Sequence[int],
    duration_minutes: int,
) -> List[dict]:
    """Build discharge schedule entries with per-period power."""

    if len(discharge_periods) != len(power_ranks):
        raise ValueError("discharge_periods and power_ranks must be the same length")

    schedule = []
    for period, power in zip(discharge_periods, power_ranks, strict=True):
        start = _normalize_start_time(period.get("start"))
        duration = period.get("duration", duration_minutes)
        if not start:
            continue
        schedule.append({"start": start, "power": power, "duration": duration})
    return schedule


def _normalize_start_time(value: object) -> str | None:
    if not value:
        return None
    if isinstance(value, str) and len(value) == 5 and value[2] == ":":
        return value
    if isinstance(value, str):
        try:
            parsed = isoparse(value)
            return parsed.strftime("%H:%M")
        except Exception:
            return None
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    return None


def merge_schedules(charge: Iterable[dict], discharge: Iterable[dict]) -> dict:
    """Merge charge and discharge schedules. Charge takes priority on overlap."""

    charge_list = list(charge)
    discharge_list = list(discharge)

    charge_starts = {item.get("start") for item in charge_list}
    filtered_discharge = [item for item in discharge_list if item.get("start") not in charge_starts]

    return {"charge": charge_list, "discharge": filtered_discharge}
