"""Margin checks for grid charging that is not part of the cheapest top-X slots."""

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
    """Decide whether a non-top-X grid charge earns the required margin.

    The result carries everything the decision trace needs: ``allowed``,
    ``reason``, ``expected_sell_price`` and ``margin``.
    """

    target = intended_sell_price(
        charge_end,
        discharge_windows,
        next_window_start_after(charge_end, charge_windows),
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
