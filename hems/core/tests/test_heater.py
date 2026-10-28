from datetime import datetime, timedelta, timezone

import pytest

from hems.dryrun import EngineInputs, EngineSettings, _load_forecast
from hems.forecast import LOCAL_TZ
from hems.heater import HeatingRun, WaterHeaterConfig, legionella_due, legionella_overdue, plan_runs, record_legionella, run_kwh_per_quarter, without_daily_peak
from hems.prices import PriceSeries

NOW = datetime(2026, 10, 15, 9, 7, tzinfo=LOCAL_TZ)
START = datetime(2026, 10, 15, 7, 0, tzinfo=timezone.utc)            # 09:00 local: the quarter of NOW


def days_of_history(heater_hour: int, days: int = 7, base_w: float = 600.0, heater_w: float = 2000.0) -> list[tuple[datetime, float]]:
    """`days` local days of hourly mean load: a flat base and the heater adding `heater_w` in `heater_hour` of every day."""
    first = datetime(2026, 10, 8, tzinfo=LOCAL_TZ)
    return [(first + timedelta(days=d, hours=h), base_w + (heater_w if h == heater_hour else 0.0)) for d in range(days) for h in range(24)]


ON = WaterHeaterConfig(enabled=True)


def day_prices(*days: tuple[int, int, int], cheap: dict[int, float] | None = None, base: float = 0.30, first_hour: int = 0) -> PriceSeries:
    """Quarter prices for whole local days (year 2026, month, day): `base` everywhere, `cheap` {local hour: price} for chosen hours; from local hour `first_hour` of the first day."""
    starts = []
    for year_month_day in days:
        day = datetime(*year_month_day, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
        end = datetime(year_month_day[0], year_month_day[1], year_month_day[2], tzinfo=LOCAL_TZ) + timedelta(days=1)
        starts += [day + timedelta(minutes=15 * k) for k in range(int((end.astimezone(timezone.utc) - day) / timedelta(minutes=15)))]
    starts = [t for t in starts if t >= datetime(*days[0], first_hour, tzinfo=LOCAL_TZ).astimezone(timezone.utc)]
    imp = [(cheap or {}).get(t.astimezone(LOCAL_TZ).hour, base) for t in starts]
    return PriceSeries(tuple(starts), tuple(imp), tuple(imp))


def test_the_module_off_plans_nothing():
    """Switched off (the default) the module leaves the forecast alone."""
    assert plan_runs(day_prices((2026, 10, 15)), NOW, WaterHeaterConfig(), LOCAL_TZ) == []


def test_the_day_run_is_the_cheapest_hour_of_06_to_24_even_when_the_night_is_cheaper():
    """Like the add-on: 04:00 is the cheapest hour of Thursday 15 Oct but the heating runs in the day part, 13:00-14:00 (no night run: 0 kWh by default).
    The run carries the normal energy and the hour's mean price. Times are UTC."""
    runs = plan_runs(day_prices((2026, 10, 15), cheap={13: 0.05, 4: 0.01}), NOW, ON, LOCAL_TZ)
    assert [(r.start, r.end, r.energy_kwh, r.kind) for r in runs] == [(datetime(2026, 10, 15, 11, tzinfo=timezone.utc), datetime(2026, 10, 15, 12, tzinfo=timezone.utc), 1.9, "heating")]
    assert runs[0].avg_price == pytest.approx(0.05)


def test_equal_prices_take_the_earliest_window_like_the_add_on():
    """A flat day: the day run starts at the first allowed hour, 06:00 (the add-on takes the first of equal candidates)."""
    run, = plan_runs(day_prices((2026, 10, 15)), datetime(2026, 10, 15, 0, 5, tzinfo=LOCAL_TZ), ON, LOCAL_TZ)
    assert run.start.astimezone(LOCAL_TZ).hour == 6


def test_a_night_run_is_planned_in_the_cheapest_night_hour_when_it_has_energy():
    """With night energy set, the night program gets its own run in 00-06 (cheapest 04:00) next to the day run; before it has ended both are listed in time order."""
    config = WaterHeaterConfig(enabled=True, night_energy_kwh=0.5)
    night, day = plan_runs(day_prices((2026, 10, 15), cheap={13: 0.05, 4: 0.01}), datetime(2026, 10, 15, 0, 5, tzinfo=LOCAL_TZ), config, LOCAL_TZ)
    assert (night.kind, night.start.astimezone(LOCAL_TZ).hour, night.energy_kwh) == ("night", 4, 0.5)
    assert (day.kind, day.start.astimezone(LOCAL_TZ).hour, day.energy_kwh) == ("heating", 13, 1.9)


def test_every_day_with_a_complete_price_curve_gets_a_run_and_an_incomplete_day_none():
    """Today and tomorrow are planned; a third day with only its first hours known is left out, because the cheapest of a few hours is not the heater's choice."""
    prices = day_prices((2026, 10, 15), (2026, 10, 16), cheap={13: 0.05})
    known = PriceSeries(prices.starts + tuple(datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * k) for k in range(12)),
                        prices.import_eur_kwh + (0.01,) * 12, prices.export_eur_kwh + (0.01,) * 12)
    runs = plan_runs(known, NOW, ON, LOCAL_TZ)
    assert [r.start.astimezone(LOCAL_TZ).strftime("%d %H:%M") for r in runs] == ["15 13:00", "16 13:00"]


def test_a_day_that_is_already_part_over_is_not_planned_on_what_is_left():
    """Prices only known from 15:00 on: no day run for today (its cheapest hour may have been before 15:00), a complete tomorrow gets one."""
    today_late = day_prices((2026, 10, 15), (2026, 10, 16), cheap={20: 0.01}, first_hour=15)
    runs = plan_runs(today_late, NOW, ON, LOCAL_TZ)
    assert [(r.start.astimezone(LOCAL_TZ).day, r.start.astimezone(LOCAL_TZ).hour) for r in runs] == [(16, 20)]


def test_a_run_that_has_ended_is_dropped_and_one_that_is_going_on_stays():
    """At 13:30 the 13:00-14:00 run is going on and stays; at 14:00 it is over."""
    prices = day_prices((2026, 10, 15), cheap={13: 0.05})
    assert len(plan_runs(prices, datetime(2026, 10, 15, 13, 30, tzinfo=LOCAL_TZ), ON, LOCAL_TZ)) == 1
    assert plan_runs(prices, datetime(2026, 10, 15, 14, 0, tzinfo=LOCAL_TZ), ON, LOCAL_TZ) == []


def test_the_legionella_day_has_the_longer_and_larger_run():
    """Saturday 17 Oct: three consecutive hours around the cheap midday, 2.6 kWh, kind 'legionella'; the weekday is a setting."""
    prices = day_prices((2026, 10, 17), cheap={12: 0.05, 13: 0.04, 14: 0.05})
    run, = plan_runs(prices, NOW, ON, LOCAL_TZ)
    assert (run.start.astimezone(LOCAL_TZ).hour, run.end - run.start, run.energy_kwh, run.kind) == (12, timedelta(hours=3), 2.6, "legionella")
    sunday, = plan_runs(prices, NOW, WaterHeaterConfig(enabled=True, legionella_weekday=6), LOCAL_TZ)
    assert (sunday.kind, sunday.end - sunday.start) == ("heating", timedelta(hours=1))


def test_a_run_of_no_energy_is_not_planned():
    """Zero kWh means the setting is off for that kind of day."""
    assert plan_runs(day_prices((2026, 10, 15)), NOW, WaterHeaterConfig(enabled=True, energy_kwh=0.0), LOCAL_TZ) == []


def test_the_day_the_clock_goes_back_has_25_hours_and_the_parts_have_the_hours_they_really_have():
    """25 Oct 2026 (clock change): the night part is 7 real hours (cheapest 03:00 CET = 02:00 UTC, after the repeated 02:00 hour) and the day part 18."""
    prices = day_prices((2026, 10, 25), cheap={3: 0.01, 9: 0.02})
    night, day = plan_runs(prices, datetime(2026, 10, 24, 12, tzinfo=LOCAL_TZ), WaterHeaterConfig(enabled=True, night_energy_kwh=0.5), LOCAL_TZ)
    assert night.start == datetime(2026, 10, 25, 2, tzinfo=timezone.utc) and night.end - night.start == timedelta(hours=1)
    assert day.start == datetime(2026, 10, 25, 8, tzinfo=timezone.utc)


def test_a_runs_energy_is_spread_evenly_over_its_quarters_in_utc():
    """1.9 kWh over 13:00-14:00 local is 0.475 kWh in each of the four quarters, keyed by UTC quarter start."""
    run = [HeatingRun(datetime(2026, 10, 15, 13, tzinfo=LOCAL_TZ), datetime(2026, 10, 15, 14, tzinfo=LOCAL_TZ), 1.9)]
    per_quarter = run_kwh_per_quarter(run)
    assert sorted(per_quarter) == [datetime(2026, 10, 15, 11, 15 * k, tzinfo=timezone.utc) for k in range(4)]
    assert all(v == pytest.approx(0.475) for v in per_quarter.values()) and sum(per_quarter.values()) == pytest.approx(1.9)


def test_each_days_heater_is_taken_out_of_the_history_up_to_the_configured_energy():
    """The peak hour loses what it has above the day's median (2.0 kWh), at most the cap; other hours stay."""
    history = days_of_history(12)
    cleaned = without_daily_peak(history, 1.9, LOCAL_TZ)
    peaks = [w for (_, w), (_, old) in zip(cleaned, history) if w != old]
    assert len(peaks) == 7 and all(w == pytest.approx(2600 - 1900) for w in peaks)
    assert without_daily_peak(history, 5.0, LOCAL_TZ)[12][1] == pytest.approx(600.0), "a bigger cap removes the whole excess, never more"
    assert without_daily_peak(history, 0.0, LOCAL_TZ) == history


def test_a_short_day_is_left_alone():
    """With only a few hours of a day there is no telling which is the peak: nothing is removed."""
    history = days_of_history(12, days=1)[:12]
    assert without_daily_peak(history, 1.9, LOCAL_TZ) == history


def test_the_forecast_without_the_heater_model_is_what_it_was():
    """No cap, no runs: the median profile, labelled 'history'."""
    inputs = EngineInputs(NOW, None, [], days_of_history(12), None)
    load, source = _load_forecast(inputs, EngineSettings(), START, 8)
    assert source == "history" and load[START] == pytest.approx(0.15)


def test_the_planned_run_replaces_the_smeared_peak_in_the_forecast():
    """History has the heater at 12:00 every day; the module plans it at 13:00. Without the model 12:00 stays high and 13:00 is flat; with it the
    peak moves to 13:00 and the day's total grows by nothing (one heater run in, one out)."""
    history = days_of_history(12)
    run = [HeatingRun(datetime(2026, 10, 15, 13, tzinfo=LOCAL_TZ), datetime(2026, 10, 15, 14, tzinfo=LOCAL_TZ), 1.9)]
    start = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)                # 12:00 local
    plain, _ = _load_forecast(EngineInputs(NOW, None, [], history, None), EngineSettings(), start, 8)
    modelled, source = _load_forecast(EngineInputs(NOW, None, [], history, None), EngineSettings(water_heater=ON), start, 8, run)
    hour = lambda load, first: sum(load[start + timedelta(minutes=15 * (first + k))] for k in range(4))
    assert source == "history+heater"
    assert hour(plain, 0) == pytest.approx(2.6) and hour(plain, 4) == pytest.approx(0.6)                       # the old forecast: peak at 12, flat at 13
    assert hour(modelled, 0) == pytest.approx(0.7) and hour(modelled, 4) == pytest.approx(0.6 + 1.9)           # the modelled one: 12 flat, peak at 13


def test_legionella_is_planned_only_when_due_on_calendar_days():
    """The add-on's rule (1.3.1): due seven calendar days after the *day* of the last run. The run of Saturday 17 Oct was stamped 18:30, so
    on Saturday 24 Oct the 14:00 window is due (6 days 19.5 h elapsed, but the 7th calendar day); a hot tank on Sunday 25 Oct (a negative
    price, by hand) makes Saturday 31 Oct not due, so that day gets an ordinary heating run. No run known: due."""
    sat_24 = datetime(2026, 10, 24, 0, 0, tzinfo=LOCAL_TZ)
    prices = day_prices((2026, 10, 24), cheap={13: 0.04, 14: 0.03, 15: 0.04})
    stamped = datetime(2026, 10, 17, 18, 30, tzinfo=LOCAL_TZ)
    run, = plan_runs(prices, sat_24, ON, LOCAL_TZ, last_legionella=stamped)
    assert run.kind == "legionella" and run.start.astimezone(LOCAL_TZ).hour == 13
    sat_31 = datetime(2026, 10, 31, 0, 0, tzinfo=LOCAL_TZ)
    hot_sunday = datetime(2026, 10, 25, 9, 0, tzinfo=LOCAL_TZ)
    later, = plan_runs(day_prices((2026, 10, 31)), sat_31, ON, LOCAL_TZ, last_legionella=hot_sunday)
    assert later.kind == "heating"
    assert legionella_due(None, sat_31.date(), LOCAL_TZ) and plan_runs(day_prices((2026, 10, 31)), sat_31, ON, LOCAL_TZ)[0].kind == "legionella"


def test_the_overdue_alert_waits_one_day_past_the_due_day():
    """Last run Saturday 17 Oct: due Saturday 24th; not overdue on the 24th or Sunday the 25th, overdue on Monday the 26th."""
    last = datetime(2026, 10, 17, 18, 30, tzinfo=LOCAL_TZ)
    assert [legionella_overdue(last, datetime(2026, 10, d).date(), LOCAL_TZ) for d in (24, 25, 26)] == [False, False, True]
    assert not legionella_overdue(None, datetime(2026, 10, 26).date(), LOCAL_TZ)


def test_hems_records_the_day_the_tank_first_reaches_60_degrees():
    """HEMS keeps its own record (the add-on goes): the first moment of a local day at 60 °C or more; staying hot does not move it, a
    cooler tank does not either, the next day's hot tank does."""
    sat = datetime(2026, 10, 24, 13, 40, tzinfo=LOCAL_TZ)
    assert record_legionella(None, 58.0, sat, LOCAL_TZ) is None and record_legionella(None, None, sat, LOCAL_TZ) is None
    first = record_legionella(None, 60.5, sat, LOCAL_TZ)
    assert first == sat
    assert record_legionella(first, 62.0, sat.replace(hour=18, minute=30), LOCAL_TZ) == sat, "not refreshed while hot (the add-on's mistake)"
    sunday = datetime(2026, 10, 25, 9, 0, tzinfo=LOCAL_TZ)
    assert record_legionella(first, 45.0, sunday, LOCAL_TZ) == sat and record_legionella(first, 70.0, sunday, LOCAL_TZ) == sunday
