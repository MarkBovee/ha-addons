"""Tests for soc_guardian module."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.soc_guardian import (
    calculate_sell_buffer_soc,
    calculate_soc_per_hour,
    can_charge,
    can_discharge,
)


class TestCanCharge:
    def test_below_max_allows_charge(self):
        assert can_charge(50.0, 100.0) is True

    def test_at_max_disallows(self):
        assert can_charge(100.0, 100.0) is False

    def test_above_max_disallows(self):
        assert can_charge(101.0, 100.0) is False


class TestCanDischarge:
    def test_above_conservative_allows(self):
        assert can_discharge(60.0, 5.0, 40.0, is_conservative=True) is True

    def test_below_min_blocks(self):
        assert can_discharge(4.0, 5.0, 40.0, is_conservative=False) is False

    def test_at_min_blocks(self):
        assert can_discharge(5.0, 5.0, 40.0, is_conservative=False) is False

    def test_above_min_non_conservative_allows(self):
        assert can_discharge(10.0, 5.0, 40.0, is_conservative=False) is True

    def test_below_conservative_with_flag_blocks(self):
        assert can_discharge(30.0, 5.0, 40.0, is_conservative=True) is False

    def test_below_conservative_without_flag_allows(self):
        assert can_discharge(30.0, 5.0, 40.0, is_conservative=False) is True


class TestSellBufferSoc:
    def test_soc_per_hour_from_power_and_capacity(self):
        # 8kW on 25kWh battery -> 32% SOC per hour
        assert calculate_soc_per_hour(8000, 25) == pytest.approx(32.0)

    def test_sell_buffer_one_hour(self):
        # 20% safety + 32%/h * 1h = 52% -> rounded to nearest 10% => 50%
        result = calculate_sell_buffer_soc(
            1.0, 20.0, 8000.0, 25.0, floor_soc=5.0, rounding_step_pct=10.0
        )
        assert result == pytest.approx(50.0)

    def test_sell_buffer_two_hours(self):
        # 20% safety + 32%/h * 2h = 84% -> rounded to nearest 10% => 80%
        result = calculate_sell_buffer_soc(
            2.0, 20.0, 8000.0, 25.0, floor_soc=5.0, rounding_step_pct=10.0
        )
        assert result == pytest.approx(80.0)

    def test_sell_buffer_clamped_to_100(self):
        result = calculate_sell_buffer_soc(
            4.0, 20.0, 8000.0, 25.0, floor_soc=5.0, rounding_step_pct=10.0
        )
        assert result == 100.0

    def test_sell_buffer_respects_floor(self):
        result = calculate_sell_buffer_soc(
            0.0, 2.0, 8000.0, 25.0, floor_soc=5.0, rounding_step_pct=10.0
        )
        assert result == 5.0

    def test_sell_buffer_without_rounding(self):
        result = calculate_sell_buffer_soc(
            1.0, 20.0, 8000.0, 25.0, floor_soc=5.0, rounding_step_pct=0.0
        )
        assert result == pytest.approx(52.0)
