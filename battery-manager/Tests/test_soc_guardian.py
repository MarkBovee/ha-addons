import logging
from datetime import datetime, time

from app.soc_guardian import can_charge, can_discharge, should_target_eod

logger = logging.getLogger("battery-manager-tests")


def test_can_charge():
    logger.info("soc_guardian: charge allowed under max SOC")
    assert can_charge(50, 100) is True
    assert can_charge(100, 100) is False


def test_can_discharge_min_soc():
    logger.info("soc_guardian: enforces minimum SOC")
    assert can_discharge(4, 5, 40, False) is False
    assert can_discharge(5, 5, 40, False) is False
    assert can_discharge(6, 5, 40, False) is True


def test_can_discharge_conservative():
    logger.info("soc_guardian: conservative SOC threshold")
    assert can_discharge(39, 5, 40, True) is False
    assert can_discharge(40, 5, 40, True) is True


def test_should_target_eod_time():
    logger.info("soc_guardian: end-of-day target timing")
    eod_time = time(23, 0)
    assert should_target_eod(time(22, 59), eod_time, 20) is False
    assert should_target_eod(time(23, 0), eod_time, 20) is True


def test_should_target_eod_datetime():
    logger.info("soc_guardian: end-of-day target with datetime")
    eod_time = time(23, 0)
    current_time = datetime(2026, 1, 20, 23, 1)
    assert should_target_eod(current_time, eod_time, 20) is True
