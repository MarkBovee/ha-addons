"""Temperature-based discharge duration helpers."""

from __future__ import annotations

from typing import Iterable, List, Optional


def get_discharge_hours(
    temperature: Optional[float],
    thresholds: Iterable[dict],
    default_hours: int = 2,
) -> int:
    """Return discharge hours based on temperature thresholds.

    Thresholds must be an iterable of dicts with keys: temp_max, discharge_hours.
    The first threshold with temperature <= temp_max is selected.
    """

    if temperature is None:
        return default_hours

    normalized: List[dict] = sorted(
        thresholds, key=lambda item: float(item.get("temp_max", float("inf")))
    )
    for entry in normalized:
        temp_max = float(entry.get("temp_max", float("inf")))
        hours = entry.get("discharge_hours")
        if hours is None:
            continue
        if temperature <= temp_max:
            return int(hours)

    return default_hours
