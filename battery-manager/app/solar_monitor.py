"""Solar monitoring helpers."""

from __future__ import annotations

from typing import Optional


def detect_excess_solar(
    solar_power: Optional[float],
    house_load: Optional[float],
    threshold: float,
) -> Optional[float]:
    """Return excess solar power (solar - load) or None if inputs missing."""

    if solar_power is None or house_load is None:
        return None
    return solar_power - house_load


def should_charge_from_solar(excess: Optional[float], threshold: float) -> bool:
    """Return True if excess solar exceeds the configured threshold."""

    if excess is None:
        return False
    return excess > threshold
