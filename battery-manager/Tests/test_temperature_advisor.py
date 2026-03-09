"""Tests for temperature-based discharge duration selection."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.temperature_advisor import get_discharge_hours


def test_get_discharge_hours_preserves_fractional_threshold_values():
    thresholds = [
        {"temp_max": 0, "discharge_hours": 1},
        {"temp_max": 8, "discharge_hours": 1.5},
        {"temp_max": 12, "discharge_hours": 2},
        {"temp_max": 16, "discharge_hours": 2.5},
        {"temp_max": 999, "discharge_hours": 3},
    ]

    assert get_discharge_hours(7.0, thresholds) == 1.5
    assert get_discharge_hours(14.0, thresholds) == 2.5


def test_get_discharge_hours_uses_float_default_when_temperature_missing():
    assert get_discharge_hours(None, [], default_hours=2.5) == 2.5