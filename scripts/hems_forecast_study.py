"""Replay recorded days with the forecasts HEMS really had, against the oracle of recorded load and PV (read-only).

    python3 scripts/hems_forecast_study.py MARGIN MODE      # MODE oracle | logged

The days are 14 to 19 Oct 2026 as one chain (the logged plans, `hems_trace.py --pull`, start on 13 Oct). In `logged` mode the planner of each quarter
gets the load and PV forecast of the cycle HEMS logged in that quarter (`plans.jsonl`: what it expected, builds and all); the simulated battery
and the accounting use what really happened (`hems_collect.py`), so forecast errors cost what they cost. Prints `margin mode cash kWh/day rec recorded-cash`.
"""
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hems" / "core"))

import hems_replay as replay  # noqa: E402
from hems.battery import BatteryConfig  # noqa: E402
from hems.prices import PriceModel  # noqa: E402

QUARTER = timedelta(minutes=15)
FIRST, LAST = "2026-10-14", "2026-10-20"


def local_midnight(day: str) -> datetime:
    """UTC moment of 00:00 local on `day` (YYYY-MM-DD)."""
    return datetime.fromisoformat(day).replace(tzinfo=replay.LOCAL_TZ).astimezone(timezone.utc)


def logged_forecasts() -> dict[datetime, tuple[dict[datetime, float], dict[datetime, float]]]:
    """Per cycle (quarter start, UTC) the load and PV forecast HEMS logged then; a later line of the same cycle (a restart) wins."""
    found: dict[datetime, tuple[dict, dict]] = {}
    for line in replay.TRACE_PLANS.read_text().splitlines():
        plan = json.loads(line)
        start = datetime.fromisoformat(plan["start"])
        found[datetime.fromisoformat(plan["cycle"])] = ({start + k * QUARTER: v for k, v in enumerate(plan["load"])},
                                                         {start + k * QUARTER: v for k, v in enumerate(plan["pv"])})
    return found


def main() -> int:
    """Replay the chain once and print cash, kWh per day and what the real battery earned."""
    margin, mode = float(sys.argv[1]), sys.argv[2]
    base, hourly = BatteryConfig(), replay.load_hourly()
    prices = replay.load_prices(PriceModel(), replay.trace_prices())
    data = replay.build(prices, hourly, local_midnight(FIRST), local_midnight(LAST), base.capacity_kwh)
    soc_value = sorted(data.prices.import_eur_kwh)[len(data.prices.import_eur_kwh) // 5]
    days = sorted({replay.local_day(s) for s in data.prices.starts})
    recorded_soc = replay.recorded_soc(hourly, data, base.capacity_kwh)
    logged = logged_forecasts() if mode == "logged" else None
    sim = replay.run_replay(data, replace(base, min_profit_margin=margin), forecasts=(lambda start: logged.get(start)) if logged else None)
    planner, recorded = replay.window(data, sim, data.recorded_battery_kwh, days, soc_value, recorded_soc)
    discharged = sum(-x for x in sim.battery_kwh if x < 0)
    missing = sum(1 for s in data.prices.starts if logged is not None and s not in logged)
    print(f"{margin:.2f} {mode} {planner:+.2f} {discharged / len(days):.1f} rec {recorded:+.2f}" + (f" (quarters without a logged cycle: {missing})" if logged else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
