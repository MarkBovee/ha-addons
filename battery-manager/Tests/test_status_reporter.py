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
    get_temperature_icon,
    update_entity,
)


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
