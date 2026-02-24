"""Tests for solar_monitor module."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from app.solar_monitor import SolarMonitor


class FakeHaApi:
    """Fake HA API returning dict-based entity states."""

    def __init__(self, states: dict):
        self._states = states

    def get_entity_state(self, entity_id):
        return self._states.get(entity_id)


DEFAULT_CONFIG = {
    "entities": {
        "solar_power_entity": "sensor.pv_power",
        "grid_power_entity": "sensor.grid_power",
    },
    "passive_solar": {
        "enabled": True,
        "entry_threshold": 1000,
        "exit_threshold": 200,
        "min_solar_entry_power": 200,
    },
}


@pytest.fixture
def monitor():
    return SolarMonitor(DEFAULT_CONFIG, logging.getLogger("test"))


class TestSolarMonitor:
    """Tests use standard P1 sign convention: positive=import, negative=export."""

    def test_activates_on_high_export(self, monitor):
        ha = FakeHaApi({
            "sensor.pv_power": {"state": "3000"},
            "sensor.grid_power": {"state": "-1500"},  # negative = exporting
        })
        assert monitor.check_passive_state(ha) is True
        assert monitor.is_passive_active is True

    def test_stays_inactive_below_threshold(self, monitor):
        ha = FakeHaApi({
            "sensor.pv_power": {"state": "500"},
            "sensor.grid_power": {"state": "-500"},  # exporting but below 1000W threshold
        })
        assert monitor.check_passive_state(ha) is False

    def test_stays_inactive_when_importing(self, monitor):
        ha = FakeHaApi({
            "sensor.pv_power": {"state": "500"},
            "sensor.grid_power": {"state": "3000"},  # positive = importing
        })
        assert monitor.check_passive_state(ha) is False

    def test_stays_inactive_on_high_export_with_low_solar(self, monitor):
        ha = FakeHaApi({
            "sensor.pv_power": {"state": "12"},
            "sensor.grid_power": {"state": "-2317"},  # heavy export from other sources
        })
        assert monitor.check_passive_state(ha) is False
        assert monitor.is_passive_active is False

    def test_deactivates_on_grid_import(self, monitor):
        # Activate first with heavy export
        ha_export = FakeHaApi({
            "sensor.pv_power": {"state": "3000"},
            "sensor.grid_power": {"state": "-1500"},  # negative = exporting
        })
        monitor.check_passive_state(ha_export)

        # Now grid importing (positive value)
        ha_import = FakeHaApi({
            "sensor.pv_power": {"state": "1000"},
            "sensor.grid_power": {"state": "300"},  # positive = importing
        })
        assert monitor.check_passive_state(ha_import) is False
        assert monitor.is_passive_active is False

    def test_deactivates_on_low_solar(self, monitor):
        # Activate
        ha_export = FakeHaApi({
            "sensor.pv_power": {"state": "3000"},
            "sensor.grid_power": {"state": "-1500"},  # negative = exporting
        })
        monitor.check_passive_state(ha_export)

        # Low solar with slight export
        ha_low = FakeHaApi({
            "sensor.pv_power": {"state": "100"},
            "sensor.grid_power": {"state": "-50"},  # still exporting but low solar
        })
        assert monitor.check_passive_state(ha_low) is False

    def test_returns_false_when_disabled(self):
        config = {**DEFAULT_CONFIG, "passive_solar": {"enabled": False}}
        mon = SolarMonitor(config, logging.getLogger("test"))
        ha = FakeHaApi({
            "sensor.pv_power": {"state": "5000"},
            "sensor.grid_power": {"state": "-3000"},  # negative = exporting
        })
        assert mon.check_passive_state(ha) is False

    def test_handles_unavailable_sensors(self, monitor):
        ha = FakeHaApi({})
        assert monitor.check_passive_state(ha) is False

    def test_handles_non_numeric_state(self, monitor):
        ha = FakeHaApi({
            "sensor.pv_power": {"state": "unavailable"},
            "sensor.grid_power": {"state": "unknown"},
        })
        assert monitor.check_passive_state(ha) is False
