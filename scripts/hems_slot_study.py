#!/usr/bin/env python3
"""How many SAJ time slots the live HEMS plans need, and what merging short pauses into one slot costs.

A SAJ slot is one start, one end and one power for every day (seven for charging, seven for discharging). A plan that
charges or sells in pieces needs one slot per piece. This study reads every logged plan (docs/hems/observations/data/
trace/plans.jsonl, after `hems_trace.py --pull`) and, for the coming 24 hours of each plan:

  * counts the pieces (runs of charge and of discharge quarters) as planned;
  * merges pieces of the same action whose gap is at most G idle quarters, spreads the same energy evenly over the
    merged block (one slot, one power) and prices the difference with the plan's own prices: the import price where
    the plan imports in that quarter, the export price where it exports.

The money is an estimate: the planner would re-plan around a merged block, so the real cost is at most this.

Usage: python3 scripts/hems_slot_study.py [--from 2026-10-17] [--gaps 0,1,2,3,4] [--write docs/hems/observations/slot-study.md]
"""
import argparse
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "docs" / "hems" / "observations" / "data" / "trace" / "plans.jsonl"
TZ = ZoneInfo("Europe/Amsterdam")
SAJ_SLOTS = 7               # per direction
DAY_QUARTERS = 96
NOON_HOUR = 14              # the plan made after the day-ahead prices are in is the one that shapes the evening


@dataclass(frozen=True)
class Piece:
    """A run of quarters with the same action ('c' or 'd'), as indices into the plan."""
    action: str
    first: int
    last: int


@dataclass(frozen=True)
class PlanResult:
    """Slots needed and the cost of merging for one plan and one gap size."""
    start: datetime
    gap: int
    charge_slots: int
    discharge_slots: int
    cost_eur: float          # extra cost of the merged plan over the plan as made (positive = merging costs money)


# Runs of 'c' and 'd' in the action string, within the first `n` quarters.
def pieces(actions: str, n: int) -> list[Piece]:
    out: list[Piece] = []
    for i, a in enumerate(actions[:n]):
        if a not in "cd":
            continue
        if out and out[-1].action == a and out[-1].last == i - 1:
            out[-1] = Piece(a, out[-1].first, i)
        else:
            out.append(Piece(a, i, i))
    return out


# Merge pieces of the same action when only idle quarters (at most `gap`) separate them.
def merge(found: list[Piece], actions: str, gap: int) -> list[Piece]:
    merged: list[Piece] = []
    for p in found:
        prev = merged[-1] if merged else None
        between = actions[prev.last + 1:p.first] if prev else ""
        if prev and prev.action == p.action and len(between) <= gap and set(between) <= {"i"}:
            merged[-1] = Piece(p.action, prev.first, p.last)
        else:
            merged.append(p)
    return merged


# Price of one kWh moved in quarter i: what the plan pays on import or gets on export there.
def marginal_price(plan: dict, i: int) -> float:
    return plan["imp"][i] if plan["grid"][i] > 0 else plan["exp"][i]


# Extra cost of running a merged block at one constant power instead of the planned quarter powers.
def block_cost(plan: dict, block: Piece) -> float:
    idx = range(block.first, block.last + 1)
    kwh = [plan["w"][i] / 4000 for i in idx]                 # AC kWh per quarter, + charge / - discharge
    even = sum(kwh) / len(kwh)
    # a charge kWh costs its price, a discharge kWh (negative) earns it: cost = sum(kWh * price) either way
    return sum((even - k) * marginal_price(plan, i) for k, i in zip(kwh, idx))


# Slots and merge cost of one plan for one gap size, over its coming 24 hours.
def study_plan(plan: dict, gap: int) -> PlanResult:
    n = min(plan["n"], DAY_QUARTERS)
    blocks = merge(pieces(plan["a"], n), plan["a"], gap)
    cost = sum(block_cost(plan, b) for b in blocks)
    return PlanResult(datetime.fromisoformat(plan["start"]), gap, sum(b.action == "c" for b in blocks),
                      sum(b.action == "d" for b in blocks), cost)


# Logged plans from a local date on.
def load_plans(since: datetime) -> list[dict]:
    plans = []
    for line in PLANS.read_text().splitlines():
        plan = json.loads(line)
        if datetime.fromisoformat(plan["start"]) >= since and "w" in plan and "imp" in plan:
            plans.append(plan)
    return plans


# One afternoon plan per local day: the first one at or after NOON_HOUR.
def afternoon_plans(plans: list[dict]) -> list[dict]:
    seen, out = set(), []
    for plan in plans:
        local = datetime.fromisoformat(plan["start"]).astimezone(TZ)
        if local.hour >= NOON_HOUR and local.date() not in seen:
            seen.add(local.date())
            out.append(plan)
    return out


# Markdown report: all cycles summarised per gap size, then the afternoon plan of each day.
def report(plans: list[dict], gaps: list[int]) -> str:
    lines = [f"# SAJ-sloten en het samenvoegen van pauzes ({len(plans)} plannen)", "",
             "Per plan de komende 24 uur. Kosten: wat één slot op vast vermogen extra kost tegenover het plan zoals het is gemaakt "
             "(bovengrens, de planner zou eromheen herplannen).", "",
             "| Gat ≤ | Laadsloten mediaan / max | Ontlaadsloten mediaan / max | Plannen > 7 sloten | Kosten mediaan | Kosten p90 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for gap in gaps:
        rows = [study_plan(p, gap) for p in plans]
        over = sum(r.charge_slots > SAJ_SLOTS or r.discharge_slots > SAJ_SLOTS for r in rows)
        costs = sorted(r.cost_eur for r in rows)
        lines.append(f"| {gap} | {statistics.median(r.charge_slots for r in rows):.0f} / {max(r.charge_slots for r in rows)} "
                     f"| {statistics.median(r.discharge_slots for r in rows):.0f} / {max(r.discharge_slots for r in rows)} "
                     f"| {over} ({over / len(rows):.0%}) | € {statistics.median(costs):.3f} | € {costs[int(0.9 * (len(costs) - 1))]:.3f} |")
    lines += ["", f"## Middagplan per dag (eerste plan na {NOON_HOUR}:00)", "",
              "| Dag | " + " | ".join(f"gat ≤ {g}: sloten (c/d), kosten" for g in gaps) + " |", "| --- |" + " --- |" * len(gaps)]
    for plan in afternoon_plans(plans):
        day = datetime.fromisoformat(plan["start"]).astimezone(TZ).strftime("%a %d %b")
        cells = [study_plan(plan, g) for g in gaps]
        lines.append(f"| {day} | " + " | ".join(f"{r.charge_slots}/{r.discharge_slots}, € {r.cost_eur:.2f}" for r in cells) + " |")
    return "\n".join(lines) + "\n"


# Command line entry point.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="since", default="2026-10-17")
    parser.add_argument("--gaps", default="0,1,2,3,4")
    parser.add_argument("--write")
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since).replace(tzinfo=TZ)
    text = report(load_plans(since), [int(g) for g in args.gaps.split(",")])
    if args.write:
        Path(args.write).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
