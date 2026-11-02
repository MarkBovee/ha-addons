"""Margin checks for grid charging: a charge must earn its round-trip loss and a minimum margin."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

DEFAULT_ROUND_TRIP_EFFICIENCY = 0.90


def charge_margin(expected_sell_price: float, charge_price: float, efficiency: float) -> float:
    """Return net margin per kWh bought: sell price after losses minus charge price."""

    return float(expected_sell_price) * float(efficiency) - float(charge_price)


def intended_sell_price(
    charge_end: datetime,
    discharge_windows: Sequence[Dict[str, Any]],
    next_charge_start: Optional[datetime] = None,
) -> Optional[Tuple[float, List[Dict[str, Any]]]]:
    """Return the duration-weighted sell price of the windows a charge is meant for.

    These are the sell windows starting at/after ``charge_end`` and before the
    next charge window. Returns None when no sell window follows the charge.
    """

    weighted = 0.0
    total_minutes = 0.0
    used: List[Dict[str, Any]] = []
    for window in discharge_windows:
        start_dt = window.get("start")
        end_dt = window.get("end")
        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
            continue
        if start_dt < charge_end:
            continue
        if next_charge_start is not None and start_dt >= next_charge_start:
            continue
        minutes = max((end_dt - start_dt).total_seconds() / 60.0, 0.0)
        if minutes <= 0:
            continue
        weighted += float(window.get("avg_price", 0.0)) * minutes
        total_minutes += minutes
        used.append(window)
    if total_minutes <= 0:
        return None
    return weighted / total_minutes, used


def first_sale_start_after(
    charge_end: datetime,
    discharge_windows: Sequence[Dict[str, Any]],
) -> Optional[datetime]:
    """Return the start of the first sell window beginning at/after ``charge_end``."""

    starts = [
        window["start"]
        for window in discharge_windows
        if isinstance(window.get("start"), datetime) and window["start"] >= charge_end
    ]
    return min(starts) if starts else None


def next_window_start_after(
    charge_end: datetime,
    charge_windows: Sequence[Dict[str, Any]],
) -> Optional[datetime]:
    """Return the start of the first other charge window beginning at/after ``charge_end``."""

    starts = [
        window["start"]
        for window in charge_windows
        if isinstance(window.get("start"), datetime) and window["start"] >= charge_end
    ]
    return min(starts) if starts else None


def _window_hours(window: Dict[str, Any]) -> float:
    """Return a window's length in hours (0 for malformed windows)."""

    start_dt, end_dt = window.get("start"), window.get("end")
    if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
        return 0.0
    return max((end_dt - start_dt).total_seconds() / 3600.0, 0.0)


def cheaper_window_ahead(
    window: Dict[str, Any],
    charge_windows: Sequence[Dict[str, Any]],
    discharge_windows: Sequence[Dict[str, Any]],
    min_saving: float,
) -> Optional[Dict[str, Any]]:
    """Return the cheapest later charge window that makes ``window`` pointless, or None.

    A later window replaces this one when it starts before the next sale (so the energy still
    arrives in time), is at least ``min_saving`` cheaper, and the cheaper windows together last
    at least as long as this one (so they can take over its energy). 2026-11-02: 21:45 @0.404
    was charged while 01:00-06:15 @0.396 came before the 08:00 sale.
    """

    price = float(window.get("avg_price", 0.0))
    first_sale = first_sale_start_after(window["end"], discharge_windows)
    cheaper = [
        other
        for other in charge_windows
        if other is not window
        and isinstance(other.get("start"), datetime)
        and other["start"] >= window["end"]
        and (first_sale is None or other["start"] < first_sale)
        and float(other.get("avg_price", 0.0)) <= price - min_saving + 1e-9
    ]
    if not cheaper or sum(_window_hours(w) for w in cheaper) < _window_hours(window) - 1e-9:
        return None
    return min(cheaper, key=lambda w: float(w.get("avg_price", 0.0)))


def window_has_exact_slot(window: Dict[str, Any], exact_start_dts: Set[datetime]) -> bool:
    """True when the grouped charge window contains a strict top-X cheapest slot."""

    for slot in window.get("slots") or []:
        if slot.get("start") in exact_start_dts:
            return True
    return window.get("start") in exact_start_dts


def evaluate_grid_charge(
    *,
    charge_price: float,
    charge_end: datetime,
    discharge_windows: Sequence[Dict[str, Any]],
    charge_windows: Sequence[Dict[str, Any]],
    efficiency: float,
    min_margin: float,
) -> Dict[str, Any]:
    """Decide whether a grid charge earns the required margin.

    The result carries everything the decision trace needs: ``allowed``,
    ``reason``, ``expected_sell_price`` and ``margin``.
    """

    # A charge feeds the next sale. Charge windows between the charge and that sale belong to the same
    # block and do not end it; only a charge window after the sale's start bounds the sales it is for.
    first_sale_start = first_sale_start_after(charge_end, discharge_windows)
    target = intended_sell_price(
        charge_end,
        discharge_windows,
        next_window_start_after(first_sale_start, charge_windows) if first_sale_start is not None else None,
    )
    if target is None:
        return {
            "allowed": False,
            "reason": "no sell window follows this charge",
            "expected_sell_price": None,
            "margin": None,
        }
    expected, used = target
    margin = charge_margin(expected, charge_price, efficiency)
    allowed = margin >= min_margin - 1e-9
    return {
        "allowed": allowed,
        "reason": (
            f"margin {margin:.3f} >= {min_margin:.3f}"
            if allowed
            else f"margin {margin:.3f} < {min_margin:.3f} "
            f"(sell {expected:.3f} x{efficiency:.2f} - charge {charge_price:.3f})"
        ),
        "expected_sell_price": round(expected, 4),
        "margin": round(margin, 4),
        "sell_windows": [w["start"].isoformat() for w in used],
    }
