"""Tests for solar-aware charge allocation helpers."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.solar_charge_optimizer import (
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