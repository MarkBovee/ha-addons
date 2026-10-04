"""Tests for solar-aware charge allocation helpers."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.solar_charge_optimizer import (
    allocate_charge_powers,
    allocate_solar_aware_charge_powers,
    calculate_charge_deficit_kwh,
    parse_remaining_solar_energy_kwh,
)


def test_parse_remaining_solar_energy_handles_watt_totals():
    entity_state = {
        "state": "5000",
        "attributes": {"unit_of_measurement": "W"},
    }

    assert parse_remaining_solar_energy_kwh(entity_state) == 5.0


def test_calculate_charge_deficit_kwh_uses_target_soc():
    assert calculate_charge_deficit_kwh(50.0, 100.0, 12.0) == 6.0


def test_allocate_solar_aware_charge_powers_spreads_remaining_grid_need():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slots = [
        {"start": now, "end": now + timedelta(hours=1), "base_power": 4000},
        {"start": now + timedelta(hours=1), "end": now + timedelta(hours=2), "base_power": 6000},
        {"start": now + timedelta(hours=2), "end": now + timedelta(hours=3), "base_power": 8000},
    ]

    allocation = allocate_solar_aware_charge_powers(
        slots,
        charge_deficit_kwh=6.0,
        remaining_solar_kwh=3.0,
        min_charge_power_w=500,
        forecast_safety_factor=1.0,
    )

    assert allocation.applied is True
    assert allocation.grid_energy_target_kwh == 3.0
    assert list(allocation.slot_powers.values()) == [1000, 1000, 1000]


def test_allocate_solar_aware_charge_powers_can_skip_grid_slots_when_solar_covers_need():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slots = [
        {"start": now, "end": now + timedelta(hours=1), "base_power": 4000},
        {"start": now + timedelta(hours=1), "end": now + timedelta(hours=2), "base_power": 6000},
    ]

    allocation = allocate_solar_aware_charge_powers(
        slots,
        charge_deficit_kwh=2.0,
        remaining_solar_kwh=5.0,
        min_charge_power_w=500,
        forecast_safety_factor=1.0,
    )

    assert allocation.applied is True
    assert allocation.grid_energy_target_kwh == 0.0
    assert allocation.slot_powers == {}


def test_allocate_charge_powers_spreads_target_across_longer_window_set():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slots = [
        {"start": now, "end": now + timedelta(hours=3), "base_power": 8000},
        {"start": now + timedelta(hours=3), "end": now + timedelta(hours=6), "base_power": 8000},
    ]

    slot_powers = allocate_charge_powers(
        slots,
        target_grid_energy_kwh=24.0,
        min_charge_power_w=500,
    )

    assert list(slot_powers.values()) == [4000, 4000]


def test_live_grid_charge_power_drops_with_solar_surplus_and_floors_to_step():
    from app.solar_charge_optimizer import calculate_live_grid_charge_power

    # 20 kWh over 4 h = 5000 W required; no sun -> 5000 + 1000 buffer, capped at ceiling
    assert calculate_live_grid_charge_power(20.0, 4.0, 0, 8000) == 6000
    # 1750 W surplus -> 5000 - 1750 + 1000 = 4250 -> floored to 4000
    assert calculate_live_grid_charge_power(20.0, 4.0, 1750, 8000) == 4000
    # strong sun -> grid share goes to 0
    assert calculate_live_grid_charge_power(20.0, 4.0, 7700, 8000) == 0


def test_live_grid_charge_power_respects_ceiling_and_empty_deficit():
    from app.solar_charge_optimizer import calculate_live_grid_charge_power

    assert calculate_live_grid_charge_power(20.0, 1.0, 0, 3252) == 3252
    assert calculate_live_grid_charge_power(0.0, 4.0, 0, 8000) == 0
