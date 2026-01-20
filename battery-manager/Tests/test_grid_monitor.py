import logging

from app.grid_monitor import is_exporting, should_reduce_discharge

logger = logging.getLogger("battery-manager-tests")


def test_is_exporting():
    logger.info("grid_monitor: detects export based on threshold")
    assert is_exporting(-800, 500) is True
    assert is_exporting(-400, 500) is False
    assert is_exporting(100, 500) is False


def test_is_exporting_missing():
    logger.info("grid_monitor: handles missing grid power")
    assert is_exporting(None, 500) is False


def test_should_reduce_discharge():
    logger.info("grid_monitor: reduce discharge decision")
    assert should_reduce_discharge(-800, 500) is True
    assert should_reduce_discharge(-400, 500) is False
