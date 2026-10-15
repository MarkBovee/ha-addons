import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_rolling import recorded_day

from hems.battery import BatteryConfig, Plan, PlanSlot, Slot, plan
from hems.forecast import LOCAL_TZ
from hems.windows import KEPT_FOR_LATER, NO_STOCK, PLANNED, analyse, detect, record

FIXTURES = Path(__file__).parent / "fixtures"
CFG = BatteryConfig()
QUARTER = timedelta(minutes=15)
DAY = datetime(2026, 10, 14, 22, 0, tzinfo=timezone.utc)       # 00:00 local on 15 Oct


def real_day(day: int) -> tuple[list[datetime], list[float], list[float]]:
    """Quarter starts, import and export prices of a recorded real day (14 or 15 Oct 2026)."""
    with (FIXTURES / f"real_prices_2026_10_{day}.csv").open(newline="") as f:
        rows = [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"]), float(r["export_price_eur_kwh"])) for r in csv.DictReader(f)]
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]


def hhmm(moment: datetime) -> str:
    """Local time of day of a UTC moment."""
    return moment.astimezone(LOCAL_TZ).strftime("%H:%M")


def run(day: int, soc: float, load: float = 0.1):
    """Plan a real day from `soc` (fraction) and analyse it: (windows analysis, plan)."""
    starts, imp, exp = real_day(day)
    slots = [Slot(i, e, load, 0.0) for i, e in zip(imp, exp)]
    result = plan(slots, soc * CFG.capacity_kwh, CFG)
    return analyse(starts, slots, result, soc * CFG.capacity_kwh, CFG), result


def flat_day(import_price: float, export_price: float, **changes: dict[int, float]) -> tuple[list[datetime], list[float], list[float]]:
    """A day of flat prices; `imp` and `exp` change maps set single quarters by index."""
    starts = [DAY + i * QUARTER for i in range(96)]
    imp, exp = [import_price] * 96, [export_price] * 96
    for t, v in changes.get("imp", {}).items():
        imp[t] = v
    for t, v in changes.get("exp", {}).items():
        exp[t] = v
    return starts, imp, exp


def test_the_two_windows_of_15_oct_and_what_each_needs():
    """The peak of 08:15 (0.489) does not pay on a night charge (needs 0.514) but does when the energy is bought back later (needs 0.382)."""
    starts, imp, exp = real_day(15)
    morning, evening = detect(starts, imp, exp, CFG)
    assert (hhmm(morning.peak_at), morning.peak_price, morning.viable) == ("08:15", 0.4894, "replace")
    assert morning.fresh.headroom < 0 and morning.fresh.threshold == pytest.approx(0.5142, abs=0.001) and hhmm(morning.fresh.at) == "04:15"
    assert morning.replace.headroom > 0.1 and morning.replace.threshold == pytest.approx(0.3821, abs=0.001) and hhmm(morning.replace.at) == "14:00"
    assert (hhmm(evening.peak_at), evening.viable) == ("18:30", "fresh") and hhmm(evening.fresh.at) == "14:00"


def test_a_threshold_is_import_over_round_trip_plus_margin_and_the_carrying_cost_of_waiting():
    """Charge at 0.20 at 02:00, sell at 0.60 at 08:00: 0.20 / 0.82 + 0.10 + 0.002 * 6 h / 0.9055 per kWh stored."""
    starts, imp, exp = flat_day(0.40, 0.30, imp={8: 0.20}, exp={32: 0.60})
    (window,) = detect(starts, imp, exp, CFG)
    carrying = CFG.hold_cost_kwh_h * 6 / CFG.round_trip_eff ** 0.5
    assert window.fresh.threshold == pytest.approx(0.20 / CFG.round_trip_eff + CFG.min_profit_margin + carrying, abs=1e-3)
    assert window.fresh.headroom == pytest.approx(0.60 - window.fresh.threshold, abs=1e-3) and hhmm(window.fresh.at) == "02:00"
    assert window.viable == "both" or window.viable == "fresh"


def test_a_short_dip_inside_a_peak_keeps_one_window_and_a_long_one_splits_it():
    """The dip of one hour is part of the same window (the plan sells around it); two hours apart is another window."""
    peak = {t: 0.70 for t in (40, 41, 42, 43)}
    near = {**peak, **{t: 0.70 for t in (48, 49, 50, 51)}}                  # four quarters (1 h) of dip between the two peaks
    far = {**peak, **{t: 0.70 for t in (52, 53, 54, 55)}}                   # five quarters of dip
    starts, imp, exp = flat_day(0.30, 0.28, imp={8: 0.20}, exp=near)
    assert len(detect(starts, imp, exp, CFG)) == 1
    starts, imp, exp = flat_day(0.30, 0.28, imp={8: 0.20}, exp=far)
    assert len(detect(starts, imp, exp, CFG)) == 2


def test_without_stock_the_morning_peak_is_not_sold_and_the_evening_is_fed_by_the_midday_charge():
    """15 Oct from 30%: nothing above the floor at 06:30 and only a replacement would pay, so 'no_stock'; the evening sells what 12:45-15:15 charged."""
    analysis, result = run(15, 0.30)
    morning, evening = analysis.reports
    assert morning.status == NO_STOCK and morning.sold_kwh == 0 and morning.window.viable == "replace"
    assert evening.status == PLANNED and (hhmm(evening.sold_from), hhmm(evening.sold_to)) == ("17:15", "19:30")
    assert [(hhmm(c.start), hhmm(c.end)) for c in evening.charges] == [("12:45", "15:15")]
    assert sum(c.kwh for c in evening.charges) == pytest.approx(evening.sold_kwh, abs=0.05) and evening.from_stock_kwh == 0
    assert analysis.outside_kwh == 0 and set(analysis.serves) == {s for s in (DAY + i * QUARTER for i in range(96)) if "12:45" <= hhmm(s) < "15:15"}
    assert all(windows == (evening.window.start,) for windows in analysis.serves.values())


def test_with_stock_the_same_peak_is_sold_from_the_battery_and_nothing_is_charged_for_it():
    """15 Oct from 83%: the morning window is sold from the 12 kWh above the floor; the midday charge is for the evening only."""
    analysis, _ = run(15, 0.83)
    morning, evening = analysis.reports
    assert morning.status == PLANNED and morning.from_stock_kwh == pytest.approx(12.0, abs=0.05) and morning.charges == ()
    assert (hhmm(morning.sold_from), hhmm(morning.sold_to)) == ("07:45", "09:30") and evening.status == PLANNED


@pytest.mark.parametrize("day,soc", [(14, 0.30), (14, 0.83), (15, 0.30), (15, 0.83)])
def test_every_sold_kwh_is_accounted_for_by_stock_or_by_a_charge(day, soc):
    """What a window sells equals what it took from the battery's stock plus what was bought for it (oldest energy first)."""
    analysis, _ = run(day, soc)
    for report in analysis.reports:
        assert report.sold_kwh == pytest.approx(report.from_stock_kwh + sum(c.kwh for c in report.charges), abs=0.06), report.window.start
    assert analysis.outside_kwh == 0


def test_a_window_the_plan_leaves_for_a_better_one_is_kept_for_later():
    """Two peaks, stock for one: the plan sells the higher one, the lower one is 'kept_for_later', not a miss."""
    starts, imp, exp = flat_day(0.40, 0.28, imp={t: 0.20 for t in range(88, 96)}, exp={**{t: 0.55 for t in range(32, 36)}, **{t: 0.80 for t in range(72, 76)}})
    slots = [Slot(i, e, 0.0, 0.0) for i, e in zip(imp, exp)]
    result = plan(slots, 0.45 * CFG.capacity_kwh, CFG)
    early, late = analyse(starts, slots, result, 0.45 * CFG.capacity_kwh, CFG).reports
    assert (early.status, late.status) == (KEPT_FOR_LATER, PLANNED) and early.sold_kwh == 0 and late.sold_kwh > 3


def test_a_sale_outside_every_window_is_reported_in_kwh():
    """Flat prices have no window; a planned discharge there is counted as outside, so the monitor can flag it."""
    starts, imp, exp = flat_day(0.30, 0.30)
    slots = [Slot(i, e, 0.0, 0.0) for i, e in zip(imp, exp)]
    manual = Plan([PlanSlot(0, "idle", 0.0, 12.0, 0.0, 0.0), PlanSlot(1, "discharge", -2.0, 10.0, -2.0, 0.0)] + [PlanSlot(t, "idle", 0.0, 10.0, 0.0, 0.0) for t in range(2, 96)])
    analysis = analyse(starts, slots, manual, 12.0, CFG)
    assert analysis.reports == () and analysis.outside_kwh == 2.0


@pytest.mark.parametrize("day", [f"2026-10-{d:02d}" for d in range(4, 12)])
@pytest.mark.parametrize("soc", [0.30, 0.83])
def test_over_the_48_hours_the_planner_runs_on_it_never_sells_outside_a_window(day, soc):
    """The check the monitor relies on: on the recorded days every planned sale lies inside a detected window."""
    prices = recorded_day(day, days=2)
    slots = [Slot(i, e, 0.1, 0.0) for i, e in zip(prices.import_eur_kwh, prices.export_eur_kwh)]
    result = plan(slots, soc * CFG.capacity_kwh, CFG)
    assert analyse(list(prices.starts), slots, result, soc * CFG.capacity_kwh, CFG).outside_kwh == 0


def test_the_end_of_a_one_day_horizon_sells_stock_outside_any_window():
    """Known model edge: stock left at the end of the horizon is valued at the cheapest import price, so a short horizon dumps it.
    HEMS plans 48 hours ahead, so this shows up at most in the last quarters; the monitor reports it as outside_kwh."""
    prices = recorded_day("2026-10-09")
    slots = [Slot(i, e, 0.1, 0.0) for i, e in zip(prices.import_eur_kwh, prices.export_eur_kwh)]
    result = plan(slots, 0.83 * CFG.capacity_kwh, CFG)
    assert analyse(list(prices.starts), slots, result, 0.83 * CFG.capacity_kwh, CFG).outside_kwh > 4


def test_a_window_record_is_plain_json_with_times_prices_thresholds_and_the_charges_that_feed_it():
    """What the decision trace and the sensor carry."""
    analysis, _ = run(15, 0.30)
    text = json.dumps([record(r) for r in analysis.reports])
    evening = json.loads(text)[1]
    assert evening["status"] == "planned" and evening["viable"] == "fresh" and evening["charges"][0]["from"] == "2026-10-15T10:45:00+00:00"
    assert {"from", "to", "peak", "need_fresh", "room_fresh", "need_replace", "room_replace", "sold_kwh", "sold_from", "from_stock_kwh", "soc_before_kwh"} <= set(evening)


def manual_plan(moves: dict[int, tuple[str, float]], soc: float = 15.0) -> Plan:
    """A hand-made plan over a day: `moves` maps a quarter to (action, AC kWh with + charge / - discharge); everything else idles."""
    slots = []
    for t in range(96):
        action, kwh = moves.get(t, ("idle", 0.0))
        slots.append(PlanSlot(t, action, kwh, soc, kwh if action == "charge" else (kwh if action == "discharge" else 0.0), 0.0))
    return Plan(slots)


def test_energy_is_sold_oldest_first_so_a_night_charge_is_not_credited_with_what_stock_could_cover():
    """Stock 7.5 kWh above the floor, 4 kWh charged at 01:15, 3 kWh sold at 02:00 and 4 kWh at 15:00: the first sale is stock, the second takes the rest of it."""
    starts, imp, exp = flat_day(0.40, 0.28, imp={5: 0.15}, exp={8: 0.65, 60: 0.65})
    slots = [Slot(i, e, 0.0, 0.0) for i, e in zip(imp, exp)]
    result = manual_plan({5: ("charge", 4.0), 8: ("discharge", -3.0), 60: ("discharge", -4.0)})
    early, late = analyse(starts, slots, result, 15.0, CFG).reports
    assert early.from_stock_kwh == pytest.approx(3.0, abs=0.01) and early.charges == ()
    assert late.from_stock_kwh == pytest.approx(3.79, abs=0.02) and sum(c.kwh for c in late.charges) == pytest.approx(0.21, abs=0.02)
    assert [(hhmm(c.start), c.avg_import) for c in late.charges] == [("01:15", 0.15)]


def test_a_window_sold_only_below_its_best_quarter_is_partial():
    """The plan sells at 0.50 while 0.60 is right next to it: not 'planned' (the best quarter is not sold), and it says so."""
    starts, imp, exp = flat_day(0.40, 0.28, imp={5: 0.15}, exp={8: 0.60, 9: 0.50})
    slots = [Slot(i, e, 0.0, 0.0) for i, e in zip(imp, exp)]
    best = analyse(starts, slots, manual_plan({8: ("discharge", -2.0)}), 15.0, CFG).reports[0]
    lesser = analyse(starts, slots, manual_plan({9: ("discharge", -2.0)}), 15.0, CFG).reports[0]
    assert best.status == PLANNED and lesser.status == "partial" and lesser.sold_kwh == 2.0
