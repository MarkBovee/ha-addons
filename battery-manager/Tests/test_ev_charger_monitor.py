import logging

from app.ev_charger_monitor import adjust_house_load, is_ev_charging, should_pause_discharge

logger = logging.getLogger("battery-manager-tests")


def test_is_ev_charging():
    logger.info("ev_charger_monitor: detects charging threshold")
    assert is_ev_charging(0, 500) is False
    assert is_ev_charging(500, 500) is False
    assert is_ev_charging(600, 500) is True


def test_should_pause_discharge():
    logger.info("ev_charger_monitor: pause decision based on EV load")
    assert should_pause_discharge(1000, 500) is True
    assert should_pause_discharge(100, 500) is False


def test_adjust_house_load():
    logger.info("ev_charger_monitor: adjusts house load excluding EV power")
    assert adjust_house_load(3000, 1000) == 2000
    assert adjust_house_load(500, 1000) == 0


def test_adjust_house_load_missing_inputs():
    logger.info("ev_charger_monitor: handles missing inputs")
    assert adjust_house_load(None, 1000) is None
    assert adjust_house_load(3000, None) == 3000
