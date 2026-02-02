"""EV charger monitoring helpers."""

from __future__ import annotations

from typing import Optional


def is_ev_charging(ev_power: Optional[float], threshold: float) -> bool:
    """Return True if EV charger power exceeds the threshold."""

    if ev_power is None:
        return False
    return ev_power > threshold


def should_pause_discharge(ev_power: Optional[float], threshold: float) -> bool:
    """Return True when battery discharge should pause due to EV charging."""

    return is_ev_charging(ev_power, threshold)


def adjust_house_load(house_load: Optional[float], ev_power: Optional[float]) -> Optional[float]:
    """Return house load excluding EV charging power."""

    if house_load is None:
        return None
    if ev_power is None:
        return house_load

    adjusted = house_load - max(ev_power, 0)
    return max(adjusted, 0)
