"""Margin and parameter sweep per recorded day: how much cash the HEMS planner makes against the real battery (read-only).

Replays the planner on the collected hourly data (`hems_collect.py`) and the prices of the logged plans (`hems_trace.py --pull`), one local
day at a time from the recorded SoC at its start, once per variant, and prints a table of cash saving versus no battery per day. Load and PV
are the recorded ones (an oracle): this is the planner's economic ceiling, not a forecast-driven result.

    python3 scripts/hems_margin_study.py [--first 2026-10-07] [--last 2026-10-16]
"""
import argparse
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hems" / "core"))

import hems_replay as replay  # noqa: E402
from hems.battery import BatteryConfig  # noqa: E402
from hems.prices import PriceModel  # noqa: E402

MARGINS = (0.0, 0.03, 0.05, 0.08, 0.10, 0.12)


def local_midnight(day: str) -> datetime:
    """UTC moment of 00:00 local on `day` (YYYY-MM-DD)."""
    return datetime.fromisoformat(day).replace(tzinfo=replay.LOCAL_TZ).astimezone(timezone.utc)


def variants(base: BatteryConfig) -> dict[str, BatteryConfig]:
    """The configurations to compare: the margin sweep, and the waiting cost and the reserve at a margin of 0.05."""
    found = {f"m{margin:.2f}": replace(base, min_profit_margin=margin) for margin in MARGINS}
    found["m0.05 hold0"] = replace(base, min_profit_margin=0.05, hold_cost_kwh_h=0.0)
    found["m0.05 res5"] = replace(base, min_profit_margin=0.05, reserve_soc=0.05)
    return found


def blocks(first: str, last: str) -> list[tuple[str, str]]:
    """Replay windows [from, to): the first days as one block, every later day alone.

    The recorder export of prices ends on 12 Oct and the logged plans start on 13 Oct at about 12:30, so a window that crosses
    that gap has no prices for part of a day: 13 Oct is left out, and from 14 Oct on each day is replayed from its own recorded start."""
    out, day, end = [], datetime.fromisoformat(first), datetime.fromisoformat(last) + timedelta(days=1)
    if day < datetime(2026, 10, 13):
        out.append((first, "2026-10-13"))
    day = max(day, datetime(2026, 10, 14))
    while day < end:
        out.append((day.date().isoformat(), (day + timedelta(days=1)).date().isoformat()))
        day += timedelta(days=1)
    return out


def main() -> int:
    """Print cash saving per day and variant, with what the real battery did the same day."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--first", default="2026-10-07")
    parser.add_argument("--last", default="2026-10-16")
    args = parser.parse_args()
    base, hourly = BatteryConfig(), replay.load_hourly()
    prices = replay.load_prices(PriceModel(), replay.trace_prices())
    configs = variants(base)
    saved: dict[str, dict[str, tuple[float, float]]] = {name: {} for name in configs}
    for first, last in blocks(args.first, args.last):
        try:
            data = replay.build(prices, hourly, local_midnight(first), local_midnight(last), base.capacity_kwh)
        except SystemExit as err:
            print(f"skip {first}: {str(err)[:100]}", file=sys.stderr)
            continue
        soc_value = sorted(data.prices.import_eur_kwh)[len(data.prices.import_eur_kwh) // 5]
        days = sorted({replay.local_day(s) for s in data.prices.starts})
        recorded_soc = replay.recorded_soc(hourly, data, base.capacity_kwh)
        for name, cfg in configs.items():
            sim = replay.run_replay(data, cfg)
            for day in days:
                saved[name][day] = replay.window(data, sim, data.recorded_battery_kwh, [day], soc_value, recorded_soc)
    names = list(configs)
    days = sorted(saved[names[0]])
    print("| day | " + " | ".join(names) + " | recorded |")
    print("|---|" + "---|" * (len(names) + 1))
    for day in days:
        print(f"| {day} | " + " | ".join(f"{saved[n][day][0]:+.2f}" for n in names) + f" | {saved[names[0]][day][1]:+.2f} |")
    print("| total | " + " | ".join(f"{sum(v[0] for v in saved[n].values()):+.2f}" for n in names) + f" | {sum(v[1] for v in saved[names[0]].values()):+.2f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
