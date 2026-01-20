import logging

from app.temperature_advisor import get_discharge_hours

logger = logging.getLogger("battery-manager-tests")


DEFAULT_THRESHOLDS = [
    {"temp_max": 0, "discharge_hours": 1},
    {"temp_max": 8, "discharge_hours": 1},
    {"temp_max": 16, "discharge_hours": 2},
    {"temp_max": 20, "discharge_hours": 2},
    {"temp_max": 999, "discharge_hours": 3},
]


def test_temperature_bands():
    logger.info("temperature_advisor: maps temperature bands to hours")
    assert get_discharge_hours(-5, DEFAULT_THRESHOLDS) == 1
    assert get_discharge_hours(4, DEFAULT_THRESHOLDS) == 1
    assert get_discharge_hours(12, DEFAULT_THRESHOLDS) == 2
    assert get_discharge_hours(18, DEFAULT_THRESHOLDS) == 2
    assert get_discharge_hours(25, DEFAULT_THRESHOLDS) == 3


def test_temperature_boundaries():
    logger.info("temperature_advisor: handles boundary values")
    assert get_discharge_hours(0, DEFAULT_THRESHOLDS) == 1
    assert get_discharge_hours(8, DEFAULT_THRESHOLDS) == 1
    assert get_discharge_hours(16, DEFAULT_THRESHOLDS) == 2
    assert get_discharge_hours(20, DEFAULT_THRESHOLDS) == 2


def test_custom_thresholds():
    logger.info("temperature_advisor: supports custom thresholds")
    custom = [
        {"temp_max": 10, "discharge_hours": 1},
        {"temp_max": 30, "discharge_hours": 4},
    ]

    assert get_discharge_hours(5, custom) == 1
    assert get_discharge_hours(25, custom) == 4


def test_none_temperature_defaults():
    assert get_discharge_hours(None, DEFAULT_THRESHOLDS) == 2


def test_missing_hours_uses_default():
    thresholds = [{"temp_max": 10}]
    assert get_discharge_hours(5, thresholds) == 2
