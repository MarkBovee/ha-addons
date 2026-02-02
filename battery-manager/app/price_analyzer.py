"""Price analysis helpers for selecting charge/discharge periods."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from dateutil.parser import isoparse


@dataclass(frozen=True)
class PricePoint:
    index: int
    price: float
    value: object


@dataclass(frozen=True)
class PriceRange:
    min_price: float
    max_price: float


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


def detect_interval_minutes(prices: Sequence[Union[float, int, dict]]) -> int:
    """Infer interval length from price curve entries."""

    if len(prices) >= 90:
        return 15

    if len(prices) < 2:
        return 60

    try:
        first = prices[0]
        second = prices[1]
        if isinstance(first, dict) and isinstance(second, dict):
            start_a = isoparse(first.get("start"))
            start_b = isoparse(second.get("start"))
            diff = int((start_b - start_a).total_seconds() / 60)
            if diff > 0:
                return diff
    except Exception:
        pass

    return 60


from datetime import datetime, timezone

def _ensure_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC default if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def calculate_top_x_count(hours: int, interval_minutes: int) -> int:
    """Convert hours into interval count based on interval length."""

    if hours <= 0:
        return 0
    interval_minutes = max(interval_minutes, 1)
    return max(1, int(hours * (60 / interval_minutes)))


def calculate_price_ranges(
    import_curve: Sequence[dict],
    export_curve: Sequence[dict],
    top_x_charge: int,
    top_x_discharge: int,
    min_profit: float,
) -> Tuple[Optional[PriceRange], Optional[PriceRange], Optional[PriceRange]]:
    """Calculate load, discharge, and adaptive ranges."""

    import_points = _to_price_points(import_curve)
    export_points = _to_price_points(export_curve)

    if not import_points:
        return None, None, None

    lowest_periods = _select_top(import_points, top_x=top_x_charge, reverse=False)
    highest_periods = _select_top(export_points, top_x=top_x_discharge, reverse=True)

    if not lowest_periods or not highest_periods:
        return None, None, None

    lowest_prices = [p.price for p in lowest_periods]
    highest_prices = [p.price for p in highest_periods]

    load_range = PriceRange(min_price=min(lowest_prices), max_price=max(lowest_prices))

    min_import_price = min(p.price for p in import_points)
    discharge_min = max(min(highest_prices), min_import_price + min_profit)
    discharge_range = PriceRange(min_price=discharge_min, max_price=max(highest_prices))

    if discharge_range.min_price <= load_range.max_price:
        adaptive_range = None
    else:
        adaptive_range = PriceRange(min_price=load_range.max_price, max_price=discharge_range.min_price)

    return load_range, discharge_range, adaptive_range


def get_current_price_entry(curve: Sequence[dict], now: datetime, interval_minutes: int) -> Optional[dict]:
    """Get the current price entry based on time and interval length."""

    if not curve:
        return None

    interval_minutes = max(interval_minutes, 1)
    
    # Ensure consistent timezone for comparison
    now = _ensure_aware(now)
    rounded = now.replace(minute=(now.minute // interval_minutes) * interval_minutes, second=0, microsecond=0)

    for entry in curve:
        start = entry.get("start")
        end = entry.get("end")
        if not start:
            continue
        try:
            start_dt = _ensure_aware(isoparse(start))
            end_dt = _ensure_aware(isoparse(end)) if end else start_dt
        except Exception:
            continue
        if start_dt <= rounded < end_dt:
            return entry
        if start_dt <= now < end_dt:
            return entry

    return None


def get_current_period_rank(
    curve: Sequence[dict],
    top_x: int,
    now: datetime,
    *,
    reverse: bool,
) -> Optional[int]:
    """Return 1-based rank for current interval within top X periods."""

    points = _to_price_points(curve)
    if not points or top_x <= 0:
        return None

    now = _ensure_aware(now)

    ranked = _select_top(points, top_x=top_x, reverse=reverse)
    for index, point in enumerate(ranked, start=1):
        if isinstance(point.value, dict):
            start = point.value.get("start")
            end = point.value.get("end")
            if not start:
                continue
            try:
                start_dt = _ensure_aware(isoparse(start))
                end_dt = _ensure_aware(isoparse(end)) if end else start_dt
            except Exception:
                continue
            if start_dt <= now < end_dt:
                return index
    return None


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
