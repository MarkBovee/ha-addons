"""Tests for negative price charging optimizations.

Covers:
- _determine_price_range() always returns "load" for negative import prices
- find_upcoming_windows() includes negative-price slots outside load_range
- generate_schedule() prioritizes negative-price windows at proportionally-scaled power
  (most-negative price → max_charge_power; less-negative → proportionally lower, floor=min_scaled_power)
- generate_schedule() bypasses solar-aware reduction for negative-price slots
"""

import sys
import os
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.price_analyzer import PriceRange
from app.main import _determine_price_range
from app.status_reporter import find_upcoming_windows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_curve(prices, base: datetime):
    return [
        {
            "start": (base + timedelta(hours=i)).isoformat(),
            "end": (base + timedelta(hours=i + 1)).isoformat(),
            "price": p,
        }
        for i, p in enumerate(prices)
    ]


# ---------------------------------------------------------------------------
# _determine_price_range — negative price always returns "load"
# ---------------------------------------------------------------------------

class TestDetermineRangeNegativePrice:
    def test_negative_price_returns_load_with_no_ranges(self):
        result = _determine_price_range(-0.10, -0.10, None, None)
        assert result == "load"

    def test_negative_price_returns_load_overriding_adaptive(self):
        load_range = PriceRange(0.05, 0.15)
        discharge_range = PriceRange(0.30, 0.50)
        # Import price is negative — outside load_range, but should still be "load"
        result = _determine_price_range(-0.05, -0.05, load_range, discharge_range)
        assert result == "load"

    def test_negative_price_returns_load_overriding_passive(self):
        load_range = PriceRange(0.05, 0.15)
        # Below adaptive_price_threshold would normally be "passive"
        result = _determine_price_range(
            -0.02, -0.02, load_range, None,
            adaptive_price_threshold=0.25,
        )
        assert result == "load"

    def test_negative_price_returns_load_overriding_discharge(self):
        # Even if export price is in discharge range, negative import → "load"
        discharge_range = PriceRange(0.30, 0.50)
        result = _determine_price_range(-0.10, 0.40, None, discharge_range)
        assert result == "load"

    def test_zero_price_not_affected(self):
        """Price of exactly 0 is not negative, should follow normal rules."""
        load_range = PriceRange(0.05, 0.15)
        result = _determine_price_range(0.0, 0.0, load_range, None)
        # 0.0 is not in load_range (0.05-0.15), not in discharge, → adaptive
        assert result == "adaptive"

    def test_small_negative_returns_load(self):
        result = _determine_price_range(-0.001, -0.001, None, None)
        assert result == "load"

    def test_positive_price_unchanged(self):
        load_range = PriceRange(0.10, 0.20)
        result = _determine_price_range(0.15, 0.15, load_range, None)
        assert result == "load"


# ---------------------------------------------------------------------------
# find_upcoming_windows — negative price always in charge windows
# ---------------------------------------------------------------------------

class TestFindUpcomingWindowsNegativePrice:
    """Negative-price slots must appear as charge windows even outside load_range."""

    def _now(self):
        return datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc)

    def test_negative_price_outside_load_range_becomes_charge_window(self):
        """4 hours of negative prices, top_x selects only 3: 4th should still appear."""
        base = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)
        # 4 negative hours, then positive
        prices = [-0.30, -0.28, -0.25, -0.10, 0.25, 0.25, 0.25, 0.25,
                  0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
                  0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25]
        curve = _make_curve(prices, base)
        now = self._now()

        # load_range only covers the 3 most negative prices (top_x=3)
        load_range = PriceRange(min_price=-0.30, max_price=-0.25)

        result = find_upcoming_windows(
            curve, curve, load_range, None, None, now,
        )
        # All 4 negative hours should appear, grouped into 1 window
        assert len(result["charge"]) == 1
        charge_win = result["charge"][0]
        # Window spans all 4 hours (00:00-04:00)
        assert charge_win["start"].hour == 0
        assert charge_win["end"].hour == 4

    def test_negative_price_window_has_correct_avg_price(self):
        base = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)
        prices = [-0.20, -0.20, 0.30] + [0.25] * 21
        curve = _make_curve(prices, base)
        now = self._now()

        load_range = PriceRange(min_price=-0.20, max_price=-0.20)

        result = find_upcoming_windows(
            curve, curve, load_range, None, None, now,
        )
        assert len(result["charge"]) == 1
        assert pytest.approx(result["charge"][0]["avg_price"]) == -0.20

    def test_negative_price_slots_included_when_no_load_range(self):
        """Even with load_range=None, negative-price slots should be charge windows."""
        base = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)
        prices = [-0.15, -0.10, 0.25] + [0.25] * 21
        curve = _make_curve(prices, base)
        now = self._now()

        result = find_upcoming_windows(
            curve, curve, None, None, None, now,
        )
        assert len(result["charge"]) == 1
        assert result["charge"][0]["avg_price"] < 0

    def test_positive_prices_outside_load_range_not_added(self):
        """Positive prices outside load_range should NOT appear as charge windows."""
        base = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)
        prices = [0.10, 0.25, 0.30] + [0.25] * 21
        curve = _make_curve(prices, base)
        now = self._now()

        load_range = PriceRange(min_price=0.10, max_price=0.10)

        result = find_upcoming_windows(
            curve, curve, load_range, None, None, now,
        )
        # Only 0.10 in range; 0.25 and 0.30 are positive and outside → not charge
        assert len(result["charge"]) == 1
        assert result["charge"][0]["avg_price"] == pytest.approx(0.10)

    def test_negative_price_separate_from_positive_cheap(self):
        """Negative and positive cheap blocks should form separate windows if non-consecutive."""
        base = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)
        # Hours 0-1: cheap positive, hours 2-9: mid, hours 10-12: negative
        prices = [0.10, 0.11, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
                  -0.20, -0.15, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25,
                  0.25, 0.25, 0.25, 0.25]
        curve = _make_curve(prices, base)
        now = self._now()

        load_range = PriceRange(min_price=0.10, max_price=0.11)

        result = find_upcoming_windows(
            curve, curve, load_range, None, None, now,
        )
        # Should have 2 charge windows: one positive-cheap, one negative
        assert len(result["charge"]) == 2
        windows_by_start = sorted(result["charge"], key=lambda w: w["start"])
        assert windows_by_start[0]["avg_price"] > 0  # cheap positive
        assert windows_by_start[1]["avg_price"] < 0  # negative price


# ---------------------------------------------------------------------------
# generate_schedule — integration via monkeypatch
# ---------------------------------------------------------------------------

import app.main as bm_main
from copy import deepcopy


class TestGenerateScheduleNegativePrice:
    """Integration tests for negative price charging in generate_schedule()."""

    def _make_config(self, neg_price_enabled=True):
        config = deepcopy(bm_main.DEFAULT_CONFIG)
        config["negative_price_charging"] = {"enabled": neg_price_enabled}
        config["solar_aware_charging"]["enabled"] = False
        config["dry_run"] = True
        config["adaptive"]["enabled"] = False
        config["soc"]["min_soc"] = 5
        config["soc"]["conservative_soc"] = 20
        config["soc"]["max_soc"] = 99
        config["soc"]["battery_capacity_kwh"] = 25
        config["soc"]["sell_buffer_enabled"] = False
        config["heuristics"]["top_x_charge_hours"] = 2
        config["heuristics"]["top_x_discharge_hours"] = 1
        config["heuristics"]["min_profit_threshold"] = 0.10
        config["heuristics"]["overnight_wait_threshold"] = 0.02
        config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
        config["heuristics"]["adaptive_price_threshold"] = 0.25
        config["temperature_based_discharge"]["enabled"] = False
        config["passive_solar"]["enabled"] = False
        return config

    def _make_future_curve(self, prices_for_future_hours, now=None):
        """Build a curve where the first entry starts 1h from now."""
        if now is None:
            now = datetime.now(timezone.utc)
        # Start 1h into the future so all slots are upcoming
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return [
            {
                "start": (start + timedelta(hours=i)).isoformat(),
                "end": (start + timedelta(hours=i + 1)).isoformat(),
                "price": p,
            }
            for i, p in enumerate(prices_for_future_hours)
        ]

    def test_negative_price_slots_have_window_type_negative_price_charge(self, monkeypatch):
        # 2 cheap hours, then 4 negative hours — top_x=2 would only pick 2h normally
        # but negative prices should all appear as negative_price_charge windows
        prices = [0.22, 0.21, 0.28, 0.28, -0.30, -0.25, -0.20, -0.10,
                  0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28]
        curve = self._make_future_curve(prices)
        config = self._make_config()

        monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, e: 60.0 if "soc" in e else 12.0)
        monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 60.0)
        monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

        schedule = bm_main.generate_schedule(config, object(), None)

        neg_windows = [p for p in schedule.get("charge", []) if p.get("window_type") == "negative_price_charge"]
        assert len(neg_windows) >= 1, f"Expected negative_price_charge window, got: {schedule.get('charge')}"

    def test_most_negative_slot_uses_max_charge_power(self, monkeypatch):
        """The most-negative price slot must always charge at max power."""
        prices = [0.22, 0.21, 0.28, -0.30, -0.25, -0.20,
                  0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28]
        curve = self._make_future_curve(prices)
        config = self._make_config()
        max_charge_power = config["power"]["max_charge_power"]

        monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, e: 60.0 if "soc" in e else 12.0)
        monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 60.0)
        monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

        schedule = bm_main.generate_schedule(config, object(), None)

        neg_slots = [p for p in schedule.get("charge", []) if p.get("window_type") == "negative_price_charge"]
        assert len(neg_slots) >= 1
        # The most-negative slot (-0.30) must run at max power
        most_neg = min(neg_slots, key=lambda p: p["price"])
        assert most_neg["power"] == max_charge_power, (
            f"Most-negative slot power {most_neg['power']}W != max {max_charge_power}W"
        )

    def test_proportional_power_scaling(self, monkeypatch):
        """Less-negative prices charge at proportionally lower power than the deepest slot."""
        # -0.40 is reference (max power), -0.20 is half as negative → ~50% power
        prices = [0.22, 0.21, 0.28, -0.20, 0.28, -0.40,
                  0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28]
        curve = self._make_future_curve(prices)
        config = self._make_config()
        max_charge_power = config["power"]["max_charge_power"]  # 8000W
        min_scaled_power = config["power"]["min_scaled_power"]   # 2500W

        monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, e: 60.0 if "soc" in e else 12.0)
        monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 60.0)
        monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

        schedule = bm_main.generate_schedule(config, object(), None)

        neg_slots = [p for p in schedule.get("charge", []) if p.get("window_type") == "negative_price_charge"]
        by_price = {round(p["price"], 2): p["power"] for p in neg_slots}

        # -0.40 slot: ratio=1.0 → max_charge_power
        assert by_price[-0.40] == max_charge_power, f"-0.40 slot: expected {max_charge_power}W, got {by_price[-0.40]}W"
        # -0.20 slot: ratio=0.5 → round(8000 * 0.5, -2) = 4000W
        expected_low = max(min_scaled_power, round(max_charge_power * 0.20 / 0.40, -2))
        assert by_price[-0.20] == expected_low, f"-0.20 slot: expected {expected_low}W, got {by_price[-0.20]}W"
        # More negative always charges harder
        assert by_price[-0.40] > by_price[-0.20]

    def test_negative_price_slots_not_solar_aware(self, monkeypatch):
        prices = [0.22, 0.21, 0.28, -0.30, -0.25,
                  0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28]
        curve = self._make_future_curve(prices)
        config = self._make_config()
        config["solar_aware_charging"]["enabled"] = True  # enable to verify it's bypassed

        monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, e: 60.0 if "soc" in e else 12.0)
        monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 60.0)
        # Large remaining solar that would normally suppress grid charge
        monkeypatch.setattr(bm_main, "_get_remaining_solar_energy_kwh", lambda *_a: 20.0)
        monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

        schedule = bm_main.generate_schedule(config, object(), None)
        max_charge_power = config["power"]["max_charge_power"]

        for period in schedule.get("charge", []):
            if period.get("window_type") == "negative_price_charge":
                assert period.get("solar_aware") is False
                # Power is not 0 and not reduced by solar — exact value depends on
                # price ratio scaling, so we just verify it's a sane positive value
                assert period["power"] >= config["power"]["min_scaled_power"]

    def test_negative_price_windows_take_priority_over_regular(self, monkeypatch):
        """With MAX_CHARGE_PERIODS=3, negative-price windows fill slots first."""
        # 2 cheap positive + 2 negative → all 3 slots: neg wins over cheap positive
        prices = [0.15, 0.16, 0.28, -0.30, -0.25,
                  0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28]
        curve = self._make_future_curve(prices)
        config = self._make_config()

        monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, e: 60.0 if "soc" in e else 12.0)
        monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 60.0)
        monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

        schedule = bm_main.generate_schedule(config, object(), None)

        neg_windows = [p for p in schedule.get("charge", []) if p.get("window_type") == "negative_price_charge"]
        assert len(neg_windows) >= 1, "Negative price window must be scheduled"
        assert len(schedule.get("charge", [])) <= bm_main.MAX_CHARGE_PERIODS

    def test_negative_price_disabled_no_extra_windows(self, monkeypatch):
        """When disabled, extra negative-price slots are not forced as negative_price_charge."""
        prices = [0.22, 0.21, 0.28, -0.30, -0.25, -0.20, -0.10,
                  0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28]
        curve = self._make_future_curve(prices)
        config = self._make_config(neg_price_enabled=False)

        monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: curve)
        monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, e: 60.0 if "soc" in e else 12.0)
        monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 60.0)
        monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

        schedule = bm_main.generate_schedule(config, object(), None)

        neg_windows = [p for p in schedule.get("charge", []) if p.get("window_type") == "negative_price_charge"]
        assert len(neg_windows) == 0, "When disabled, no negative_price_charge windows should appear"

