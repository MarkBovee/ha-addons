"""State-of-charge protection helpers."""

from __future__ import annotations

from datetime import datetime, time
import math
from typing import Union

TimeLike = Union[datetime, time]


def can_charge(soc: float, max_soc: float) -> bool:
    """Return True if charging is allowed based on max SOC."""

    return soc < max_soc


def calculate_soc_per_hour(power_watts: float, battery_capacity_kwh: float) -> float:
    """Return SOC percentage points used/charged per hour at a given power.

    Example:
        8000W on a 25kWh battery -> 32.0 percentage points per hour.
    """

    if battery_capacity_kwh <= 0:
        return 0.0
    return max(0.0, (power_watts / 1000.0) / battery_capacity_kwh * 100.0)


def calculate_sell_buffer_soc(
    discharge_hours_before_main_charge: float,
    safety_min_soc: float,
    discharge_power_watts: float,
    battery_capacity_kwh: float,
    floor_soc: float = 0.0,
    rounding_step_pct: float = 0.0,
) -> float:
    """Calculate required SOC buffer to cover planned pre-main-charge discharge.

    Formula:
        required_soc = safety_min_soc + discharge_hours * soc_per_hour
    """

    soc_per_hour = calculate_soc_per_hour(discharge_power_watts, battery_capacity_kwh)
    required = safety_min_soc + max(0.0, discharge_hours_before_main_charge) * soc_per_hour
    if rounding_step_pct > 0:
        step = float(rounding_step_pct)
        required = math.floor((required + step / 2.0) / step) * step
    return max(floor_soc, min(100.0, required))


def can_discharge(soc: float, min_soc: float, conservative_soc: float, is_conservative: bool) -> bool:
    """Return True if discharging is allowed under SOC rules."""

    if soc <= min_soc:
        return False
    if is_conservative and soc < conservative_soc:
        return False
    return True


def should_target_eod(current_time: TimeLike, eod_time: time, target_soc: float) -> bool:
    """Return True when end-of-day SOC target should be enforced."""

    if isinstance(current_time, datetime):
        current = current_time.time()
    else:
        current = current_time

    _ = target_soc
    return current >= eod_time
