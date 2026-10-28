from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from hems.contracts import Reading
from hems.ev import (STATUS_AT_RISK, STATUS_FORCED, STATUS_IDLE, STATUS_NO_SOC, STATUS_NOT_PLUGGED, STATUS_OFF, STATUS_PLANNED, STATUS_PROBLEM,
                     EvConfig, EvState, effective_price, ev_kwh_per_quarter, next_deadline, plan_ev, required_grid_kwh, setpoint)
from hems.prices import PriceSeries

AMS = ZoneInfo("Europe/Amsterdam")
MON_2200 = datetime(2026, 10, 26, 22, 0, tzinfo=AMS)          # a Monday evening: the next deadline is Thursday, days beyond any known price
WED_2200 = datetime(2026, 10, 28, 22, 0, tzinfo=AMS)          # the evening before the Thursday 07:30 deadline, which the known prices cover
SCHEDULE = (time(7, 30), None, None, time(7, 30), None, None, None)     # Monday and Thursday 07:30


def series(import_prices: list[float], start: datetime = WED_2200, export_prices: list[float] | None = None) -> PriceSeries:
    """A UTC quarter grid from `start` with the given import prices; export defaults to 30 % under import."""
    first = start.astimezone(timezone.utc)
    starts = tuple(first + timedelta(minutes=15 * i) for i in range(len(import_prices)))
    export = export_prices if export_prices is not None else [round(p * 0.7, 4) for p in import_prices]
    return PriceSeries(starts, tuple(import_prices), tuple(export))


def config(**kw) -> EvConfig:
    """The car of this installation with the Monday and Thursday schedule, enabled."""
    return EvConfig(enabled=True, deadlines=SCHEDULE, **kw)


def plugged(soc: float = 50.0, now: datetime = WED_2200, **kw) -> EvState:
    """A plugged-in car with a fresh SoC."""
    return EvState(True, Reading(soc, now), **kw)


def test_the_next_deadline_follows_the_weekly_schedule():
    """Intent: after Monday 07:30 passed, the next deadline is Thursday 07:30; before it, it is that same morning.
    Why: a daily-time setting cannot say 'Monday and Thursday', which is how this car is used."""
    assert next_deadline(MON_2200, SCHEDULE, AMS) == datetime(2026, 10, 29, 7, 30, tzinfo=AMS)
    assert next_deadline(datetime(2026, 10, 26, 6, 0, tzinfo=AMS), SCHEDULE, AMS) == datetime(2026, 10, 26, 7, 30, tzinfo=AMS)
    assert next_deadline(MON_2200, (None,) * 7, AMS) is None


def test_the_required_energy_goes_to_the_cheapest_quarters_before_the_deadline():
    """Intent: with a deadline the required kWh lands in the cheapest quarters that end before it, at full current, not at the first ones.
    Why: charging as soon as the car is plugged in ignores the price curve, which is the whole point of the module."""
    # 38 quarters until the deadline plus 2 after it; the cheap block is 02:00-03:30 (6 quarters), the rest costs 0.30, after the deadline 0.01
    prices = [0.30] * 16 + [0.10] * 6 + [0.30] * 16 + [0.01] * 2
    cfg = config()
    need = required_grid_kwh(60.0, cfg.target_required_pct, cfg)                 # 60 % -> 80 % is about 18 kWh from the grid
    plan = plan_ev(series(prices), {}, WED_2200, cfg, plugged(60.0), AMS)
    assert plan.status == STATUS_PLANNED and plan.deadline == datetime(2026, 10, 29, 7, 30, tzinfo=AMS)
    assert plan.planned_kwh() >= need - 1e-6
    assert all(q.start + timedelta(minutes=15) <= plan.deadline.astimezone(timezone.utc) for q in plan.quarters)
    cheap_block = {s for s in series(prices).starts[16:22]}
    assert cheap_block <= {q.start for q in plan.quarters}
    assert all(6.0 <= q.current_a <= 16.0 for q in plan.quarters)


def test_a_remainder_under_the_minimum_current_is_rounded_up_to_the_minimum():
    """Intent: a last quarter that needs less than 6 A is charged at 6 A, never at 3 A.
    Why: a car does not charge below the minimum, so a 3 A request would silently deliver nothing."""
    cfg = config(target_max_pct=80.0)
    need = required_grid_kwh(79.5, cfg.target_required_pct, cfg)                 # a few tenths of a kWh
    plan = plan_ev(series([0.30] * 40), {}, WED_2200, cfg, plugged(79.5), AMS)
    assert need < cfg.quarter_kwh(cfg.min_current_a)
    assert [q.current_a for q in plan.quarters] == [6.0]


def test_surplus_makes_a_quarter_cheaper_than_the_same_import_price():
    """Intent: of two quarters with the same import price the one with PV surplus is charged first, because that kWh costs the export price.
    Why: this is how solar charging falls out of the prices without a separate mode."""
    cfg = config()
    assert effective_price(16, 0.30, 0.10, 0.0, cfg) == pytest.approx(0.30)
    assert effective_price(16, 0.30, 0.10, 100.0, cfg) == pytest.approx(0.10)
    mixed = effective_price(16, 0.30, 0.10, cfg.quarter_kwh(16) / 2, cfg)
    assert mixed == pytest.approx(0.20)
    prices = series([0.30] * 38)                                   # up to the Thursday deadline
    sunny = prices.starts[10]
    plan = plan_ev(prices, {sunny: 10.0}, WED_2200, config(target_required_pct=51.0), plugged(50.0), AMS)
    assert [q.start for q in plan.quarters] == [sunny]


def test_opportunistic_charging_stays_under_the_price_threshold():
    """Intent: above the required target only quarters at or under the threshold are charged, and none when nothing is that cheap.
    Why: the threshold is the owner's willingness to pay; the extra energy must never be bought above it."""
    cfg = config(target_required_pct=50.0, max_price_eur_kwh=0.12)
    prices = [0.30] * 8 + [0.10] * 4 + [0.30] * 8
    plan = plan_ev(series(prices), {}, WED_2200, cfg, plugged(50.0), AMS)
    assert plan.required_kwh == 0 and plan.optional_kwh > 0
    assert plan.quarters and all(q.price <= 0.12 + 1e-9 and q.tier == "cheap" for q in plan.quarters)
    none = plan_ev(series([0.30] * 20), {}, WED_2200, cfg, plugged(50.0), AMS)
    assert none.status == STATUS_IDLE and not none.quarters


def test_solar_only_charges_just_where_the_surplus_covers_the_minimum_current():
    """Intent: with solar-only on, a cheap quarter without enough surplus is skipped and a quarter with it is used.
    Why: solar-only is the one hard condition of the planner and must hold."""
    cfg = config(target_required_pct=50.0, max_price_eur_kwh=0.50, solar_only=True)
    prices = series([0.10] * 12)
    sunny = prices.starts[5]
    plan = plan_ev(prices, {sunny: 3.0, prices.starts[6]: 0.2}, WED_2200, cfg, plugged(50.0), AMS)
    assert {q.start for q in plan.quarters} == {sunny}


def test_a_deadline_the_known_prices_cannot_meet_is_at_risk_with_the_shortfall():
    """Intent: when the quarters before the deadline hold less energy than needed the status says so and reports the shortfall.
    Why: a silent half-plan would leave the car short at 07:30."""
    start = datetime(2026, 10, 29, 4, 0, tzinfo=AMS)             # Thursday 04:00, deadline 07:30: 14 quarters, at most 38.6 kWh
    cfg = config()
    plan = plan_ev(series([0.20] * 20, start), {}, start, cfg, plugged(10.0, start), AMS)
    assert plan.status == STATUS_AT_RISK and plan.shortfall_kwh > 0
    assert plan.planned_kwh() == pytest.approx(14 * cfg.quarter_kwh(16.0))


def test_a_deadline_beyond_the_known_prices_waits_for_the_prices_that_are_not_there_yet():
    """Intent: tonight, with prices only until midnight and a deadline at 07:30, nothing is required yet because the unknown hours can still deliver it.
    Why: charging at once out of caution would pay tonight's price for energy tomorrow's cheaper hours could deliver."""
    cfg = EvConfig(enabled=True, deadlines=(time(7, 30),) * 7, target_max_pct=80.0)
    plan = plan_ev(series([0.30] * 8, MON_2200), {}, MON_2200, cfg, plugged(60.0, MON_2200), AMS)
    assert plan.status == STATUS_IDLE and plan.shortfall_kwh == 0 and not plan.quarters
    assert plan.required_kwh > 0 and cfg.quarter_kwh(16.0) * 4 * 7.5 > plan.required_kwh


def test_forced_charging_takes_the_earliest_quarters_at_the_highest_current():
    """Intent: the override plans the required energy from now on at the ceiling current, whatever the price.
    Why: it is for the day the car must be charged and the prices are bad."""
    prices = [0.50] * 4 + [0.05] * 20
    cfg = config()
    plan = plan_ev(series(prices), {}, WED_2200, cfg, plugged(60.0, force=True), AMS)
    assert plan.status == STATUS_FORCED
    assert [q.current_a for q in plan.quarters][:3] == [16.0, 16.0, 16.0]
    assert plan.quarters[0].start == series(prices).starts[0] and {q.tier for q in plan.quarters} == {"forced"}


def test_the_plan_says_why_it_has_no_plan():
    """Intent: off, no car, a problem and a missing or old SoC each give their own status.
    Why: 'why nothing?' must be answerable from the sensor."""
    prices = series([0.3] * 8)
    assert plan_ev(prices, {}, WED_2200, EvConfig(), plugged(), AMS).status == STATUS_OFF
    assert plan_ev(prices, {}, WED_2200, config(), EvState(False, None), AMS).status == STATUS_NOT_PLUGGED
    assert plan_ev(prices, {}, WED_2200, config(), plugged(problem=True), AMS).status == STATUS_PROBLEM
    assert plan_ev(prices, {}, WED_2200, config(), EvState(True, None), AMS).status == STATUS_NO_SOC
    old = EvState(True, Reading(50.0, WED_2200 - timedelta(hours=2)))
    assert plan_ev(prices, {}, WED_2200, config(), old, AMS).status == STATUS_NO_SOC


def test_planned_energy_is_the_load_the_battery_planner_sees():
    """Intent: the load map holds the grid kWh of every planned quarter.
    Why: the battery plans around the EV only if the EV is in its load forecast."""
    plan = plan_ev(series([0.30] * 40), {}, WED_2200, config(), plugged(70.0), AMS)
    load = ev_kwh_per_quarter(plan)
    assert sum(load.values()) == pytest.approx(plan.planned_kwh()) and len(load) == len(plan.quarters)


def test_the_setpoint_holds_minimum_times_unless_urgent_and_obeys_the_grid_limit():
    """Intent: a started charge is not stopped inside the minimum on-time, a stop is not undone inside the off-time, an urgent plan ignores
    both, the grid limit caps the current and a cap under 6 A means zero.
    Why: stop-start cycles wear the contactor and the car; the fuse comes before the plan."""
    cfg, now = config(), WED_2200
    prices = series([0.05] * 12 + [0.30] * 28)                              # the first quarters are the cheapest: the plan charges now
    active = plan_ev(prices, {}, now, cfg, plugged(10.0), AMS)
    idle = plan_ev(prices, {}, now, config(target_required_pct=10.0, target_max_pct=10.0), plugged(10.0), AMS)
    assert active.quarters[0].start == prices.starts[0] and not idle.quarters
    just_started = EvState(True, Reading(10.0, now), charging=True, last_change=now - timedelta(minutes=3))
    long_running = EvState(True, Reading(10.0, now), charging=True, last_change=now - timedelta(minutes=30))
    just_stopped = EvState(True, Reading(10.0, now), charging=False, last_change=now - timedelta(minutes=3))
    held_on = setpoint(idle, now, just_started, cfg)
    assert (held_on.code, held_on.current_a) == ("hold_min_on", cfg.min_current_a)
    assert setpoint(idle, now, long_running, cfg).current_a == 0
    held_off = setpoint(active, now, just_stopped, cfg)
    assert (held_off.code, held_off.current_a, held_off.planned_a) == ("hold_min_off", 0.0, 16.0)
    forced = plan_ev(prices, {}, now, cfg, plugged(10.0, force=True), AMS)
    assert setpoint(forced, now, just_stopped, cfg).current_a == 16.0
    assert setpoint(active, now, long_running, cfg).current_a == 16.0
    capped = setpoint(active, now, long_running, cfg, allowed_a=8.0)
    assert (capped.code, capped.current_a) == ("limited_by_grid", 8.0)
    assert setpoint(active, now, long_running, cfg, allowed_a=4.0).current_a == 0.0


def test_the_setpoint_is_zero_when_there_is_no_plan_even_while_a_charge_just_started():
    """Intent: with a socket problem, no car or no SoC the setpoint is 0 A and says why, also inside the minimum on-time of a charge that just started.
    Why: the hold-on rule must never ask for 6 A from a socket that reports a problem."""
    cfg, now = config(), WED_2200
    charging = EvState(True, Reading(50.0, now), charging=True, problem=True, last_change=now - timedelta(minutes=2))
    for state in (charging, EvState(False, None, charging=True, last_change=now - timedelta(minutes=2))):
        plan = plan_ev(series([0.3] * 8), {}, now, cfg, state, AMS)
        point = setpoint(plan, now, state, cfg)
        assert point.current_a == 0.0 and point.code == plan.status
