"""Tests for status_reporter module."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta
from app.status_reporter import (
    build_status_message,
    build_next_event_summary,
    build_schedule_display,
    build_schedule_markdown,
    build_today_story,
    build_tomorrow_story,
    build_price_ranges_display,
    build_windows_display,
    build_combined_schedule_display,
    find_upcoming_windows,
    _serialize_windows,
    _group_consecutive_slots,
    get_temperature_icon,
    update_entity,
)
from app.price_analyzer import PriceRange


class TestGetTemperatureIcon:
    def test_none(self):
        assert get_temperature_icon(None) == ""

    def test_sub_zero(self):
        assert get_temperature_icon(-5.0) == "❄️"

    def test_cold(self):
        assert get_temperature_icon(3.0) == "🥶"

    def test_cool(self):
        assert get_temperature_icon(14.0) == "🌥️"

    def test_warm(self):
        assert get_temperature_icon(18.0) == "🌤️"

    def test_hot(self):
        assert get_temperature_icon(25.0) == "☀️"


class TestBuildStatusMessage:
    def test_charging_active(self):
        msg = build_status_message("load", True, False, 8000, None, 20.0)
        assert "Charging Active" in msg
        assert "8000W" in msg

    def test_discharging_active(self):
        msg = build_status_message("discharge", False, True, None, 6000, 18.0)
        assert "Discharging Active" in msg
        assert "6000W" in msg

    def test_idle(self):
        msg = build_status_message("adaptive", False, False, None, None, 14.0)
        assert "Idle" in msg
        assert "Adaptive" in msg

    def test_paused(self):
        msg = build_status_message("load", False, True, None, None, None, paused=True, pause_reason="EV Charging")
        assert "Paused" in msg
        assert "EV Charging" in msg

    def test_reduced(self):
        msg = build_status_message("adaptive", False, True, None, None, None, reduced=True, pause_reason="High Export")
        assert "Reduced" in msg


class TestBuildScheduleDisplay:
    def test_no_periods(self):
        result = build_schedule_display({"charge": []}, "charge", datetime.now(timezone.utc))
        assert "No charge planned" in result

    def test_active_period(self):
        now = datetime.now(timezone.utc)
        schedule = {
            "charge": [{
                "start": (now - timedelta(minutes=5)).isoformat(),
                "duration": 60,
                "power": 8000,
            }]
        }
        result = build_schedule_display(schedule, "charge", now)
        assert "Active" in result
        assert "8000W" in result

    def test_next_period(self):
        now = datetime.now(timezone.utc)
        schedule = {
            "discharge": [{
                "start": (now + timedelta(hours=2)).isoformat(),
                "duration": 60,
                "power": 6000,
            }]
        }
        result = build_schedule_display(schedule, "discharge", now)
        assert "Next" in result
        assert "6000W" in result


class TestBuildScheduleMarkdown:
    def test_empty_schedule(self):
        result = build_schedule_markdown({"charge": [], "discharge": []}, datetime.now(timezone.utc))
        assert result == "No schedule"

    def test_table_format(self):
        now = datetime.now(timezone.utc)
        schedule = {
            "charge": [{
                "start": (now + timedelta(hours=1)).isoformat(),
                "duration": 15,
                "power": 8000,
            }],
            "discharge": [],
        }
        result = build_schedule_markdown(schedule, now)
        assert "|Time|Type|Power|" in result
        assert "⚡ Charge" in result
        assert "8000W" in result


class TestBuildNextEventSummary:
    def test_no_upcoming(self):
        now = datetime.now(timezone.utc)
        result = build_next_event_summary({"charge": [], "discharge": []}, now)
        assert "No upcoming" in result

    def test_with_upcoming(self):
        now = datetime.now(timezone.utc)
        schedule = {
            "charge": [{
                "start": (now + timedelta(hours=1)).isoformat(),
                "duration": 15,
                "power": 8000,
            }],
            "discharge": [],
        }
        result = build_next_event_summary(schedule, now)
        assert "Charge" in result
        assert "8000W" in result


class TestUpdateEntityDryRun:
    def test_dry_run_does_not_raise(self):
        """update_entity with dry_run=True should not require an mqtt client."""
        update_entity(None, "status", "idle", dry_run=True)

    def test_none_mqtt_returns_silently(self):
        """update_entity with mqtt=None and dry_run=False returns without error."""
        update_entity(None, "status", "idle", dry_run=False)


class TestBuildTodayStory:
    def test_contains_market_header(self):
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234), PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
        )
        assert "Today's Energy Market" in result

    def test_contains_price_ranges(self):
        result = build_today_story(
            "load", 0.231, 0.241,
            PriceRange(0.231, 0.234), PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
        )
        assert "€0.231" in result
        assert "€0.341" in result

    def test_contains_spread(self):
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234), PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
        )
        assert "Spread" in result

    def test_contains_current_zone(self):
        now = datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc)
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234), PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331), now=now,
        )
        assert "10:00" in result
        assert "€0.276" in result

    def test_no_ranges_still_works(self):
        result = build_today_story("adaptive", 0.276, 0.291, None, None, None)
        assert "Today's Energy Market" in result
        assert "€0.276" in result


class TestBuildTomorrowStory:
    def test_no_data(self):
        result = build_tomorrow_story(None, None, None)
        assert "not yet available" in result

    def test_with_ranges(self):
        result = build_tomorrow_story(
            PriceRange(0.20, 0.22), PriceRange(0.35, 0.40),
            PriceRange(0.22, 0.35),
        )
        assert "Tomorrow's Forecast" in result
        assert "€0.200" in result
        assert "€0.400" in result

    def test_with_spread(self):
        result = build_tomorrow_story(
            PriceRange(0.20, 0.22), PriceRange(0.35, 0.40),
            PriceRange(0.22, 0.35),
        )
        assert "Spread" in result

    def test_first_charge_window(self):
        curve = [
            {"start": "2026-02-12T02:00:00+00:00", "price": 0.21},
            {"start": "2026-02-12T03:00:00+00:00", "price": 0.20},
        ]
        result = build_tomorrow_story(
            PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None,
            tomorrow_curve=curve,
        )
        assert "02:00" in result


class TestBuildPriceRangesDisplay:
    def test_all_ranges(self):
        result = build_price_ranges_display(
            PriceRange(0.231, 0.234), PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
        )
        assert "Load:" in result
        assert "Adaptive:" in result
        assert "Discharge:" in result

    def test_no_data(self):
        assert build_price_ranges_display(None, None, None) == "No price data"

    def test_with_threshold_no_adaptive(self):
        result = build_price_ranges_display(
            PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None,
            charging_price_threshold=0.26,
        )
        assert "Passive:" in result


class TestFindUpcomingWindows:
    """Tests for find_upcoming_windows() - scans price curve to find charge/discharge windows."""

    def _make_curve(self, prices, start_hour=0):
        """Build a 24h price curve with hourly entries starting at given UTC hour."""
        base = datetime(2026, 2, 11, start_hour, 0, tzinfo=timezone.utc)
        return [
            {
                "start": (base + timedelta(hours=i)).isoformat(),
                "end": (base + timedelta(hours=i + 1)).isoformat(),
                "price": p,
            }
            for i, p in enumerate(prices)
        ]

    def test_finds_charge_windows(self):
        # Hours 0-2 are cheap (in load range), rest are middle
        prices = [0.20, 0.21, 0.22] + [0.30] * 21
        curve = self._make_curve(prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)  # Before the curve

        result = find_upcoming_windows(
            curve, curve, PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None, now,
        )
        assert len(result["charge"]) == 1  # Grouped into 1 window
        assert result["charge"][0]["start"].hour == 0
        assert result["charge"][0]["end"].hour == 3

    def test_finds_discharge_windows(self):
        import_prices = [0.30] * 24
        export_prices = [0.25] * 7 + [0.38, 0.39, 0.40] + [0.25] * 14
        import_curve = self._make_curve(import_prices)
        export_curve = self._make_curve(export_prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            import_curve, export_curve, PriceRange(0.20, 0.22),
            PriceRange(0.35, 0.40), None, now,
        )
        assert len(result["discharge"]) == 1
        assert result["discharge"][0]["start"].hour == 7
        assert result["discharge"][0]["end"].hour == 10

    def test_skips_past_periods(self):
        prices = [0.20, 0.21, 0.22] + [0.30] * 21
        curve = self._make_curve(prices)
        # now is past the cheap hours
        now = datetime(2026, 2, 11, 5, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve, PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None, now,
        )
        assert len(result["charge"]) == 0

    def test_empty_curve(self):
        result = find_upcoming_windows([], None, None, None, None, datetime.now(timezone.utc))
        assert result == {"charge": [], "discharge": []}

    def test_non_consecutive_windows_grouped_separately(self):
        # Cheap at hours 0-1 and 22-23 (gap in between)
        prices = [0.20, 0.21] + [0.30] * 20 + [0.20, 0.21]
        curve = self._make_curve(prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve, PriceRange(0.20, 0.22), None, None, now,
        )
        assert len(result["charge"]) == 2  # Two separate windows

    def test_charge_and_discharge_in_same_curve(self):
        # Hours 0-2 cheap, hours 17-19 expensive
        prices = [0.20, 0.21, 0.22] + [0.28] * 14 + [0.36, 0.37, 0.38] + [0.28] * 4
        curve = self._make_curve(prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve, PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None, now,
        )
        assert len(result["charge"]) == 1
        assert len(result["discharge"]) == 1
        assert result["charge"][0]["start"].hour == 0
        assert result["discharge"][0]["start"].hour == 17


class TestBuildWindowsDisplay:
    def test_no_windows(self):
        result = build_windows_display([], "charge", 8000, datetime.now(timezone.utc))
        assert result == "No charge windows today"

    def test_upcoming_windows(self):
        now = datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc)
        windows = [
            {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
             "avg_price": 0.231},
            {"start": datetime(2026, 2, 11, 22, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 23, 0, tzinfo=timezone.utc),
             "avg_price": 0.234},
        ]
        result = build_windows_display(windows, "charge", 8000, now)
        assert "00:00" in result
        assert "03:00" in result
        assert "22:00" in result
        assert "8000W" in result
        assert "€0.231" in result
        # First window is past, second is upcoming
        assert "✅" in result  # past
        assert "⚡" in result  # upcoming

    def test_active_window(self):
        now = datetime(2026, 2, 11, 1, 30, tzinfo=timezone.utc)
        windows = [
            {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
             "avg_price": 0.231},
        ]
        result = build_windows_display(windows, "charge", 8000, now)
        assert "🔴" in result  # active

    def test_discharge_type(self):
        now = datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc)
        windows = [
            {"start": datetime(2026, 2, 11, 17, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 19, 0, tzinfo=timezone.utc),
             "avg_price": 0.380},
        ]
        result = build_windows_display(windows, "discharge", 6000, now)
        assert "No discharge" not in result
        assert "💰" in result
        assert "6000W" in result


class TestBuildCombinedScheduleDisplay:
    def test_empty(self):
        result = build_combined_schedule_display(
            {"charge": [], "discharge": []}, 8000, 6000, datetime.now(timezone.utc),
        )
        assert result == "No schedule"

    def test_combined_table(self):
        now = datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc)
        windows = {
            "charge": [
                {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
                 "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
                 "avg_price": 0.231},
            ],
            "discharge": [
                {"start": datetime(2026, 2, 11, 17, 0, tzinfo=timezone.utc),
                 "end": datetime(2026, 2, 11, 19, 0, tzinfo=timezone.utc),
                 "avg_price": 0.380},
            ],
        }
        result = build_combined_schedule_display(windows, 8000, 6000, now)
        assert "|Time|Type|Power|Price|" in result
        assert "⚡ Charge" in result
        assert "💰 Discharge" in result
        assert "8000W" in result
        assert "6000W" in result
        assert "€0.231" in result
        assert "€0.380" in result

    def test_ordered_by_time(self):
        now = datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc)
        windows = {
            "charge": [
                {"start": datetime(2026, 2, 11, 22, 0, tzinfo=timezone.utc),
                 "end": datetime(2026, 2, 11, 23, 0, tzinfo=timezone.utc),
                 "avg_price": 0.231},
            ],
            "discharge": [
                {"start": datetime(2026, 2, 11, 17, 0, tzinfo=timezone.utc),
                 "end": datetime(2026, 2, 11, 19, 0, tzinfo=timezone.utc),
                 "avg_price": 0.380},
            ],
        }
        result = build_combined_schedule_display(windows, 8000, 6000, now)
        lines = result.split("\n")
        data_lines = [l for l in lines if l.startswith("|") and "---" not in l and "Time" not in l]
        # Discharge at 17:00 should come before charge at 22:00
        assert "17:00" in data_lines[0]
        assert "22:00" in data_lines[1]


class TestGroupConsecutiveSlots:
    def test_single_slot(self):
        slots = [{"start_dt": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
                  "end_dt": datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc),
                  "price": 0.20}]
        result = _group_consecutive_slots(slots)
        assert len(result) == 1
        assert result[0]["avg_price"] == 0.20

    def test_consecutive_slots_grouped(self):
        slots = [
            {"start_dt": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end_dt": datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc),
             "price": 0.20},
            {"start_dt": datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc),
             "end_dt": datetime(2026, 2, 11, 2, 0, tzinfo=timezone.utc),
             "price": 0.22},
        ]
        result = _group_consecutive_slots(slots)
        assert len(result) == 1
        assert result[0]["start"].hour == 0
        assert result[0]["end"].hour == 2
        assert result[0]["avg_price"] == pytest.approx(0.21)

    def test_gap_splits_groups(self):
        slots = [
            {"start_dt": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end_dt": datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc),
             "price": 0.20},
            {"start_dt": datetime(2026, 2, 11, 5, 0, tzinfo=timezone.utc),
             "end_dt": datetime(2026, 2, 11, 6, 0, tzinfo=timezone.utc),
             "price": 0.21},
        ]
        result = _group_consecutive_slots(slots)
        assert len(result) == 2

    def test_empty(self):
        assert _group_consecutive_slots([]) == []


class TestSerializeWindows:
    def test_round_trip(self):
        windows = [
            {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
             "avg_price": 0.23145},
        ]
        result = _serialize_windows(windows)
        assert result[0]["start"] == "2026-02-11T00:00:00+00:00"
        assert result[0]["end"] == "2026-02-11T03:00:00+00:00"
        assert result[0]["avg_price"] == 0.2314  # rounded to 4 decimals
