"""Lessons from the battery-manager incident of 2026-10-14, as HEMS checks.

The day had two price peaks (morning 07:30-09:30 up to 0.62, evening 17:45-20:30 up to 0.53) with the cheapest hours
in between. battery-manager planned only the evening because a heuristic removed every quarter before the midday charge
window. HEMS has no such gate (one economic objective over the whole horizon); these tests keep it that way, and keep the
explanation of each decision consistent with the decision itself.
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from test_rolling import recorded_day

from hems.battery import REASON_DIGITS, BatteryConfig, Slot, plan
from hems.contracts import BatteryCommand
from hems.forecast import LOCAL_TZ
from hems.prices import PriceSeries
from hems.rolling import HorizonInputs, plan_next

FIXTURES = Path(__file__).parent / "fixtures"
CFG = BatteryConfig()
EFF = CFG.round_trip_eff ** 0.5
MARGINAL_SLACK = 0.005         # EUR per kWh: the SoC grid makes 'keep' a finite difference, so smaller gaps are not a modelling question


def shown(value: float) -> float:
    """A price as the reason text prints it."""
    return round(value, REASON_DIGITS)


def real_day() -> PriceSeries:
    """The consumer import and export prices of 2026-10-14 as the energy-prices sensors published them."""
    with (FIXTURES / "real_prices_2026_10_14.csv").open(newline="") as f:
        rows = [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"]), float(r["export_price_eur_kwh"])) for r in csv.DictReader(f)]
    return PriceSeries(tuple(t for t, _, _ in rows), tuple(i for _, i, _ in rows), tuple(e for _, _, e in rows))


def local_hour(series: PriceSeries, index: int) -> float:
    """Local time of day of a quarter, in hours."""
    t = series.starts[index].astimezone(LOCAL_TZ)
    return t.hour + t.minute / 60


def test_a_day_with_two_peaks_sells_both_and_refills_in_between():
    """Night charge, morning sale, midday refill from the actual post-sale SoC, evening sale: the whole cycle of 14 Oct."""
    prices = real_day()
    p = plan([Slot(i, e, 0.12, 0.0) for i, e in zip(prices.import_eur_kwh, prices.export_eur_kwh)], 0.45 * 25, CFG)
    sells = [k for k, s in enumerate(p.slots) if s.action == "discharge"]
    morning = [k for k in sells if 6 <= local_hour(prices, k) < 11]
    evening = [k for k in sells if 16 <= local_hour(prices, k) < 22]
    assert len(morning) >= 6 and len(evening) >= 8, "both peaks are sold"
    top = max(range(96), key=lambda k: prices.export_eur_kwh[k])
    assert top in sells and 8 <= local_hour(prices, top) < 10, "the day's highest price (09:00) is sold"
    night_charge = [k for k, s in enumerate(p.slots) if s.action == "charge" and local_hour(prices, k) < 7.5]
    midday_charge = [k for k, s in enumerate(p.slots) if s.action == "charge" and 11 <= local_hour(prices, k) < 16]
    assert night_charge and midday_charge, "the morning sale is charged for beforehand, the evening sale after the midday dip"
    assert p.slots[midday_charge[-1]].soc_kwh >= 0.99 * CFG.capacity_kwh, "the midday charge refills to full before the evening sale"
    assert min(p.slots[k].soc_kwh for k in sells) >= CFG.reserve_soc * CFG.capacity_kwh - 1e-9
    assert p.saving > 5


def test_at_four_in_the_morning_the_battery_is_charged_for_the_peak_not_left_to_cover_the_house():
    """The first command at 04:00 (SoC 58 %, price 0.33, sale at 0.5-0.6 at 07:30) is a charge, as in the live dry-run."""
    prices = real_day()
    now = datetime(2026, 10, 14, 4, 0, tzinfo=LOCAL_TZ)
    decision = plan_next(HorizonInputs(now, 0.58 * 25, prices, {s: 0.12 for s in prices.starts}, {}), CFG)
    assert isinstance(decision.command, BatteryCommand) and decision.command.power_w > 3000
    assert decision.plan.slots[0].reason_code == "buy"


def test_a_discharge_above_the_house_load_is_priced_as_export_in_its_explanation():
    """08:15 of 14 Oct: house load 0.133 kWh, PV 0.049, import 0.538, export 0.579. The sold kWh lands on the export price."""
    cheap, dear = Slot(0.20, 0.20, 0.1, 0.0), Slot(0.538, 0.579, 0.133, 0.049)
    p = plan([cheap] * 8 + [dear] * 4 + [cheap] * 4, 0.9 * 25, CFG)
    sold = [s for k, s in enumerate(p.slots) if s.action == "discharge" and 8 <= k < 12]
    assert sold, "the expensive quarters are sold"
    for s in sold:
        assert s.sell_value == pytest.approx(EFF * (0.579 - CFG.min_profit_margin), abs=1e-9)    # not 0.538 (the import price)
        assert s.sell_value + MARGINAL_SLACK >= s.stored_value and s.reason.startswith("sell ")


@pytest.mark.parametrize("day", ["2026-10-04", "2026-10-06", "2026-10-09", "2026-10-12"])
@pytest.mark.parametrize("load_kwh", [0.02, 0.25])
def test_an_explanation_never_prints_a_comparison_that_is_false(day, load_kwh):
    """'sell x > keep y' and 'buy x < keep y' only appear when the printed numbers say so; otherwise the text says plan-level."""
    prices = recorded_day(day)
    for soc in (0.35, 0.9):
        p = plan([Slot(i, e, load_kwh, 0.0) for i, e in zip(prices.import_eur_kwh, prices.export_eur_kwh)], soc * 25, CFG)
        for s in p.slots:
            if s.action == "discharge" and s.stored_value is not None:
                assert s.reason.startswith("sell ") == (shown(s.sell_value) >= shown(s.stored_value)), s.reason
                assert s.reason.startswith("sell ") or s.reason.startswith("plan-level sale")
            if s.action == "charge" and s.stored_value is not None:
                assert s.reason.startswith("buy ") == (shown(s.buy_cost) <= shown(s.stored_value)), s.reason
                assert s.reason.startswith("buy ") or s.reason.startswith("plan-level charge")


def test_selling_never_needs_the_marginal_comparison_to_be_false_on_recorded_days():
    """With the sell price taken where the kWh lands, every sale on nine recorded days passes the marginal test."""
    cases = fails = 0
    for day in [f"2026-10-{d:02d}" for d in range(4, 13)]:
        prices = recorded_day(day)
        for load_kwh in (0.02, 0.1, 0.25):
            p = plan([Slot(i, e, load_kwh, 0.0) for i, e in zip(prices.import_eur_kwh, prices.export_eur_kwh)], 0.6 * 25, CFG)
            for s in p.slots:
                if s.action == "discharge" and s.stored_value is not None:
                    cases += 1
                    fails += s.sell_value + MARGINAL_SLACK < s.stored_value
    assert cases > 200 and fails == 0


def test_the_reason_text_says_plan_level_when_the_marginal_comparison_contradicts_the_choice():
    """Direct check of both branches: a sale below keep and a charge above keep are labelled, never printed as sell > keep / buy < keep."""
    from hems.battery import _reason

    slot = Slot(0.40, 0.45, 0.1, 0.0)
    held = _reason("discharge", slot, -1.0, 0.60, EFF, CFG, at_floor=False, at_full=False)
    assert held.text.startswith("plan-level sale") and held.code == "sell"
    plain = _reason("discharge", slot, -1.0, 0.20, EFF, CFG, at_floor=False, at_full=False)
    assert plain.text.startswith("sell ") and "> keep" in plain.text
    dear = _reason("charge", slot, 1.0, 0.10, EFF, CFG, at_floor=False, at_full=False)
    assert dear.text.startswith("plan-level charge") and dear.code == "buy"
    cheap = _reason("charge", slot, 1.0, 0.90, EFF, CFG, at_floor=False, at_full=False)
    assert cheap.text.startswith("buy ") and "< keep" in cheap.text


def test_a_comparison_that_prints_equal_numbers_says_so_and_one_that_prints_reversed_numbers_is_plan_level():
    """14 Oct 01:00 printed 'buy 0.313 < keep 0.313', 02:15 'buy 0.330 < keep 0.328': a reader checks the text against its own numbers."""
    from hems.battery import _reason

    slot = Slot(0.30, 0.20, 0.1, 0.0)
    buy_price = 0.30 / EFF
    equal = _reason("charge", slot, 1.0, buy_price + 0.0001, EFF, CFG, at_floor=False, at_full=False)
    assert equal.text == f"buy {shown(buy_price):.3f} <= keep {shown(buy_price):.3f}"
    reversed_ = _reason("charge", slot, 1.0, buy_price - 0.002, EFF, CFG, at_floor=False, at_full=False)
    assert reversed_.text.startswith("plan-level charge: buy ") and reversed_.code == "buy"
    sell_price = EFF * (0.45 - CFG.min_profit_margin)
    equal_sale = _reason("discharge", Slot(0.40, 0.45, 0.1, 0.0), -1.0, sell_price - 0.0001, EFF, CFG, at_floor=False, at_full=False)
    assert equal_sale.text == f"sell {shown(sell_price):.3f} >= keep {shown(sell_price):.3f}"
    floor = _reason("idle", Slot(0.40, 0.45, 0.0, 0.0), 0.0, sell_price - 0.0001, EFF, CFG, at_floor=True, at_full=False)
    assert floor.code == "floor" and floor.text == f"hold at reserve floor (sell {shown(sell_price):.3f} >= keep {shown(sell_price):.3f})"
