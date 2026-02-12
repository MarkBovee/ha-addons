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

    def test_contains_profit_summary(self):
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234), PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
        )
        assert "💵 Profit" in result
        assert "/kWh" in result

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

    def test_with_profit_summary(self):
        result = build_tomorrow_story(
            PriceRange(0.20, 0.22), PriceRange(0.35, 0.40),
            PriceRange(0.22, 0.35),
        )
        assert "💵 Profit" in result
        assert "/kWh" in result

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

    def test_past_today_windows_still_included(self):
        """Past windows from today should be included (shown as completed)."""
        prices = [0.20, 0.21, 0.22] + [0.30] * 21
        curve = self._make_curve(prices)
        # now is past the cheap hours but same day
        now = datetime(2026, 2, 11, 5, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve, PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None, now,
        )
        assert len(result["charge"]) == 1  # Past charge window still included
        assert result["charge"][0]["start"].hour == 0
        assert result["charge"][0]["end"].hour == 3

    def test_yesterday_windows_excluded(self):
        """Windows from yesterday should be excluded."""
        prices = [0.20, 0.21, 0.22] + [0.30] * 21
        # Curve starts on Feb 10 (yesterday)
        base = datetime(2026, 2, 10, 0, 0, tzinfo=timezone.utc)
        curve = [
            {
                "start": (base + timedelta(hours=i)).isoformat(),
                "end": (base + timedelta(hours=i + 1)).isoformat(),
                "price": p,
            }
            for i, p in enumerate(prices)
        ]
        # now is the next day
        now = datetime(2026, 2, 11, 5, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve, PriceRange(0.20, 0.22), PriceRange(0.35, 0.40), None, now,
        )
        assert len(result["charge"]) == 0  # Yesterday's windows excluded

    def test_empty_curve(self):
        result = find_upcoming_windows([], None, None, None, None, datetime.now(timezone.utc))
        assert result == {"charge": [], "discharge": [], "adaptive": []}

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

    def test_tomorrow_uses_separate_ranges(self):
        """Tomorrow's slots should use tomorrow's ranges, not today's."""
        # Today (Feb 11): cheapest 3h at 0.231-0.234
        today_prices = [0.231, 0.232, 0.234] + [0.28] * 21
        # Tomorrow (Feb 12): cheapest 3h at 0.234-0.237
        tomorrow_prices = [0.237, 0.237, 0.234] + [0.28] * 21
        base_today = datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc)
        base_tomorrow = datetime(2026, 2, 12, 0, 0, tzinfo=timezone.utc)

        curve = [
            {"start": (base_today + timedelta(hours=i)).isoformat(),
             "end": (base_today + timedelta(hours=i + 1)).isoformat(),
             "price": p}
            for i, p in enumerate(today_prices)
        ] + [
            {"start": (base_tomorrow + timedelta(hours=i)).isoformat(),
             "end": (base_tomorrow + timedelta(hours=i + 1)).isoformat(),
             "price": p}
            for i, p in enumerate(tomorrow_prices)
        ]

        now = datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc)
        today_load = PriceRange(0.231, 0.234)
        tomorrow_load = PriceRange(0.234, 0.237)  # Wider range for tomorrow

        result = find_upcoming_windows(
            curve, curve, today_load, None, None, now,
            tomorrow_load_range=tomorrow_load,
        )
        # Today: 3 charge slots (0.231, 0.232, 0.234)
        # Tomorrow: 3 charge slots (0.237, 0.237, 0.234) — all within 0.234-0.237
        today_windows = [w for w in result["charge"] if w["start"].day == 11]
        tomorrow_windows = [w for w in result["charge"] if w["start"].day == 12]
        assert len(today_windows) == 1  # Grouped into 1 window
        assert len(tomorrow_windows) >= 1  # Tomorrow has windows too

        # Count total tomorrow charge hours
        total_tomorrow_hours = sum(
            int((w["end"] - w["start"]).total_seconds() / 3600)
            for w in tomorrow_windows
        )
        assert total_tomorrow_hours == 3  # All 3 hours qualify with tomorrow's range


class TestBuildWindowsDisplay:
    def test_no_windows(self):
        result = build_windows_display([], "charge", 8000, datetime.now(timezone.utc))
        assert result == "No charge windows today"

    def test_no_windows_with_reason(self):
        result = build_windows_display(
            [], "discharge", 6000, datetime.now(timezone.utc),
            no_range_reason="📉 No profitable discharge today (spread €0.062 < €0.10 minimum)",
        )
        assert "No profitable discharge" in result
        assert "spread" in result

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

    def test_tomorrow_label_shown(self):
        """When windows span today and tomorrow, a 'Tomorrow' label should appear."""
        now = datetime(2026, 2, 11, 14, 0, tzinfo=timezone.utc)
        windows = [
            {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
             "avg_price": 0.231},
            {"start": datetime(2026, 2, 12, 2, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 12, 3, 0, tzinfo=timezone.utc),
             "avg_price": 0.234},
        ]
        result = build_windows_display(windows, "charge", 8000, now)
        assert "Tomorrow" in result

    def test_no_tomorrow_label_for_today_only(self):
        """When all windows are today, no 'Tomorrow' label."""
        now = datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc)
        windows = [
            {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
             "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
             "avg_price": 0.231},
        ]
        result = build_windows_display(windows, "charge", 8000, now)
        assert "Tomorrow" not in result


class TestBuildCombinedScheduleDisplay:
    def test_empty(self):
        result = build_combined_schedule_display(
            {"charge": [], "discharge": []}, 8000, 6000, datetime.now(timezone.utc),
        )
        assert "No scheduled windows today" in result

    def test_empty_with_no_discharge_reason(self):
        result = build_combined_schedule_display(
            {"charge": [], "discharge": []}, 8000, 6000, datetime.now(timezone.utc),
            no_discharge_reason="📉 No profitable discharge (spread €0.062 < €0.10)",
        )
        assert "No profitable discharge" in result
        assert "No scheduled windows today" in result

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

    def test_tomorrow_label_in_combined(self):
        now = datetime(2026, 2, 11, 14, 0, tzinfo=timezone.utc)
        windows = {
            "charge": [
                {"start": datetime(2026, 2, 11, 0, 0, tzinfo=timezone.utc),
                 "end": datetime(2026, 2, 11, 3, 0, tzinfo=timezone.utc),
                 "avg_price": 0.231},
                {"start": datetime(2026, 2, 12, 2, 0, tzinfo=timezone.utc),
                 "end": datetime(2026, 2, 12, 5, 0, tzinfo=timezone.utc),
                 "avg_price": 0.234},
            ],
            "discharge": [],
        }
        result = build_combined_schedule_display(windows, 8000, 6000, now)
        assert "**Tomorrow**" in result


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


class TestFindUpcomingWindowsAdaptive:
    """Tests for adaptive window detection in find_upcoming_windows."""

    def _make_curve(self, prices, start_hour=0):
        base = datetime(2026, 2, 11, start_hour, 0, tzinfo=timezone.utc)
        return [
            {
                "start": (base + timedelta(hours=i)).isoformat(),
                "end": (base + timedelta(hours=i + 1)).isoformat(),
                "price": p,
            }
            for i, p in enumerate(prices)
        ]

    def test_adaptive_windows_detected(self):
        """Slots above threshold but not in load/discharge should be adaptive."""
        # 0-2: load (cheap), 3-5: adaptive (above threshold), 6: passive (below threshold), 17-19: discharge
        prices = [0.20, 0.21, 0.22, 0.28, 0.29, 0.30, 0.24] + [0.28] * 10 + [0.36, 0.37, 0.38] + [0.28] * 4
        curve = self._make_curve(prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve,
            PriceRange(0.20, 0.22),   # load
            PriceRange(0.35, 0.40),   # discharge
            0.27,                      # threshold — below this is passive
            now,
        )
        assert len(result["charge"]) >= 1
        assert len(result["discharge"]) >= 1
        assert len(result["adaptive"]) >= 1
        # Hours 3-5 (0.28, 0.29, 0.30) are above threshold 0.27 → adaptive
        adaptive_starts = [w["start"].hour for w in result["adaptive"]]
        assert 3 in adaptive_starts or any(w["start"].hour <= 3 and w["end"].hour >= 4 for w in result["adaptive"])

    def test_no_adaptive_without_threshold(self):
        """Without threshold, no adaptive windows should be created."""
        prices = [0.20, 0.21, 0.22] + [0.28] * 14 + [0.36, 0.37, 0.38] + [0.28] * 4
        curve = self._make_curve(prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve,
            PriceRange(0.20, 0.22),
            PriceRange(0.35, 0.40),
            None,  # no threshold
            now,
        )
        assert result["adaptive"] == []

    def test_passive_below_threshold_not_adaptive(self):
        """Slots below the threshold should NOT be adaptive."""
        # Hours 0-2: load (0.20-0.22), hours 3-4: passive (0.25, 0.26 — below 0.27 threshold)
        # Hours 5-23: all 0.26 — also below threshold, so passive too
        prices = [0.20, 0.21, 0.22, 0.25, 0.26] + [0.26] * 19
        curve = self._make_curve(prices)
        now = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)

        result = find_upcoming_windows(
            curve, curve,
            PriceRange(0.20, 0.22),
            PriceRange(0.35, 0.40),
            0.27,  # All non-load prices are below threshold → no adaptive
            now,
        )
        assert result["adaptive"] == []


class TestBuildTodayStoryPassiveBalancingSplit:
    """Tests for passive/balancing split in build_today_story."""

    def test_split_when_threshold_in_adaptive_range(self):
        """When threshold splits adaptive range, both passive and balancing shown."""
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234),   # load
            PriceRange(0.331, 0.341),   # discharge
            PriceRange(0.234, 0.331),   # adaptive range
            charging_price_threshold=0.27,
        )
        assert "💤 Passive" in result
        assert "⚖️ Balancing" in result
        assert "€0.234" in result  # passive start
        assert "€0.270" in result  # passive end / balancing start
        assert "€0.331" in result  # balancing end

    def test_no_split_without_threshold(self):
        """Without threshold, show full adaptive as balancing."""
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234),
            PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
            charging_price_threshold=None,
        )
        assert "⚖️ Balancing" in result
        assert "💤 Passive" not in result

    def test_threshold_at_bottom_of_range(self):
        """When threshold is at or below adaptive min, no passive section."""
        result = build_today_story(
            "adaptive", 0.276, 0.291,
            PriceRange(0.231, 0.234),
            PriceRange(0.331, 0.341),
            PriceRange(0.234, 0.331),
            charging_price_threshold=0.234,  # At adaptive min
        )
        assert "⚖️ Balancing" in result
        assert "💤 Passive" not in result


class TestBuildPriceRangesDisplayPassiveBalancingSplit:
    """Tests for passive/balancing split in build_price_ranges_display."""

    def test_split_with_threshold(self):
        result = build_price_ranges_display(
            PriceRange(0.20, 0.22),
            PriceRange(0.35, 0.40),
            PriceRange(0.22, 0.35),
            charging_price_threshold=0.27,
        )
        assert "Passive:" in result
        assert "Adaptive:" in result
        assert "€0.220–0.270" in result  # passive portion
        assert "€0.270–0.350" in result  # adaptive portion

    def test_no_split_without_threshold(self):
        result = build_price_ranges_display(
            PriceRange(0.20, 0.22),
            PriceRange(0.35, 0.40),
            PriceRange(0.22, 0.35),
        )
        assert "Adaptive:" in result
        assert "Passive:" not in result
