import logging
import pytest

from app.power_calculator import calculate_scaled_power

logger = logging.getLogger("battery-manager-tests")


def test_rank_based_scaling():
    logger.info("power_calculator: scales power by rank")
    assert calculate_scaled_power(1, 8000, 4000) == 8000
    assert calculate_scaled_power(2, 8000, 4000) == 4000
    assert calculate_scaled_power(3, 8000, 4000) == 4000
    assert calculate_scaled_power(4, 8000, 4000) == 4000


def test_invalid_rank():
    logger.info("power_calculator: rejects invalid rank")
    with pytest.raises(ValueError):
        calculate_scaled_power(0, 8000, 4000)


def test_invalid_power_values():
    logger.info("power_calculator: rejects invalid power values")
    with pytest.raises(ValueError):
        calculate_scaled_power(1, 0, 4000)
