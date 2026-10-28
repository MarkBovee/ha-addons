"""One replay of the terminal-value study: a margin and a terminal mode over one of two chains of recorded days (read-only).

    python3 scripts/hems_terminal_study.py CHAIN MARGIN MODE      # CHAIN A = 7-12 Oct, B = 14-19 Oct; MODE default | h0 | h03 | h06

`default` values the energy left at the end of the horizon at the cheapest import price; `hN` at the typical peak of the last days
(hems.terminal) with a haircut of N hundredths EUR per kWh. Prints `chain margin mode cash kWh/day rec recorded-cash`. Run the 40 combinations in
parallel with xargs -P: a sequential run of one chain takes minutes per combination. Results: docs/hems/observations/margin-study-2026-10-17.md.
"""
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hems" / "core"))

import hems_replay as replay  # noqa: E402
from hems.battery import BatteryConfig  # noqa: E402
from hems.prices import PriceModel  # noqa: E402
from hems.terminal import daily_peaks  # noqa: E402

CHAINS = {"A": ("2026-10-07", "2026-10-13"), "B": ("2026-10-14", "2026-10-20")}
HAIRCUTS = {"default": 0.0, "h0": 0.0, "h03": 0.03, "h06": 0.06}


def local_midnight(day: str) -> datetime:
    """UTC moment of 00:00 local on `day` (YYYY-MM-DD)."""
    return datetime.fromisoformat(day).replace(tzinfo=replay.LOCAL_TZ).astimezone(timezone.utc)


def main() -> int:
    """Replay one chain with one margin and terminal mode and print cash, kWh per day and what the real battery earned."""
    chain, margin, mode = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    base, hourly = BatteryConfig(), replay.load_hourly()
    prices = replay.load_prices(PriceModel(), replay.trace_prices())
    first, last = CHAINS[chain]
    data = replay.build(prices, hourly, local_midnight(first), local_midnight(last), base.capacity_kwh)
    soc_value = sorted(data.prices.import_eur_kwh)[len(data.prices.import_eur_kwh) // 5]
    days = sorted({replay.local_day(s) for s in data.prices.starts})
    recorded_soc = replay.recorded_soc(hourly, data, base.capacity_kwh)
    cfg = replace(base, min_profit_margin=margin, future_peak_haircut=HAIRCUTS[mode])
    sim = replay.run_replay(data, cfg, peaks=None if mode == "default" else daily_peaks(prices, replay.LOCAL_TZ))
    planner, recorded = replay.window(data, sim, data.recorded_battery_kwh, days, soc_value, recorded_soc)
    discharged = sum(-x for x in sim.battery_kwh if x < 0)
    print(f"{chain} {margin:.2f} {mode} {planner:+.2f} {discharged / len(days):.1f} rec {recorded:+.2f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
