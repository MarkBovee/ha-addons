"""Price analysis helpers for selecting charge/discharge periods."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Iterable, List, Optional, Sequence, Set, Tuple, Union

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
    # Equal prices resolve to the earliest slot for both directions so that ties
    # form contiguous windows instead of drifting to the end of the day.
    if reverse:
        sorted_points = sorted(points, key=lambda p: (-p.price, p.index))
    else:
        sorted_points = sorted(points, key=lambda p: (p.price, p.index))
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

def calculate_top_x_count(hours: float, interval_minutes: int) -> int:
    """Convert hours into interval count based on interval length."""

    if hours <= 0:
        return 0
    interval_minutes = max(interval_minutes, 1)
    required_minutes = float(hours) * 60.0
    return max(1, int(math.ceil(required_minutes / interval_minutes)))


def calculate_discharge_top_x_count(hours: float, interval_minutes: int) -> int:
    """Convert discharge hours into a conservative interval count.

    Discharge windows should not round up to an extra slot when the interval
    granularity cannot represent the fractional remainder. That avoids building
    impossible sell windows such as 3 hourly slots for a 2.5h target.
    """

    if hours <= 0:
        return 0
    interval_minutes = max(interval_minutes, 1)
    required_minutes = float(hours) * 60.0
    return max(1, int(math.floor(required_minutes / interval_minutes)))


def find_profitable_discharge_starts(
    import_curve: Sequence[dict],
    export_curve: Sequence[dict],
    top_x_discharge: int,
    min_profit: float,
    cost_basis: Optional[float] = None,
) -> Set[str]:
    """Return exact export-curve start timestamps selected for profitable discharge.

    ``cost_basis`` replaces the day's cheapest import price as the energy cost
    that ``min_profit`` is added to (e.g. the forgone export price of PV energy).
    """

    import_points = _to_price_points(import_curve)
    export_points = _to_price_points(export_curve)

    if not import_points or not export_points or top_x_discharge <= 0:
        return set()

    basis = cost_basis if cost_basis is not None else min(point.price for point in import_points)
    min_profitable_price = basis + float(min_profit)
    selected = _select_top(export_points, top_x=top_x_discharge, reverse=True)

    starts: Set[str] = set()
    for point in selected:
        if point.price < min_profitable_price:
            continue
        if isinstance(point.value, dict):
            start = point.value.get("start")
            if isinstance(start, str) and start:
                starts.add(start)

    return starts


def calculate_price_ranges(
    import_curve: Sequence[dict],
    export_curve: Sequence[dict],
    top_x_charge: int,
    top_x_discharge: int,
    min_profit: float,
    cost_basis: Optional[float] = None,
    discharge_export_curve: Optional[Sequence[dict]] = None,
) -> Tuple[Optional[PriceRange], Optional[PriceRange], Optional[PriceRange]]:
    """Calculate load, discharge, and adaptive ranges.

    ``cost_basis`` replaces the day's cheapest import price in the profit margin.
    ``discharge_export_curve`` restricts the quarters eligible for the discharge
    band (e.g. only quarters after the charge window); the load band and the
    default export curve are unaffected.
    """

    import_points = _to_price_points(import_curve)
    export_points = _to_price_points(export_curve)

    if not import_points:
        return None, None, None

    discharge_points = (
        export_points if discharge_export_curve is None else _to_price_points(discharge_export_curve)
    )
    lowest_periods = _select_top(import_points, top_x=top_x_charge, reverse=False)
    highest_periods = _select_top(discharge_points, top_x=top_x_discharge, reverse=True)

    if not lowest_periods:
        return None, None, None

    lowest_prices = [p.price for p in lowest_periods]
    load_range = PriceRange(min_price=min(lowest_prices), max_price=max(lowest_prices))

    if not highest_periods:
        if discharge_export_curve is None:
            return None, None, None
        return load_range, None, None

    highest_prices = [p.price for p in highest_periods]

    min_import_price = cost_basis if cost_basis is not None else min(p.price for p in import_points)
    discharge_min = max(min(highest_prices), min_import_price + min_profit)
    discharge_max = max(highest_prices)
    
    # If spread is too small, no profitable discharge range exists
    if discharge_min > discharge_max:
        discharge_range = None
        adaptive_range = PriceRange(min_price=load_range.max_price, max_price=discharge_max)
    else:
        discharge_range = PriceRange(min_price=discharge_min, max_price=discharge_max)
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


def find_top_x_charge_starts(
    import_curve: Sequence[dict],
    top_x_charge: int,
) -> Set[str]:
    """Return exact import-curve start timestamps for the cheapest top-X charge slots.

    Uses the same slot selection as ``calculate_price_ranges`` so that the charge
    window classification in ``find_upcoming_windows`` is strictly limited to those
    N slots rather than to all slots at-or-below the Nth price. This prevents a
    single expensive slot from expanding the price ceiling and pulling in hours that
    should not be charged (e.g. top-3 with prices [0.13, 0.13, 0.21] would otherwise
    allow all hours ≤ 0.21 to qualify, even when six cheaper alternatives exist).
    """

    if not import_curve or top_x_charge <= 0:
        return set()

    points = _to_price_points(import_curve)
    selected = _select_top(points, top_x=top_x_charge, reverse=False)

    starts: Set[str] = set()
    for point in selected:
        if isinstance(point.value, dict):
            start = point.value.get("start")
            if isinstance(start, str) and start:
                starts.add(start)
    return starts


def expand_charge_starts_within_price_delta(
    import_curve: Sequence[dict],
    selected_starts: Set[str],
    max_price_delta: float,
) -> Set[str]:
    """Expand selected charge slots with nearly-equal priced periods.

    Starts from the exact Top-X slot selection and adds extra periods whose import
    price stays within ``max_price_delta`` of the most expensive already-selected
    charge slot. This keeps charging inside a tight cheap-price band while allowing
    longer, lower-power charging windows when many hours are similarly cheap.
    """

    if not import_curve or not selected_starts:
        return set(selected_starts)

    try:
        max_delta = max(0.0, float(max_price_delta))
    except (TypeError, ValueError):
        max_delta = 0.0

    if max_delta <= 0:
        return set(selected_starts)

    selected_prices: List[float] = []
    for entry in import_curve:
        start = entry.get("start")
        if start not in selected_starts:
            continue
        try:
            selected_prices.append(float(entry.get("price", 0.0)))
        except (TypeError, ValueError):
            continue

    if not selected_prices:
        return set(selected_starts)

    price_ceiling = max(selected_prices) + max_delta
    expanded = set(selected_starts)
    for entry in import_curve:
        start = entry.get("start")
        if not isinstance(start, str) or not start:
            continue
        try:
            price = float(entry.get("price", 0.0))
        except (TypeError, ValueError):
            continue
        if price <= price_ceiling:
            expanded.add(start)

    return expanded


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


def _entry_bounds(entry: dict, interval_minutes: int) -> Optional[Tuple[datetime, datetime]]:
    start = entry.get("start")
    if not isinstance(start, str) or not start:
        return None
    try:
        start_dt = _ensure_aware(isoparse(start))
        end = entry.get("end")
        end_dt = _ensure_aware(isoparse(end)) if end else start_dt + timedelta(minutes=interval_minutes)
    except Exception:
        return None
    return start_dt, end_dt


def find_main_charge_window(
    curve: Sequence[dict],
    exact_starts: Set[str],
    charge_starts: Set[str],
    interval_minutes: int,
) -> Optional[Tuple[datetime, datetime]]:
    """Return the main charge window of a day as (start, end).

    Consecutive ``charge_starts`` slots form windows; the main window is the one
    holding the most exact top-X slots (earliest wins a tie). Spread-only windows
    elsewhere in the day (e.g. a cheap late-night block) never become the main
    window, so they cannot push "after the charge window" into the night.
    """

    if not curve or not exact_starts:
        return None

    slots: List[Tuple[datetime, datetime, bool]] = []
    for entry in curve:
        start = entry.get("start")
        if start not in charge_starts:
            continue
        bounds = _entry_bounds(entry, interval_minutes)
        if bounds is not None:
            slots.append((bounds[0], bounds[1], start in exact_starts))
    if not slots:
        return None
    slots.sort(key=lambda item: item[0])

    windows: List[List[object]] = []  # [start, end, exact_count]
    for start_dt, end_dt, is_exact in slots:
        if windows and start_dt <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end_dt)
            windows[-1][2] += 1 if is_exact else 0
        else:
            windows.append([start_dt, end_dt, 1 if is_exact else 0])

    best = max(windows, key=lambda w: (w[2], -w[0].timestamp()))
    if best[2] <= 0:
        return None
    return best[0], best[1]


def filter_curve_from(curve: Sequence[dict], not_before: datetime) -> List[dict]:
    """Return curve entries that start at or after ``not_before``."""

    kept: List[dict] = []
    for entry in curve:
        bounds = _entry_bounds(entry, 15)
        if bounds is not None and bounds[0] >= not_before:
            kept.append(entry)
    return kept


def min_price_between(curve: Sequence[dict], start: datetime, end: datetime) -> Optional[float]:
    """Return the lowest price among entries starting inside [start, end)."""

    prices: List[float] = []
    for entry in curve:
        bounds = _entry_bounds(entry, 15)
        if bounds is None or entry.get("price") is None:
            continue
        if start <= bounds[0] < end:
            prices.append(float(entry["price"]))
    return min(prices) if prices else None
