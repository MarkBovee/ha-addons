import logging
import pytest

from app.price_analyzer import (
    PricePoint,
    find_top_x_charge_periods,
    find_top_x_discharge_periods,
)

logger = logging.getLogger("battery-manager-tests")


def test_charge_periods_basic_list():
    logger.info("price_analyzer: selects cheapest periods")
    prices = [0.30, 0.10, 0.20, 0.10]
    result = find_top_x_charge_periods(prices, top_x=2)

    assert [p.price for p in result] == [0.10, 0.10]
    assert [p.index for p in result] == [1, 3]


def test_discharge_periods_basic_list():
    logger.info("price_analyzer: selects most expensive periods")
    prices = [0.30, 0.10, 0.20, 0.10]
    result = find_top_x_discharge_periods(prices, top_x=2)

    assert [p.price for p in result] == [0.30, 0.20]
    assert [p.index for p in result] == [0, 2]


def test_charge_periods_dicts():
    logger.info("price_analyzer: supports dict price entries")
    prices = [
        {"start": "00:00", "price": 0.25},
        {"start": "00:15", "price": 0.05},
        {"start": "00:30", "price": 0.15},
    ]
    result = find_top_x_charge_periods(prices, top_x=1)

    assert result[0].price == 0.05
    assert result[0].value["start"] == "00:15"


def test_top_x_larger_than_available():
    prices = [0.10, 0.20]
    result = find_top_x_charge_periods(prices, top_x=5)

    assert len(result) == 2


def test_empty_prices():
    result = find_top_x_charge_periods([], top_x=3)
    assert result == []


def test_invalid_price_item():
    with pytest.raises(ValueError):
        find_top_x_charge_periods(["bad"], top_x=1)


def test_top_x_zero():
    prices = [0.10, 0.20]
    result = find_top_x_discharge_periods(prices, top_x=0)

    assert result == []


def test_price_point_type():
    prices = [0.10]
    result = find_top_x_charge_periods(prices, top_x=1)

    assert isinstance(result[0], PricePoint)
