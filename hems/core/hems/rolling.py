"""Rolling-horizon step: plan from now to the end of the known prices, execute only the first quarter.

Called every quarter with the actual SoC; the rest of the plan is a forecast that is replaced next time.
Pure (no I/O, no clock): the caller supplies `now`, so the same code serves live dry-run and replay.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from hems.battery import BatteryConfig, Plan, Slot, plan
from hems.contracts import BatteryCommand
from hems.decision_log import best_later, plan_segments
from hems.prices import PriceSeries
from hems.slots import SLOT_H, SLOT_MINUTES
from hems.terminal import terminal_value
from hems.trace import explain
from hems.windows import MAX_LOOKBACK, WindowAnalysis, analyse, record

QUARTER = timedelta(minutes=SLOT_MINUTES)
SHIFT_POWER_FRACTION = 0.25          # a replanned quarter that moves more than this share of its power is logged


def floor_to_quarter(moment: datetime) -> datetime:
    """UTC start of the quarter containing `moment` (timezone-aware)."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    utc = moment.astimezone(timezone.utc)
    return utc.replace(minute=utc.minute - utc.minute % SLOT_MINUTES, second=0, microsecond=0)


@dataclass(frozen=True)
class HorizonInputs:
    now: datetime
    soc_kwh: float
    prices: PriceSeries
    load_kwh: Mapping[datetime, float]       # base load per quarter start (UTC)
    pv_kwh: Mapping[datetime, float]         # PV production per quarter start (UTC)
    max_slots: int = 192                     # 48 h; the known prices usually end earlier
    terminal_value: float | None = None
    history_peak: float | None = None        # typical recent peak (hems.terminal.reference_peak): values energy kept past the horizon; None = the default
    import_cap_kwh: float | None = None      # most grid energy per quarter the connection may deliver; None = no cap


@dataclass(frozen=True)
class Decision:
    slot_start: datetime                     # the quarter this decision executes
    command: BatteryCommand
    plan: Plan
    trace: dict
    slots: tuple[Slot, ...] = ()             # the slots the plan was computed from (prices, load, PV per quarter)
    analysis: WindowAnalysis | None = None   # the sell windows of the horizon and what the plan does with them (read-only, hems.windows)


def _build_slots(inputs: HorizonInputs, start: datetime) -> tuple[list[Slot], int]:
    """Slots from `start` while prices are contiguous; also counts slots without a load or PV forecast."""
    by_start = {s: (i, e) for s, i, e in zip(inputs.prices.starts, inputs.prices.import_eur_kwh, inputs.prices.export_eur_kwh)}
    slots, missing = [], 0
    for n in range(inputs.max_slots):
        at = start + n * QUARTER
        if at not in by_start:
            break
        load, pv = inputs.load_kwh.get(at), inputs.pv_kwh.get(at)
        missing += load is None or pv is None
        slots.append(Slot(*by_start[at], load_kwh=load or 0.0, pv_kwh=pv or 0.0, import_cap_kwh=inputs.import_cap_kwh))
    return slots, missing


def plan_next(inputs: HorizonInputs, cfg: BatteryConfig) -> Decision | None:
    """Plan the horizon and return the command for the current quarter, or None when no price is known for it."""
    start = floor_to_quarter(inputs.now)
    slots, missing = _build_slots(inputs, start)
    if not slots:
        return None
    default = min(s.import_price for s in slots) * cfg.round_trip_eff ** 0.5
    terminal = inputs.terminal_value
    if terminal is None and inputs.history_peak is not None:
        terminal = terminal_value(inputs.history_peak, default, cfg)
    result = plan(slots, inputs.soc_kwh, cfg, terminal)
    first = result.slots[0]
    command = BatteryCommand(start, start + QUARTER, round(first.battery_kwh / SLOT_H * 1000))
    trace = {
        "slot_start": start.isoformat(), "soc_kwh": round(inputs.soc_kwh, 2),
        "soc_pct": round(inputs.soc_kwh / cfg.capacity_kwh * 100, 1), "horizon_slots": len(slots),
        "missing_forecast_slots": missing, "import_price": round(slots[0].import_price, 4),
        "export_price": round(slots[0].export_price, 4), "power_w": command.power_w,
        **explain(result, [s.import_price for s in slots], [s.export_price for s in slots]),
        "compare": {"code": first.reason_code, "sell": _r(first.sell_value), "buy": _r(first.buy_cost), "keep": _r(first.stored_value),
                    "at_floor": first.at_floor, "at_full": first.at_full, **best_later(result, start)},
        "segments": plan_segments(result, slots, start, inputs.soc_kwh, cfg.capacity_kwh),
        "terminal": {"default": round(default, 4), "history_peak": None if inputs.history_peak is None else round(inputs.history_peak, 4),
                     "value": round(default if terminal is None else terminal, 4)},
    }
    earlier = dict(zip(inputs.prices.starts, inputs.prices.import_eur_kwh))
    past: list[float] = []
    for k in range(1, MAX_LOOKBACK + 1):                                  # the contiguous run of known quarters right before this one
        if start - k * QUARTER not in earlier:
            break
        past.insert(0, earlier[start - k * QUARTER])
    analysis = analyse([start + n * QUARTER for n in range(len(slots))], slots, result, inputs.soc_kwh, cfg, past)
    trace["windows"] = [record(r) for r in analysis.reports]
    trace["windows_outside_kwh"] = analysis.outside_kwh
    return Decision(start, command, result, trace, tuple(slots), analysis)


def _r(value: float | None) -> float | None:
    """Round a comparison value that may be None to four decimals (EUR per kWh)."""
    return None if value is None else round(value, 4)


def plan_shift(previous: Decision | None, current: Decision) -> dict | None:
    """What the previous plan intended for this quarter versus now, when it moved by more than 25 % of its power.

    'A plan that changes like this is not a plan': every shift is logged with both values so it can be explained."""
    if previous is None:
        return None
    index = int((current.slot_start - previous.slot_start) / QUARTER)
    if not 0 <= index < len(previous.plan.slots):
        return None
    was_w = round(previous.plan.slots[index].battery_kwh / SLOT_H * 1000)
    now_w = current.command.power_w
    moved = abs(now_w - was_w)
    if moved <= SHIFT_POWER_FRACTION * max(abs(was_w), abs(now_w)):
        return None
    return {"was_w": was_w, "now_w": now_w, "quarter": current.slot_start.isoformat(), "planned_at": previous.slot_start.isoformat()}
