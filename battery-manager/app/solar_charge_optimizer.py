"""Helpers for forecast-assisted charge power allocation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SolarAwareChargeAllocation:
    """Allocation result for solar-aware charge slots."""

    applied: bool
    slot_powers: Dict[str, int]
    slot_solar_kwh: Dict[str, float]
    usable_solar_kwh: float
    grid_energy_target_kwh: float
    remaining_grid_energy_kwh: float


def parse_remaining_solar_energy_kwh(entity_state: Optional[Dict[str, Any]]) -> Optional[float]:
    """Convert a Home Assistant remaining-solar sensor state to kWh.

    The source sensor is expected to represent a remaining energy budget for today.
    Some installs expose that as `kWh`, others as `Wh` or `W`; the latter two are
    interpreted as watt-hour style totals and divided by 1000.
    """

    if not entity_state:
        return None

    try:
        raw_value = float(entity_state.get("state"))
    except (TypeError, ValueError):
        return None

    if raw_value <= 0:
        return 0.0

    attributes = entity_state.get("attributes", {}) or {}
    unit = str(
        attributes.get("unit_of_measurement")
        or attributes.get("unit")
        or ""
    ).strip().lower()

    if unit == "kwh":
        return raw_value
    if unit in {"wh", "w", "watt", "watts", ""}:
        return raw_value / 1000.0
    return raw_value / 1000.0


def calculate_charge_deficit_kwh(
    current_soc: Optional[float],
    target_soc: float,
    battery_capacity_kwh: float,
) -> float:
    """Calculate the remaining battery energy needed to reach target SOC."""

    if current_soc is None or battery_capacity_kwh <= 0:
        return 0.0

    bounded_soc = max(0.0, min(float(current_soc), 100.0))
    bounded_target = max(0.0, min(float(target_soc), 100.0))
    if bounded_target <= bounded_soc:
        return 0.0

    return ((bounded_target - bounded_soc) / 100.0) * float(battery_capacity_kwh)


def allocate_solar_aware_charge_powers(
    slots: List[Dict[str, Any]],
    charge_deficit_kwh: float,
    remaining_solar_kwh: float,
    min_charge_power_w: int,
    forecast_safety_factor: float,
) -> SolarAwareChargeAllocation:
    """Allocate today's grid charge power while reserving room for expected PV.

    `slots` must contain `start`, `end`, and `base_power`. `base_power` acts as the
    ceiling that preserves the existing ranked charge behavior when more grid power
    is still needed.
    """

    valid_slots: List[Dict[str, Any]] = []
    total_hours = 0.0
    for slot in slots:
        start_dt = slot.get("start")
        end_dt = slot.get("end")
        base_power = slot.get("base_power")
        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
            continue
        if not isinstance(base_power, (int, float)) or base_power <= 0:
            continue
        duration_hours = max((end_dt - start_dt).total_seconds() / 3600.0, 0.0)
        if duration_hours <= 0:
            continue
        valid_slots.append(slot)
        total_hours += duration_hours

    if charge_deficit_kwh <= 0 or not valid_slots or total_hours <= 0:
        return SolarAwareChargeAllocation(False, {}, {}, 0.0, 0.0, 0.0)

    safety_factor = max(0.0, min(float(forecast_safety_factor), 1.0))
    usable_solar_kwh = min(max(0.0, float(remaining_solar_kwh)) * safety_factor, charge_deficit_kwh)
    grid_energy_target_kwh = max(0.0, charge_deficit_kwh - usable_solar_kwh)

    slot_solar_kwh: Dict[str, float] = {}
    for slot in valid_slots:
        duration_hours = max((slot["end"] - slot["start"]).total_seconds() / 3600.0, 0.0)
        slot_key = slot["start"].isoformat()
        slot_solar_kwh[slot_key] = round(usable_solar_kwh * (duration_hours / total_hours), 3)

    if grid_energy_target_kwh <= 0:
        return SolarAwareChargeAllocation(True, {}, slot_solar_kwh, usable_solar_kwh, 0.0, 0.0)

    slot_powers: Dict[str, int] = {}
    remaining_grid_kwh = grid_energy_target_kwh
    remaining_hours = total_hours
    min_power = max(0, int(min_charge_power_w))

    for slot in valid_slots:
        slot_hours = max((slot["end"] - slot["start"]).total_seconds() / 3600.0, 0.0)
        if slot_hours <= 0:
            continue

        base_power = int(slot["base_power"])
        average_power_w = math.ceil((remaining_grid_kwh / max(remaining_hours, slot_hours)) * 1000.0)
        power_w = min(base_power, max(min_power, average_power_w))
        if power_w <= 0:
            remaining_hours = max(0.0, remaining_hours - slot_hours)
            continue

        slot_key = slot["start"].isoformat()
        slot_powers[slot_key] = power_w
        remaining_grid_kwh = max(0.0, remaining_grid_kwh - ((power_w / 1000.0) * slot_hours))
        remaining_hours = max(0.0, remaining_hours - slot_hours)

        if remaining_grid_kwh <= 0:
            break

    return SolarAwareChargeAllocation(
        True,
        slot_powers,
        slot_solar_kwh,
        round(usable_solar_kwh, 3),
        round(grid_energy_target_kwh, 3),
        round(remaining_grid_kwh, 3),
    )