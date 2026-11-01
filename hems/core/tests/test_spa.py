"""The spa module: hold the band, heat in the cheap quarters, pause for the grid, and plan around it in the load forecast."""
from datetime import datetime, timedelta, timezone

from hems.prices import PriceSeries
from hems.spa import SpaConfig, plan_spa, spa_kwh_per_quarter, spa_target

CFG = SpaConfig(enabled=True, control="climate")
T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def series(prices: list[float], export: list[float] | None = None) -> PriceSeries:
    starts = tuple(T0 + k * timedelta(minutes=15) for k in range(len(prices)))
    return PriceSeries(starts, tuple(prices), tuple(export or prices))


def test_the_water_never_leaves_the_band_and_heats_in_the_cheap_hours():
    """Eight hours of 0.40 with a cheap hour (0.20) in the middle, outdoor 5 °C: the water stays in 37-38.5 °C and the heating falls in the
    cheap hour where it can."""
    prices = [0.40] * 12 + [0.20] * 4 + [0.40] * 16
    plan = plan_spa(series(prices), {}, {}, T0, 37.8, SpaConfig(enabled=True, control="climate", default_outdoor_c=5))
    temps = [q.temp_c for q in plan.quarters]
    assert plan.feasible and min(temps) >= 37.0 - 1e-9 and max(temps) <= 38.5 + 1e-9
    cheap = [q.heat for q in plan.quarters[12:16]]
    assert all(cheap), "the cheap hour is used to top up"
    assert sum(q.heat for q in plan.quarters[:12]) <= sum(q.heat for q in plan.quarters[12:16])


def test_below_the_band_heats_at_once_whatever_the_price():
    plan = plan_spa(series([0.60] * 16), {}, {}, T0, 35.0, CFG)
    assert plan.quarters[0].heat and "below the band" in plan.reason


def test_solar_surplus_is_used_at_the_export_price():
    """Import 0.40 all afternoon, export 0.05 with enough surplus in two quarters: the spa heats there."""
    prices = [0.40] * 16
    export = [0.40] * 6 + [0.05] * 2 + [0.40] * 8
    surplus = {T0 + k * timedelta(minutes=15): 1.0 for k in (6, 7)}
    plan = plan_spa(series(prices, export), surplus, {}, T0, 37.5, CFG)
    assert plan.quarters[6].heat and plan.quarters[7].heat and plan.quarters[6].price == 0.05


def test_the_target_is_the_top_of_the_band_to_heat_and_the_bottom_to_pause_or_give_way():
    plan = plan_spa(series([0.20] * 4 + [0.60] * 12), {}, {}, T0, 37.5, CFG)
    at = next(q.start for q in plan.quarters if q.heat)                  # equal prices: it heats as late as it can (less heat lost)
    heat = spa_target(plan, at, CFG)
    assert (heat.target_c, heat.heat) == (38.5, True)
    paused = spa_target(plan, at, CFG, allowed=False)
    assert (paused.target_c, paused.heat) == (37.0, False) and "phase is full" in paused.reason
    assert spa_target(plan, T0 + timedelta(hours=2), CFG).target_c == 37.0


def test_an_unreachable_band_is_reported_and_the_plan_heats_flat_out():
    weak = SpaConfig(enabled=True, control="climate", heat_rate_c_h=0.1, cool_k_h=0.05, default_outdoor_c=-10)
    plan = plan_spa(series([0.30] * 8), {}, {}, T0, 36.0, weak)
    assert not plan.feasible and all(q.heat for q in plan.quarters)


def test_the_spa_kwh_goes_into_the_load_and_off_or_no_temperature_plans_nothing():
    plan = plan_spa(series([0.20] * 4), {}, {}, T0, 36.5, CFG)
    assert all(v == 0.75 for v in spa_kwh_per_quarter(plan).values()) and spa_kwh_per_quarter(None) == {}
    assert plan_spa(series([0.2]), {}, {}, T0, None, CFG) is None and plan_spa(series([0.2]), {}, {}, T0, 37, SpaConfig()) is None


def test_an_external_spa_is_forecast_in_the_cheapest_quarters_of_each_day():
    """Spapilot heats by itself in the cheapest hours (Mark, 1 Nov 2026: about 20 kWh a day since 29 Oct). HEMS places that energy in each
    day's cheapest quarters at the heater's power, and nothing in quarters already past."""
    from zoneinfo import ZoneInfo
    from hems.spa import external_spa_kwh
    tz = ZoneInfo("Europe/Amsterdam")
    midnight = datetime(2026, 11, 2, 0, 0, tzinfo=tz).astimezone(timezone.utc)
    prices = [0.40] * 96
    for k in range(48, 56):                       # 12:00-14:00 cheap
        prices[k] = 0.20
    starts = tuple(midnight + k * timedelta(minutes=15) for k in range(96))
    cfg = SpaConfig(enabled=True, daily_kwh=6.0)
    kwh = external_spa_kwh(PriceSeries(starts, tuple(prices), tuple(prices)), midnight, cfg, tz)
    assert sum(kwh.values()) == 6.0 and set(kwh) == set(starts[48:56])
    later = external_spa_kwh(PriceSeries(starts, tuple(prices), tuple(prices)), starts[52], cfg, tz)
    assert sum(later.values()) == 3.0, "the first hour of the cheap block is past"
    assert external_spa_kwh(PriceSeries(starts, tuple(prices), tuple(prices)), midnight, SpaConfig(enabled=True, control="climate"), tz) == {}


def test_the_external_spa_is_taken_out_of_the_load_history():
    """A day with a 3 kW spa running four hours above a 400 W base: up to daily_kwh is removed from the hours above the median, at most
    the heater's power per hour; a quiet day before the spa loses almost nothing."""
    from zoneinfo import ZoneInfo
    from hems.spa import without_flexible_load
    tz = ZoneInfo("Europe/Amsterdam")
    day = datetime(2026, 10, 30, 0, 0, tzinfo=tz)
    spa_day = [(day + timedelta(hours=h), 3400.0 if 11 <= h < 15 else 400.0) for h in range(24)]
    cleaned = without_flexible_load(spa_day, SpaConfig(enabled=True, daily_kwh=20.0), tz)
    assert all(abs(w - 400.0) < 1e-6 for _, w in cleaned)
    quiet = [(day - timedelta(days=2) + timedelta(hours=h), 450.0 if h == 18 else 400.0) for h in range(24)]
    assert sum(w for _, w in without_flexible_load(quiet, SpaConfig(enabled=True), tz)) >= sum(w for _, w in quiet) - 50
