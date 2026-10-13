"""Everything needed to follow a decision afterwards (pure): plan segments, the best later opportunities, the
compact full-plan record and a digest of the settings in force.

Three levels of detail build on each other: the decision record says what was chosen and why this quarter, the
segments show the shape of the whole plan, and the plan detail carries every planned quarter with the inputs it
was computed from, so a past plan can be rebuilt and compared line by line.
"""
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Mapping, Sequence

from hems.battery import Plan, Slot
from hems.slots import SLOT_H

if TYPE_CHECKING:
    from hems.rolling import Decision

QUARTER = timedelta(minutes=15)
ACTION_LETTER = {"charge": "c", "discharge": "d", "idle": "i"}
CODE_LETTER = {"sell": "s", "buy": "b", "hold": "h", "floor": "f", "full": "v", "none": "-"}
MAX_SEGMENTS = 16


def _round(value: float | None, digits: int) -> float | None:
    """Round a value that may be None."""
    return None if value is None else round(value, digits)


def best_later(plan: Plan, slot_start: datetime) -> dict:
    """The best selling and the cheapest buying opportunity after the current quarter, with their time and value.

    These are what 'keep' is waiting for: if the best later sell beats selling now, the plan holds."""
    later = plan.slots[1:]
    sells = [(s.sell_value, i) for i, s in enumerate(later, start=1) if s.sell_value is not None]
    buys = [(s.buy_cost, i) for i, s in enumerate(later, start=1) if s.buy_cost is not None]
    out = {}
    if sells:
        value, i = max(sells)
        out["best_sell_later"] = {"at": (slot_start + i * QUARTER).isoformat(), "value": round(value, 4)}
    if buys:
        value, i = min(buys)
        out["best_buy_later"] = {"at": (slot_start + i * QUARTER).isoformat(), "value": round(value, 4)}
    return out


def plan_segments(plan: Plan, slots: Sequence[Slot], slot_start: datetime, soc0_kwh: float, capacity_kwh: float,
                  limit: int = MAX_SEGMENTS) -> list[dict]:
    """The plan as runs of the same action: from/to, energy, average power and price, SoC at both ends.

    Longer plans are cut at `limit` segments; the last entry then says so."""
    runs: list[list[int]] = []
    for i, planned in enumerate(plan.slots):
        if runs and plan.slots[runs[-1][-1]].action == planned.action:
            runs[-1].append(i)
        else:
            runs.append([i])
    segments = []
    for run in runs[:limit]:
        first, last = run[0], run[-1]
        action = plan.slots[first].action
        energy = sum(abs(plan.slots[i].battery_kwh) for i in run)
        before = plan.slots[first - 1].soc_kwh if first else soc0_kwh
        price = None
        if energy and action != "idle":
            use_import = action == "charge"
            price = sum(abs(plan.slots[i].battery_kwh) * (slots[i].import_price if use_import else slots[i].export_price) for i in run) / energy
        segments.append({"from": (slot_start + first * QUARTER).isoformat(), "to": (slot_start + (last + 1) * QUARTER).isoformat(),
                         "action": action, "kwh": round(energy, 2), "avg_w": round(energy / (len(run) * SLOT_H) * 1000) if action != "idle" else 0,
                         "soc_from_pct": round(before / capacity_kwh * 100, 1), "soc_to_pct": round(plan.slots[last].soc_kwh / capacity_kwh * 100, 1),
                         "avg_price": _round(price, 4)})
    if len(runs) > limit:
        segments.append({"truncated": len(runs) - limit})
    return segments


def plan_detail(decision: "Decision") -> dict:
    """Every planned quarter as compact parallel arrays, with the prices, load and PV the plan was computed from.

    a: action letters (c/d/i), c: reason letters (s sell, b buy, h hold, f floor, v full), w: AC watts (+ charge),
    soc: kWh after the quarter, grid: kWh (+ import), keep/sell/buy: EUR per stored kWh, imp/exp: EUR/kWh,
    load/pv: kWh per quarter. Index i is the quarter starting at `start` + 15 minutes * i."""
    planned = decision.plan.slots
    return {"cycle": decision.slot_start.isoformat(), "start": decision.slot_start.isoformat(), "n": len(planned),
            "a": "".join(ACTION_LETTER[p.action] for p in planned), "c": "".join(CODE_LETTER.get(p.reason_code, "-") for p in planned),
            "w": [round(p.battery_kwh / SLOT_H * 1000) for p in planned], "soc": [round(p.soc_kwh, 2) for p in planned],
            "grid": [round(p.grid_kwh, 3) for p in planned], "keep": [_round(p.stored_value, 4) for p in planned],
            "sell": [_round(p.sell_value, 4) for p in planned], "buy": [_round(p.buy_cost, 4) for p in planned],
            "imp": [round(s.import_price, 4) for s in decision.slots], "exp": [round(s.export_price, 4) for s in decision.slots],
            "load": [round(s.load_kwh, 3) for s in decision.slots], "pv": [round(s.pv_kwh, 3) for s in decision.slots]}


def settings_snapshot(parts: Mapping[str, object]) -> dict:
    """The settings in force and a short hash of them, so a change between two cycles is visible as a new hash."""
    values = {name: asdict(part) if is_dataclass(part) else str(part) for name, part in parts.items()}
    digest = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return {"hash": digest, "values": values}
