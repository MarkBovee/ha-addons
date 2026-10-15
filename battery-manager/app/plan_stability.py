"""Plan stability helpers: charge power locks and power-change diffs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dateutil.parser import isoparse

LOCK_SECONDS = 3600
SOC_DEVIATION_PP = 5.0
FORECAST_CHANGE_FRACTION = 0.25
POWER_CHANGE_FRACTION = 0.25


@dataclass
class ChargePowerLock:
    """Charge power computed for a window, held for up to LOCK_SECONDS."""

    power: int
    computed_at: datetime
    soc: Optional[float]
    remaining_solar_kwh: Optional[float]
    pv_power_w: Optional[float]


def _bounds(period: Dict[str, Any]) -> Optional[tuple[datetime, datetime]]:
    try:
        start = isoparse(period["start"])
        return start, start + timedelta(minutes=int(period["duration"]))
    except (KeyError, TypeError, ValueError):
        return None


def project_soc(
    schedule: Dict[str, Any],
    soc_start: float,
    start: datetime,
    end: datetime,
    capacity_kwh: float,
) -> float:
    """Project SOC at ``end`` from ``soc_start`` at ``start`` using a published plan.

    Adds planned grid charge plus the forecast PV share of each charge period and
    subtracts scheduled (non-adaptive) discharge, pro rata over the overlap.
    """

    if capacity_kwh <= 0 or end <= start:
        return soc_start
    net_kwh = 0.0
    for kind, sign in (("charge", 1.0), ("discharge", -1.0)):
        for period in schedule.get(kind, []):
            if kind == "discharge" and period.get("window_type") == "adaptive":
                continue
            bounds = _bounds(period)
            if bounds is None:
                continue
            overlap_start = max(bounds[0], start)
            overlap_end = min(bounds[1], end)
            if overlap_end <= overlap_start:
                continue
            period_hours = (bounds[1] - bounds[0]).total_seconds() / 3600.0
            overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600.0
            net_kwh += sign * float(period.get("power", 0) or 0) / 1000.0 * overlap_hours
            solar = period.get("forecast_solar_kwh")
            if kind == "charge" and solar and period_hours > 0:
                net_kwh += float(solar) * overlap_hours / period_hours
    return max(0.0, min(100.0, soc_start + net_kwh / capacity_kwh * 100.0))


def forecast_changed(
    lock: ChargePowerLock,
    remaining_solar_kwh: Optional[float],
    pv_power_w: Optional[float],
    now: datetime,
) -> bool:
    """True when the remaining-PV forecast moved >25% beyond normal depletion.

    The remaining-energy sensor falls as PV produces, so the expected value is
    the locked value minus the elapsed time at the mean observed PV power.
    """

    if remaining_solar_kwh is None or lock.remaining_solar_kwh is None:
        return False
    if lock.remaining_solar_kwh < 1.0:
        return False
    elapsed_h = max((now - lock.computed_at).total_seconds() / 3600.0, 0.0)
    pv_samples = [value for value in (lock.pv_power_w, pv_power_w) if value is not None]
    mean_pv_kw = (sum(pv_samples) / len(pv_samples) / 1000.0) if pv_samples else 0.0
    expected = max(0.0, lock.remaining_solar_kwh - mean_pv_kw * elapsed_h)
    return abs(remaining_solar_kwh - expected) / lock.remaining_solar_kwh > FORECAST_CHANGE_FRACTION


def apply_charge_power_locks(
    charge_schedule: List[Dict[str, Any]],
    locks: Dict[str, ChargePowerLock],
    now: datetime,
    soc: Optional[float],
    remaining_solar_kwh: Optional[float],
    pv_power_w: Optional[float],
    previous_schedule: Optional[Dict[str, Any]],
    capacity_kwh: float,
) -> List[Dict[str, Any]]:
    """Hold each window's charge power for an hour unless inputs moved a lot.

    Windows are keyed by their end time (the active window's start slides with
    every regeneration). Mutates ``charge_schedule`` powers and ``locks`` and
    returns trace events describing every keep/recompute decision.
    """

    events: List[Dict[str, Any]] = []
    live_keys = set()
    for period in charge_schedule:
        if period.get("window_type") != "charge":
            continue
        bounds = _bounds(period)
        if bounds is None or bounds[1] <= now:
            continue
        key = bounds[1].astimezone(timezone.utc).isoformat()
        live_keys.add(key)
        planned = int(period.get("power", 0) or 0)
        lock = locks.get(key)
        reason: Optional[str] = None

        if lock is not None and (now - lock.computed_at).total_seconds() < LOCK_SECONDS:
            if planned == lock.power:
                continue
            if soc is not None and lock.soc is not None and previous_schedule is not None:
                projected = project_soc(previous_schedule, lock.soc, lock.computed_at, now, capacity_kwh)
                if abs(soc - projected) > SOC_DEVIATION_PP:
                    reason = f"SoC {soc:.1f}% deviates {soc - projected:+.1f}pp from projection {projected:.1f}%"
            if reason is None and forecast_changed(lock, remaining_solar_kwh, pv_power_w, now):
                reason = (
                    f"solar forecast changed >{FORECAST_CHANGE_FRACTION:.0%} "
                    f"(remaining {lock.remaining_solar_kwh}->{remaining_solar_kwh} kWh)"
                )
            if reason is None:
                ceiling = int(period.get("base_power") or lock.power)
                period["power"] = min(lock.power, ceiling)
                events.append({
                    "window_end": key,
                    "action": "kept",
                    "locked_power": period["power"],
                    "recomputed_power": planned,
                })
                continue
        elif lock is not None:
            reason = f"lock older than {LOCK_SECONDS // 60} min"

        locks[key] = ChargePowerLock(planned, now, soc, remaining_solar_kwh, pv_power_w)
        if reason is not None:
            events.append({
                "window_end": key,
                "action": "recomputed",
                "previous_power": lock.power if lock else None,
                "power": planned,
                "reason": reason,
            })

    for key in list(locks):
        if key not in live_keys:
            del locks[key]
    return events


def diff_plan_powers(
    old_schedule: Optional[Dict[str, Any]],
    new_schedule: Dict[str, Any],
    from_dt: datetime,
    interval_minutes: int = 15,
) -> List[Dict[str, Any]]:
    """Return runs of quarters whose planned power changed by more than 25%."""

    if not old_schedule:
        return []
    step = timedelta(minutes=interval_minutes)

    def per_quarter(schedule: Dict[str, Any], kind: str) -> Dict[datetime, int]:
        quarters: Dict[datetime, int] = {}
        for period in schedule.get(kind, []):
            if kind == "discharge" and period.get("window_type") != "discharge":
                continue
            bounds = _bounds(period)
            if bounds is None:
                continue
            cursor = bounds[0]
            cursor = cursor.replace(minute=(cursor.minute // interval_minutes) * interval_minutes,
                                    second=0, microsecond=0)
            while cursor < bounds[1]:
                if cursor >= from_dt:
                    quarters[cursor] = int(period.get("power", 0) or 0)
                cursor += step
        return quarters

    runs: List[Dict[str, Any]] = []
    for kind in ("charge", "discharge"):
        old_q = per_quarter(old_schedule, kind)
        new_q = per_quarter(new_schedule, kind)
        for quarter in sorted(set(old_q) & set(new_q)):
            old_p, new_p = old_q[quarter], new_q[quarter]
            if old_p <= 0 or abs(new_p - old_p) / old_p <= POWER_CHANGE_FRACTION:
                continue
            last = runs[-1] if runs else None
            if (
                last
                and last["kind"] == kind
                and last["old_power"] == old_p
                and last["new_power"] == new_p
                and last["_end"] == quarter
            ):
                last["_end"] = quarter + step
                last["quarters"] += 1
            else:
                runs.append({
                    "kind": kind,
                    "from": quarter.isoformat(),
                    "old_power": old_p,
                    "new_power": new_p,
                    "quarters": 1,
                    "_end": quarter + step,
                })
    for run in runs:
        run.pop("_end", None)
    return runs
