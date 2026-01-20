"""Price analysis helpers for selecting charge/discharge periods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple, Union


@dataclass(frozen=True)
class PricePoint:
    index: int
    price: float
    value: object


def _to_price_points(prices: Sequence[Union[float, int, dict]]) -> List[PricePoint]:
    points: List[PricePoint] = []
    for index, item in enumerate(prices):
        if isinstance(item, (int, float)):
            points.append(PricePoint(index=index, price=float(item), value=item))
        elif isinstance(item, dict) and "price" in item:
            points.append(PricePoint(index=index, price=float(item["price"]), value=item))
        else:
            raise ValueError("Each price must be a number or a dict with a 'price' key")
    return points


def _select_top(points: Iterable[PricePoint], top_x: int, reverse: bool) -> List[PricePoint]:
    if top_x <= 0:
        return []
    sorted_points = sorted(points, key=lambda p: (p.price, p.index), reverse=reverse)
    return sorted_points[: min(top_x, len(sorted_points))]


def find_top_x_charge_periods(prices: Sequence[Union[float, int, dict]], top_x: int) -> List[PricePoint]:
    """Return the cheapest Top X periods for charging.

    Each entry is a PricePoint containing the original value, its price, and index.
    """

    points = _to_price_points(prices)
    return _select_top(points, top_x=top_x, reverse=False)


def find_top_x_discharge_periods(prices: Sequence[Union[float, int, dict]], top_x: int) -> List[PricePoint]:
    """Return the most expensive Top X periods for discharging.

    Each entry is a PricePoint containing the original value, its price, and index.
    """

    points = _to_price_points(prices)
    return _select_top(points, top_x=top_x, reverse=True)
