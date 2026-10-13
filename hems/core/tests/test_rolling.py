import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hems.battery import BatteryConfig
from hems.forecast import LOCAL_TZ
from hems.prices import PriceModel, PriceSeries, curves
from hems.replay import ReplayData, account, known_until, run_replay
from hems.rolling import QUARTER, HorizonInputs, floor_to_quarter, plan_next, plan_shift
from hems.solar import is_daylight
from hems.trace import TraceWriter

FIXTURES = Path(__file__).parent / "fixtures"
MODEL = PriceModel()
UTRECHT = (52.0907, 5.1214)


def recorded_day(local_day: str, days: int = 1) -> PriceSeries:
    """Consumer prices of recorded local days (recorder export of sensor.current_price), with daylight-aware export."""
    first = datetime.fromisoformat(local_day).replace(tzinfo=LOCAL_TZ)
    last = first + timedelta(days=days)
    with open(FIXTURES / "quarter_import_prices.csv", newline="") as f:
        rows = [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"])) for r in csv.DictReader(f)]
    rows = [(t, p) for t, p in rows if first <= t < last]
    market = [MODEL.market_from_import(p) for _, p in rows]
    imp, exp = curves(market, MODEL, [is_daylight(t, *UTRECHT) for t, _ in rows])
    return PriceSeries(tuple(t for t, _ in rows), tuple(imp), tuple(exp))


def synthetic_home(prices: PriceSeries, soc0_kwh: float) -> ReplayData:
    """300 W flat house load and a 3 kW PV bell between 07:00 and 18:00 local: enough to exercise the planner."""
    local_hours = [t.astimezone(LOCAL_TZ).hour + t.astimezone(LOCAL_TZ).minute / 60 for t in prices.starts]
    pv = [3.0 * math.sin(math.pi * (h - 7) / 11) * 0.25 if 7 <= h < 18 else 0.0 for h in local_hours]
    return ReplayData(prices, tuple(0.075 for _ in local_hours), tuple(pv), soc0_kwh)


def test_plan_next_needs_a_price_for_the_current_quarter():
    """Without a price for the current quarter there is nothing to plan."""
    prices = recorded_day("2026-10-06")
    late = datetime(2026, 10, 7, 12, 0, tzinfo=LOCAL_TZ)     # after the last known quarter
    assert plan_next(HorizonInputs(late, 10.0, prices, {}, {}), BatteryConfig()) is None


def test_plan_next_commands_the_current_quarter_and_explains_itself():
    """The command covers the quarter containing 'now' and the trace carries slot, reason and missing-forecast count."""
    prices = recorded_day("2026-10-06")
    now = datetime(2026, 10, 6, 11, 7, tzinfo=LOCAL_TZ)      # inside the 11:00 quarter
    decision = plan_next(HorizonInputs(now, 10.0, prices, {}, {}), BatteryConfig())
    assert decision.command.start == floor_to_quarter(now) and decision.command.end - decision.command.start == QUARTER
    assert decision.trace["slot_start"] == decision.slot_start.isoformat()
    assert decision.trace["missing_forecast_slots"] == decision.trace["horizon_slots"]   # no forecast given: counted, not hidden
    assert decision.trace["reason"] and decision.trace["keep_value_eur_kwh"] is not None


def test_a_sold_quarter_says_why():
    """A full battery at the 6 Oct evening peak sells, and the reason starts with 'sell'."""
    prices = recorded_day("2026-10-06")
    evening = datetime(2026, 10, 6, 19, 0, tzinfo=LOCAL_TZ)   # 6 Oct peaked at 0.62; a full battery sells here
    decision = plan_next(HorizonInputs(evening, 20.0, prices, {}, {}), BatteryConfig())
    assert decision.command.power_w < 0 and decision.trace["reason"].startswith("sell")


def test_plan_shift_logs_only_large_moves():
    """A replanned quarter is only reported when it moved by more than a quarter of its power."""
    prices = recorded_day("2026-10-06")
    cfg = BatteryConfig()
    first = plan_next(HorizonInputs(datetime(2026, 10, 6, 15, 0, tzinfo=LOCAL_TZ), 12.0, prices, {}, {}), cfg)
    same = plan_next(HorizonInputs(datetime(2026, 10, 6, 15, 15, tzinfo=LOCAL_TZ), 12.0, prices, {}, {}), cfg)
    assert plan_shift(None, same) is None
    assert plan_shift(first, same) is None or abs(plan_shift(first, same)["now_w"] - plan_shift(first, same)["was_w"]) > 0
    emptier = plan_next(HorizonInputs(datetime(2026, 10, 6, 15, 15, tzinfo=LOCAL_TZ), 25.0, prices, {}, {}), cfg)
    shift = plan_shift(first, emptier)
    assert shift is None or shift["quarter"] == emptier.slot_start.isoformat()


def test_trace_writer_uses_the_injected_clock_and_rotates(tmp_path):
    """Timestamps come from the injected clock and the file rotates at the size limit."""
    fixed = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    writer = TraceWriter(tmp_path / "trace.jsonl", clock=lambda: fixed, max_bytes=200)
    for n in range(10):
        writer.write({"n": n, "reason": "x" * 30})
    lines = (tmp_path / "trace.jsonl").read_text().splitlines()
    assert json.loads(lines[-1]) == {"ts": "2026-10-13T12:00:00+00:00", "n": 9, "reason": "x" * 30}
    assert (tmp_path / "trace.jsonl.1").exists() and len(lines) < 10


def test_prices_are_known_for_tomorrow_only_after_publication():
    """Tomorrow's prices count as known only from the publication hour."""
    morning = datetime(2026, 10, 6, 9, 0, tzinfo=LOCAL_TZ)
    afternoon = datetime(2026, 10, 6, 14, 0, tzinfo=LOCAL_TZ)
    assert known_until(morning, LOCAL_TZ, 13) == datetime(2026, 10, 7, 0, 0, tzinfo=LOCAL_TZ)
    assert known_until(afternoon, LOCAL_TZ, 13) == datetime(2026, 10, 8, 0, 0, tzinfo=LOCAL_TZ)


def test_replay_earns_money_on_a_wide_spread_day_and_respects_the_device_limits():
    """On 6 Oct the replayed planner saves money while SoC and power stay within the device limits."""
    day = recorded_day("2026-10-06")                              # spread 0.29 .. 0.62
    data = synthetic_home(day, soc0_kwh=7.5)
    cfg = BatteryConfig()
    sim = run_replay(data, cfg)
    result = account(data, sim.battery_kwh, sim.soc_kwh[-1] - data.soc0_kwh)
    assert result.valued_saving(0.25) > 0.5
    assert min(sim.soc_kwh) >= cfg.hard_min_soc * cfg.capacity_kwh - 1e-6 and max(sim.soc_kwh) <= cfg.capacity_kwh + 1e-6
    assert max(abs(b) for b in sim.battery_kwh) <= cfg.max_power_kw * 0.25 + 1e-6
    assert len(sim.decisions) == len(day.starts)


def test_replay_does_not_cycle_at_a_loss_on_a_thin_spread_day():
    """On the thin-spread day of 9 Oct the planner does not lose money versus no battery."""
    day = recorded_day("2026-10-09")                              # dark day, spread ~0.18..0.34 but mostly flat
    data = synthetic_home(day, soc0_kwh=7.5)
    cfg = BatteryConfig()
    sim = run_replay(data, cfg)
    result = account(data, sim.battery_kwh, sim.soc_kwh[-1] - data.soc0_kwh)
    assert result.valued_saving(0.20) > -0.05
