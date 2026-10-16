#!/usr/bin/env python3
"""Replay the HEMS planner over the locally recorded days and compare it with what the real battery did.

Repo-specific on purpose (entity ids of this installation live here, never in hems/core). Inputs:
  docs/hems/observations/data/hourly.jsonl            hourly means from scripts/hems_collect.py (gitignored)
  hems/core/tests/fixtures/quarter_import_prices.csv  recorder export of sensor.current_price (ends at 12 Oct 2026)
  docs/hems/observations/data/trace/plans.jsonl        the prices of every later day, as HEMS planned on them (after `hems_trace.py --pull`)

Hourly means are spread evenly over the four quarters of the hour, for the planner run and the recorded battery
alike, so intra-hour structure (a 45-minute sell window) is not visible in either. Prints a markdown report.

Usage: python3 scripts/hems_replay.py [--from 2026-10-04] [--to 2026-10-12] [--write docs/hems/observations/replay.md]
"""
import argparse
import csv
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hems" / "core"))

from hems.battery import BatteryConfig  # noqa: E402
from hems.forecast import LOCAL_TZ  # noqa: E402
from hems.prices import PriceModel, PriceSeries, curves  # noqa: E402
from hems.replay import ReplayData, account, run_replay  # noqa: E402
from hems.solar import is_daylight  # noqa: E402

HOURLY = ROOT / "docs" / "hems" / "observations" / "data" / "hourly.jsonl"
PRICES = ROOT / "hems" / "core" / "tests" / "fixtures" / "quarter_import_prices.csv"
TRACE_PLANS = ROOT / "docs" / "hems" / "observations" / "data" / "trace" / "plans.jsonl"
LAT, LON = 52.0907, 5.1214
E_SOC, E_BATT, E_PV = "sensor.battery_api_battery_soc", "sensor.battery_api_battery_power", "sensor.battery_api_pv_power"
E_P1, E_INV, E_EV = "sensor.power_usage", "sensor.saj_total_grid_power", "sensor.charge_amps_monitor_charger_current_power"


def load_hourly() -> dict[datetime, dict]:
    """Hourly collector rows keyed by UTC hour start."""
    rows = {}
    for line in HOURLY.read_text().splitlines():
        row = json.loads(line)
        rows[datetime.fromisoformat(row["hour_utc"])] = row["v"]
    return rows


def mean(v: dict, entity: str, field: str = "mean") -> float:
    """A collector aggregate, 0.0 when the entity or the hour is missing."""
    return (v.get(entity) or {}).get(field) or 0.0


def trace_prices() -> dict[datetime, tuple[float, float]]:
    """Consumer import and export price per quarter (UTC) from the logged plans; a later cycle overrides an earlier one."""
    prices: dict[datetime, tuple[float, float]] = {}
    if TRACE_PLANS.exists():
        for line in TRACE_PLANS.read_text().splitlines():
            plan = json.loads(line)
            start = datetime.fromisoformat(plan["start"])
            for k, (imp, exp) in enumerate(zip(plan["imp"], plan["exp"])):
                prices[start + timedelta(minutes=15 * k)] = (imp, exp)
    return prices


def load_prices(model: PriceModel, later: dict[datetime, tuple[float, float]] | None = None) -> PriceSeries:
    """Consumer prices per quarter from the recorder export (export price daylight-aware), then the quarters of `later` it does not have."""
    with PRICES.open(newline="") as handle:
        rows = [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"])) for r in csv.DictReader(handle)]
    market = [model.market_from_import(p) for _, p in rows]
    imp, exp = curves(market, model, [is_daylight(t, LAT, LON) for t, _ in rows])
    known = {t: (i, e) for (t, _), i, e in zip(rows, imp, exp)}
    for start, pair in (later or {}).items():
        known.setdefault(start, pair)
    starts = sorted(known)
    return PriceSeries(tuple(starts), tuple(known[t][0] for t in starts), tuple(known[t][1] for t in starts))


def build(prices: PriceSeries, hourly: dict, first: datetime, last: datetime, capacity_kwh: float) -> ReplayData:
    """Replay inputs for [first, last): base load = P1 + inverter output - EV, PV, and the recorded battery flow."""
    keep = [i for i, s in enumerate(prices.starts) if first <= s < last]
    sl = PriceSeries(*(tuple(getattr(prices, f)[i] for i in keep) for f in ("starts", "import_eur_kwh", "export_eur_kwh")))
    if not sl.starts:
        raise SystemExit(f"No prices between {first:%Y-%m-%d %H:%M} and {last:%Y-%m-%d %H:%M} UTC: the recorder export ends at 12 Oct 2026; "
                         "pull the logs (`python3 scripts/hems_trace.py --pull`) for later days.")
    missing = next((s for s in sl.starts if s.replace(minute=0) not in hourly), None)
    if missing or first.replace(minute=0) - timedelta(hours=1) not in hourly:
        raise SystemExit(f"No hourly battery/PV/load data for {missing or first:%Y-%m-%d %H:%M} UTC: run `python3 scripts/hems_collect.py run --hours 72` first.")
    house, pv, batt = [], [], []
    for start in sl.starts:
        v = hourly[start.replace(minute=0)]
        house.append(max(mean(v, E_P1) + mean(v, E_INV) - mean(v, E_EV), 0.0) / 1000 * 0.25)
        pv.append(mean(v, E_PV) / 1000 * 0.25)
        batt.append(-mean(v, E_BATT) / 1000 * 0.25)               # collector: + = discharging; contract: + = charging
    before = hourly[first.replace(minute=0) - timedelta(hours=1)]
    soc0 = mean(before, E_SOC, "last") / 100 * capacity_kwh
    return ReplayData(sl, tuple(house), tuple(pv), soc0, tuple(batt))


def local_day(start: datetime) -> str:
    """Local calendar day label of a quarter."""
    return start.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


def day_rows(data: ReplayData, sim_flow, recorded_flow, soc_value: float, sim_soc, rec_soc) -> list[str]:
    """Markdown rows per local day: saving without SoC value (EUR) for the planner and for the recorded battery."""
    rows, days = [], sorted({local_day(s) for s in data.prices.starts})
    for day in days:
        idx = [i for i, s in enumerate(data.prices.starts) if local_day(s) == day]
        sub = ReplayData(PriceSeries(*(tuple(getattr(data.prices, f)[i] for i in idx) for f in ("starts", "import_eur_kwh", "export_eur_kwh"))),
                         tuple(data.house_kwh[i] for i in idx), tuple(data.pv_kwh[i] for i in idx), 0.0)
        ds = sim_soc[idx[-1]] - (sim_soc[idx[0] - 1] if idx[0] else data.soc0_kwh)
        dr = rec_soc[idx[-1]] - (rec_soc[idx[0] - 1] if idx[0] else data.soc0_kwh)
        sim = account(sub, [sim_flow[i] for i in idx], ds)
        rec = account(sub, [recorded_flow[i] for i in idx], dr)
        rows.append(f"| {day} | {sim.baseline_eur - sim.cost_eur:+.2f} | {ds:+.1f} | {rec.baseline_eur - rec.cost_eur:+.2f} | {dr:+.1f} |"
                    f" {sim.valued_saving(soc_value):+.2f} | {rec.valued_saving(soc_value):+.2f} |")
    return rows


def recorded_soc(hourly: dict, data: ReplayData, capacity_kwh: float) -> list[float]:
    """Recorded SoC (kWh) at the end of each quarter, from the hourly last value (constant within the hour)."""
    return [mean(hourly[s.replace(minute=0)], E_SOC, "last") / 100 * capacity_kwh for s in data.prices.starts]


def window(data: ReplayData, sim, rec_flow, days: list[str], soc_value: float, rec_soc: list[float]) -> tuple[float, float]:
    """(planner, recorded) cash saving versus no battery over the local days, valued with the SoC left behind."""
    idx = [i for i, s in enumerate(data.prices.starts) if local_day(s) in days]
    prices = data.prices
    sub = ReplayData(PriceSeries(*(tuple(getattr(prices, f)[i] for i in idx) for f in ("starts", "import_eur_kwh", "export_eur_kwh"))),
                     tuple(data.house_kwh[i] for i in idx), tuple(data.pv_kwh[i] for i in idx), 0.0)
    before = lambda series: series[idx[0] - 1] if idx[0] else data.soc0_kwh
    s = account(sub, [sim.battery_kwh[i] for i in idx], sim.soc_kwh[idx[-1]] - before(sim.soc_kwh))
    r = account(sub, [rec_flow[i] for i in idx], rec_soc[idx[-1]] - before(rec_soc))
    return s.valued_saving(soc_value), r.valued_saving(soc_value)


def main() -> int:
    """Replay the planner in several variants, print the markdown report, and fail when the acceptance criteria fail."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="first", default="2026-10-04")
    ap.add_argument("--to", dest="last", default="2026-10-12")
    ap.add_argument("--write")
    a = ap.parse_args()
    first = datetime.fromisoformat(a.first).replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    last = datetime.fromisoformat(a.last).replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    hourly = load_hourly()
    later = trace_prices()
    base_cfg = BatteryConfig()
    variants = [
        ("reserve 30 %, bonus switches on (default)", base_cfg, PriceModel()),
        ("reserve 5 % (as the system ran)", replace(base_cfg, reserve_soc=0.05), PriceModel()),
        ("reserve 30 %, bonus always (as energy-prices code)", base_cfg, PriceModel(bonus_only_daylight=False, bonus_only_positive_price=False)),
        ("reserve 30 %, round trip 0.90", replace(base_cfg, round_trip_eff=0.90), PriceModel()),
        ("reserve 30 %, minimum profit margin 0.05", replace(base_cfg, min_profit_margin=0.05), PriceModel()),
        ("reserve 30 %, minimum profit margin 0.00", replace(base_cfg, min_profit_margin=0.0), PriceModel()),
        ("reserve 30 %, waiting cost off (0)", replace(base_cfg, hold_cost_kwh_h=0.0), PriceModel()),
        ("reserve 30 %, waiting cost 0.001 EUR/kWh/h", replace(base_cfg, hold_cost_kwh_h=0.001), PriceModel()),
        ("reserve 30 %, waiting cost 0.005 EUR/kWh/h", replace(base_cfg, hold_cost_kwh_h=0.005), PriceModel()),
    ]
    out = [f"# HEMS replay {a.first} to {a.last} (generated by scripts/hems_replay.py)", "",
           "Planner: rolling horizon, prices as published (tomorrow after 13:00 local), load and PV known (oracle). "
           "Savings in EUR versus no battery, valued with the SoC left behind at the 20th-percentile import price. "
           "All figures are cash (the grid bill); the minimum profit margin shapes the planner's decisions and is never counted as a cost. "
           "Recorded = what the real battery did, accounted the same way.", ""]
    failures: list[str] = []
    for label, cfg, model in variants:
        prices = load_prices(model, later)
        data = build(prices, hourly, first, last, cfg.capacity_kwh)
        soc_value = sorted(data.prices.import_eur_kwh)[len(data.prices.import_eur_kwh) // 5]
        sim = run_replay(data, cfg)
        rec_soc = recorded_soc(hourly, data, cfg.capacity_kwh)
        present = {local_day(s) for s in data.prices.starts}
        pairs = {name: days for name, days in {"6 Oct": ["2026-10-06"], "7+8 Oct": ["2026-10-07", "2026-10-08"], "9 Oct": ["2026-10-09"]}.items()
                 if set(days) <= present}
        pairs["whole period"] = sorted(present)
        out += [f"## {label}", "", "| window | planner | recorded |", "|---|---|---|"]
        for name, days in pairs.items():
            planner, recorded = window(data, sim, data.recorded_battery_kwh, days, soc_value, rec_soc)
            out.append(f"| {name} | {planner:+.2f} | {recorded:+.2f} |")
            if label.startswith("reserve 30 %, bonus switches") and name != "whole period" and planner < -0.05:
                failures.append(f"{name}: planner cash saving {planner:+.2f} < -0.05")
        out += ["", f"Quarters where the replanned quarter moved >25 %: {len(sim.shifts)} of {len(sim.decisions)}", ""]
        if label.startswith("reserve 30 %, bonus switches"):
            out += ["| day | planner | planner dSoC kWh | recorded | recorded dSoC kWh | planner valued | recorded valued |", "|---|---|---|---|---|---|---|"]
            out += day_rows(data, sim.battery_kwh, data.recorded_battery_kwh, soc_value, sim.soc_kwh, rec_soc) + [""]
        print(f"done: {label}", file=sys.stderr)
    out += ["## Acceptance (default variant)", "", "Planner cash saving >= -0.05 EUR on 6 Oct, 7+8 Oct and 9 Oct: "
            + ("PASS" if not failures else "FAIL " + "; ".join(failures)), ""]
    text = "\n".join(out)
    print(text)
    if a.write:
        (ROOT / a.write).write_text(text + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
