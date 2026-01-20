import logging

from app.solar_monitor import detect_excess_solar, should_charge_from_solar

logger = logging.getLogger("battery-manager-tests")


def test_detect_excess_solar():
    logger.info("solar_monitor: detects excess solar power")
    assert detect_excess_solar(3000, 1500, 1000) == 1500


def test_detect_excess_solar_missing_inputs():
    logger.info("solar_monitor: handles missing solar/load inputs")
    assert detect_excess_solar(None, 1500, 1000) is None
    assert detect_excess_solar(2000, None, 1000) is None


def test_should_charge_from_solar():
    logger.info("solar_monitor: decides opportunistic charge")
    assert should_charge_from_solar(1500, 1000) is True
    assert should_charge_from_solar(1000, 1000) is False
    assert should_charge_from_solar(500, 1000) is False


def test_should_charge_from_solar_missing():
    logger.info("solar_monitor: skips decision when excess unknown")
    assert should_charge_from_solar(None, 1000) is False
