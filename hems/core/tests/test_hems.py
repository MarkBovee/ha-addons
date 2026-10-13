import csv
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from hems.balancer import Load, allocate
from hems.battery import BatteryConfig, Slot, plan
from hems.forecast import LOCAL_TZ, hourly_profile, to_slots_kwh
from hems.prices import PriceModel, curves
from hems.solar import is_daylight, sun_times_utc

FIXTURES = Path(__file__).parent / "fixtures"
UTRECHT = (52.0907, 5.1214)    # default location of the energy-prices add-on


def mk(market, load_w=300, pv_w=None, daylight=None):
    """Slots from a quarter-hour market curve; daylight defaults to all-day so the bonus always applies."""
    m = PriceModel()
    imp, exp = curves(market, m, daylight or [True] * len(market))
    pv_w = pv_w or [0] * len(market)
    return [Slot(i, e, load_w / 1000 * .25, p / 1000 * .25) for i, e, p in zip(imp, exp, pv_w)]


def hourly_to_quarters(hourly):
    """Repeat each hourly value four times to get quarter-hour slots."""
    return [p for p in hourly for _ in range(4)]


def load_quarter_import_prices():
    """(quarter start UTC, consumer import price) from the recorder export of sensor.current_price."""
    with open(FIXTURES / "quarter_import_prices.csv", newline="") as f:
        return [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"])) for r in csv.DictReader(f)]


# ---- prices -------------------------------------------------------------------------------------------------

def test_price_formulas():
    """Import and export formulas match the energy-prices contract, and market_from_import inverts the import price."""
    m = PriceModel()
    assert m.import_price(0.10) == pytest.approx(0.121 + 0.11085 + 0.02)
    assert m.export_price(0.10, daylight=True) == pytest.approx(0.10 * 1.331 + 0.13085)
    assert PriceModel(salderen=False).export_price(0.10, daylight=True) == pytest.approx(0.13)
    assert m.market_from_import(m.import_price(0.10)) == pytest.approx(0.10)


def test_percentage_bonus_needs_daylight_and_positive_price():
    """Only the percentage bonus depends on daylight and sign; the fixed bonus stays, and netting off drops VAT and tax."""
    m = PriceModel()
    assert m.export_price(0.10, daylight=False) == pytest.approx(0.10 * 1.21 + 0.02 + 0.11085)   # fixed bonus stays
    assert m.export_price(-0.05, daylight=True) == pytest.approx(-0.05 * 1.21 + 0.02 + 0.11085)  # 10 % must not deepen a negative price
    assert PriceModel(bonus_only_daylight=False).export_price(0.10, daylight=False) == m.export_price(0.10, daylight=True)
    assert PriceModel(salderen=False).export_price(0.10, daylight=False) == pytest.approx(0.12)


def test_curves_need_one_daylight_flag_per_slot():
    """A daylight list of the wrong length is rejected."""
    with pytest.raises(ValueError):
        curves([0.1, 0.2], PriceModel(), [True])


def test_recorded_price_fixture_is_a_gapless_quarter_grid():
    """The recorder export is 979 contiguous quarters and matches the 12 Oct snapshot price."""
    rows = load_quarter_import_prices()
    assert len(rows) == 979
    assert all(b[0] - a[0] == timedelta(minutes=15) for a, b in zip(rows, rows[1:]))
    by_start = dict(rows)
    assert by_start[datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)] == 0.4792    # matches the 08:14 snapshot


# ---- sun ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("day, rise, sset", [
    (date(2026, 6, 21), (5, 18), (22, 3)),
    (date(2026, 10, 13), (8, 1), (18, 49)),
    (date(2026, 12, 21), (8, 45), (16, 29)),
])
def test_sun_times_utrecht_within_ten_minutes(day, rise, sset):
    """Sunrise and sunset at the solstices and mid-October are within ten minutes of the expected values."""
    got_rise, got_set = (t.astimezone(LOCAL_TZ) for t in sun_times_utc(day, *UTRECHT))
    for got, (h, m) in ((got_rise, rise), (got_set, sset)):
        assert abs((got - got.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds()) < 600


def test_daylight_flag_follows_sunset_in_october():
    """On 13 Oct it is daylight at 12:00 and 18:00 local, not at 07:30 or 19:00."""
    at = lambda h, m: datetime(2026, 10, 13, h, m, tzinfo=LOCAL_TZ)
    assert is_daylight(at(12, 0), *UTRECHT) and is_daylight(at(18, 0), *UTRECHT)
    assert not is_daylight(at(19, 0), *UTRECHT) and not is_daylight(at(7, 30), *UTRECHT)


# ---- battery planner ----------------------------------------------------------------------------------------

def test_clear_spread_charges_cheap_discharges_peak():
    # night 0.02, day 0.10, evening peak 0.30 (market EUR/kWh), 24 h
    """A clear night/evening spread charges at night and discharges only after the charge window, within the peak."""
    mk_h = [0.02] * 6 + [0.10] * 12 + [0.30] * 4 + [0.10] * 2
    slots = mk(hourly_to_quarters(mk_h))
    p = plan(slots, 0.30 * 25, BatteryConfig())
    ch = [s.index for s in p.slots if s.action == "charge"]
    di = [s.index for s in p.slots if s.action == "discharge"]
    assert ch and di
    assert max(ch) < min(di)                  # discharge happens AFTER the charge window
    assert all(18 * 4 <= i < 22 * 4 for i in di)
    assert p.saving > 0


def test_thin_spread_no_cycling():
    """A spread smaller than margin plus losses leaves the battery idle."""
    mk_h = [0.10] * 12 + [0.115] * 12
    p = plan(mk(hourly_to_quarters(mk_h)), 0.30 * 25, BatteryConfig())
    assert all(s.action == "idle" for s in p.slots)


def test_minimum_profit_margin_blocks_marginal_cycles():
    """A positive minimum profit margin removes cycles that only just pay."""
    mk_h = [0.10] * 12 + [0.16] * 12
    cheap = plan(mk(hourly_to_quarters(mk_h)), 0.5 * 25, BatteryConfig(min_profit_margin=0.0))
    dear = plan(mk(hourly_to_quarters(mk_h)), 0.5 * 25, BatteryConfig(min_profit_margin=0.10))
    assert sum(s.action != "idle" for s in cheap.slots) > sum(s.action != "idle" for s in dear.slots)


def test_never_below_reserve_floor():
    """SoC never drops below the reserve floor while discharging."""
    mk_h = [0.30] * 24
    p = plan(mk(hourly_to_quarters(mk_h)), 0.31 * 25, BatteryConfig())
    assert min(s.soc_kwh for s in p.slots) >= 0.30 * 25 - 1e-9


def test_reserve_floor_can_differ_per_slot_but_never_drops_below_hard_minimum():
    """A per-slot reserve lets SoC go lower, but never under the hard minimum."""
    mk_h = [0.40] * 12 + [0.02] * 12      # sell high first; the cheap tail keeps the end-of-horizon value low
    slots = mk(hourly_to_quarters(mk_h))
    shallow = plan(slots, 25.0, BatteryConfig())
    deep = plan([replace(s, reserve_soc=0.0) for s in slots], 25.0, BatteryConfig())   # 0 is clamped to the 5 % hard minimum
    assert min(s.soc_kwh for s in shallow.slots) >= 0.30 * 25 - 1e-9
    assert 0.05 * 25 - 1e-9 <= min(s.soc_kwh for s in deep.slots) < 0.30 * 25 - 1e-9


def test_reserve_below_hard_minimum_is_rejected():
    """A reserve below the hard minimum is a configuration error."""
    with pytest.raises(ValueError):
        BatteryConfig(hard_min_soc=0.05, reserve_soc=0.02)


# ---- load balancer ------------------------------------------------------------------------------------------

def test_balancer_priorities_and_min_power():
    """Loads are served by priority, a load below its minimum is off, and hysteresis keeps a running load alive."""
    out = allocate(9000, [Load("ev", 11000, 2, min_w=4100), Load("battery", 8000, 1)], 15000)
    assert out["battery"] == 6000 and out["ev"] == 0   # battery first, EV below min -> off
    out = allocate(2000, [Load("ev", 11000, 2, min_w=4100), Load("battery", 8000, 1)], 15000)
    assert out["battery"] == 8000 and out["ev"] == 5000
    # hysteresis: running EV survives 4000 W headroom, a stopped one does not
    loads = [Load("ev", 11000, 2, min_w=4100)]
    assert allocate(11000, loads, 15000, previous={"ev": 4100})["ev"] == 4100
    assert allocate(11000, loads, 15000)["ev"] == 0


def test_balancer_deducts_uncontrollable_loads_before_controllable_ones():
    # a heat pump that cannot be throttled runs whatever its priority; the battery gets what remains
    """An uncontrollable load of lower priority still reduces what the battery gets, so the grid limit holds."""
    loads = [Load("battery", 8000, 1), Load("heatpump", 5000, 2, controllable=False)]
    out = allocate(7000, loads, 15000)
    assert out == {"heatpump": 5000, "battery": 3000}
    assert 7000 + sum(out.values()) <= 15000


# ---- forecast -----------------------------------------------------------------------------------------------

def hourly_series(first_utc, last_utc, watts):
    """Hourly (start, W) samples between two UTC moments; watts(local_hour) gives the value."""
    rows, ts = [], first_utc
    while ts <= last_utc:
        rows.append((ts, watts(ts.astimezone(LOCAL_TZ).hour)))
        ts += timedelta(hours=1)
    return rows


def test_profile_is_median_per_local_hour_over_the_day_window():
    """The profile is the median per local hour: one spike and samples older than the window do not count."""
    first = datetime(2026, 10, 1, 0, tzinfo=timezone.utc)
    hist = hourly_series(first, datetime(2026, 10, 13, 23, tzinfo=timezone.utc), lambda h: 300.0)
    hist = [(ts, 9000.0 if ts == datetime(2026, 10, 10, 8, tzinfo=timezone.utc) else w) for ts, w in hist]   # one EV spike
    hist = [(ts, 5000.0 if ts < datetime(2026, 10, 6, tzinfo=timezone.utc) else w) for ts, w in hist]        # older than 7 days
    assert hourly_profile(hist) == [300.0] * 24


def test_profile_window_counts_days_not_rows_when_the_history_has_a_gap():
    # a 168-row window would reach back over the gap and pick up the stale days; 7 calendar days must not
    """A gap in the history must not pull stale days into a 7-day window."""
    stale = hourly_series(datetime(2026, 10, 10, 0, tzinfo=timezone.utc), datetime(2026, 10, 12, 23, tzinfo=timezone.utc), lambda h: 5000.0)
    recent = hourly_series(datetime(2026, 10, 25, 0, tzinfo=timezone.utc), datetime(2026, 10, 26, 23, tzinfo=timezone.utc), lambda h: 300.0)
    assert hourly_profile(stale + recent) == [300.0] * 24


def test_slots_start_on_any_quarter_and_use_the_local_hour():
    """A horizon starting at 19:45 maps its slots to the right local hours."""
    profile = [100.0 * h for h in range(24)]
    start = datetime(2026, 10, 13, 19, 45, tzinfo=LOCAL_TZ)
    assert to_slots_kwh(profile, start, 3) == [pytest.approx(1.9 * .25), pytest.approx(2.0 * .25), pytest.approx(2.0 * .25)]


def test_slots_on_a_25_hour_day_repeat_the_hour_instead_of_drifting():
    """On the 25-hour DST day local hour 02 occurs twice and the day still ends at 23:45."""
    profile = [100.0 * h for h in range(24)]
    out = to_slots_kwh(profile, datetime(2026, 10, 25, 0, 0, tzinfo=LOCAL_TZ), 25 * 4)
    assert len(out) == 100 and out.count(pytest.approx(0.2 * .25)) == 8     # local hour 02 occurs twice
    assert out[-1] == pytest.approx(2.3 * .25)


def test_planned_ac_power_never_exceeds_the_inverter_limit():
    """The limit is AC: charging at 8.8 kW AC (8 kW into the cells) would exceed an 8 kW inverter (regression)."""
    mk_h = [0.02] * 6 + [0.40] * 6 + [0.02] * 6 + [0.40] * 6
    p = plan(mk(hourly_to_quarters(mk_h)), 12.0, BatteryConfig())
    peak_kw = max(abs(s.battery_kwh) for s in p.slots) / 0.25
    assert 7.0 < peak_kw <= 8.0 + 1e-9

