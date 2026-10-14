from datetime import datetime, timedelta, timezone

from test_rolling import recorded_day

from hems.battery import BatteryConfig
from hems.forecast import LOCAL_TZ
from hems.outlook import first_window, forecast_series, hour_mean, hour_total, price_curve, window_total
from hems.rolling import HorizonInputs, plan_next

START = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)          # 10:00 local
QUARTER = timedelta(minutes=15)


def quarters(*values: float, start: datetime = START) -> dict[datetime, float]:
    """A series with one value per quarter from `start`."""
    return {start + i * QUARTER: v for i, v in enumerate(values)}


def test_the_coming_hour_is_four_quarters_and_never_a_partial_hour():
    """Energy adds up, irradiance averages; with a quarter missing the answer is unknown, not a figure that reads too low."""
    series = quarters(0.1, 0.2, 0.3, 0.4, 0.5)
    assert hour_total(series, START) == 1.0 and hour_total(series, START + QUARTER) == 1.4
    assert hour_mean(quarters(100, 200, 300, 400), START) == 250.0
    assert hour_total(series, START + 2 * QUARTER) is None and hour_mean(series, START + 2 * QUARTER) is None
    assert hour_total({}, START) is None


def test_the_energy_in_a_window_counts_the_quarters_that_start_inside_it():
    """[begin, end): the quarter that starts at `end` belongs to the next window; unknown quarters count as nothing."""
    series = quarters(1.0, 2.0, 3.0, 4.0)
    assert window_total(series, START + QUARTER, START + 3 * QUARTER) == 5.0
    assert window_total(series, START, START) == 0.0
    assert window_total(series, START + 3 * QUARTER, START + 8 * QUARTER) == 4.0


def test_a_forecast_series_is_in_local_time_skips_what_is_unknown_and_is_cut_at_the_limit():
    """What a dashboard chart reads: local ISO times, one value per known quarter."""
    series = {**quarters(0.1234, 0.2), START + 3 * QUARTER: 0.4}
    points = forecast_series(series, START, LOCAL_TZ, "kwh")
    assert points == [{"start": "2026-10-14T10:00:00+02:00", "kwh": 0.123}, {"start": "2026-10-14T10:15:00+02:00", "kwh": 0.2},
                      {"start": "2026-10-14T10:45:00+02:00", "kwh": 0.4}]
    assert len(forecast_series(quarters(*range(10)), START, LOCAL_TZ, "w", limit=4)) == 4


def test_the_price_curve_starts_now_and_carries_import_and_export_separately():
    """The recorded day of 6 Oct: the curve from 12:00 local on, the same numbers the planner reads."""
    prices = recorded_day("2026-10-06")
    now = datetime(2026, 10, 6, 12, 0, tzinfo=LOCAL_TZ)
    imp, exp = price_curve(prices, "import", now, LOCAL_TZ), price_curve(prices, "export", now, LOCAL_TZ)
    assert imp[0]["start"] == "2026-10-06T12:00:00+02:00" and len(imp) == len(exp) == sum(1 for t in prices.starts if t >= now)
    first = prices.starts.index(now)
    assert imp[0]["price"] == round(prices.import_eur_kwh[first], 4) and exp[0]["price"] == round(prices.export_eur_kwh[first], 4)
    assert all(p["price"] is not None for p in imp)


def test_the_first_window_of_a_real_plan_has_times_and_the_energy_the_plan_expects_in_it():
    """A plan from 06:07 with a half-empty battery: the first charge comes before the first discharge, PV in the window is what the slots say."""
    now = datetime(2026, 10, 6, 6, 7, tzinfo=LOCAL_TZ)
    decision = plan_next(HorizonInputs(now, 8.0, recorded_day("2026-10-06"), {}, {}), BatteryConfig())
    charge, discharge = first_window(decision.trace["segments"], "charge"), first_window(decision.trace["segments"], "discharge")
    assert charge is not None and discharge is not None and charge["begin"] >= decision.slot_start and charge["end"] > charge["begin"]
    assert isinstance(charge["begin"], datetime) and charge["begin"].tzinfo is not None and charge["kwh"] > 0
    pv = {decision.slot_start + i * QUARTER: s.pv_kwh for i, s in enumerate(decision.slots)}
    in_window = sum(s.pv_kwh for i, s in enumerate(decision.slots) if charge["begin"] <= decision.slot_start + i * QUARTER < charge["end"])
    assert window_total(pv, charge["begin"], charge["end"], digits=6) == round(in_window, 6)


def test_a_plan_without_the_action_has_no_window():
    """Nothing planned: None, so a sensor can say unknown instead of inventing a time."""
    assert first_window([{"action": "idle", "from": START.isoformat(), "to": (START + QUARTER).isoformat()}], "charge") is None
    assert first_window([], "discharge") is None
