"""2026-10-15: a battery at 74 % SoC was charged to 100 % at 04:15 for the morning sale (incident).

The sell buffer targeted 100 % (40 % floor + two hours at 8 kW). At 0.33 the margin gate approved the charge although the price
was above the 0.25 ceiling, and 0.9.0 let that approval overrule the ceiling.

``sell_buffer_min_soc`` is the SOC a sale needs at its start. Below it the battery is charged back up to exactly that value,
at the cheapest moment before the sale; above it nothing is bought. The sale then runs down to the conservative SOC, where
adaptive takes over.
"""

import pytest

from app import main as bm_main
from Tests import curves_2026_10_15 as real
from Tests import curves_2026_10_20 as oct_20
from Tests.plan_replay import amsterdam_tz, local_start, make_config, replay  # noqa: F401

# Mark's settings of 2026-10-15
USER_SETTINGS = {
    "soc.min_soc": 5,
    "soc.conservative_soc": 30,
    "soc.max_soc": 100,
    "soc.sell_buffer_min_soc": 40,
    "soc.sell_buffer_activation_hours_before_sell": 4,
    "heuristics.min_profit_threshold": 0.08,
    "heuristics.top_x_charge_hours": 4,
    "heuristics.charge_spread_max_price_delta": 0.02,
    "power.min_scaled_power": 6500,
}


def _plan(monkeypatch, hhmm, soc, curve=None, state=None, **overrides):
    """Plan 2026-10-15 at local ``hhmm`` with ``soc`` percent and Mark's settings (``overrides`` use ``section.key`` names)."""
    return replay(monkeypatch, hhmm, soc=soc, remaining_solar=3.4, day=15, state=state,
                  import_curve=curve or real.import_curve(), export_curve=real.export_curve(),
                  config=make_config(**{**USER_SETTINGS, **overrides}))


def _precharges(schedule):
    """The precharge periods of a schedule."""
    return [p for p in schedule["charge"] if p["window_type"] == "precharge"]


def _morning_sale(schedule):
    """The sell window that starts before 11:00 (the morning peak), or None."""
    return next((p for p in schedule["discharge"] if p["window_type"] == "discharge" and local_start(p).hour < 11), None)


def test_a_battery_at_74_percent_is_not_charged_and_sells_down_to_the_conservative_soc(monkeypatch, amsterdam_tz):
    """74 % is above the 40 % start SOC: nothing is bought at 0.33. The sale takes the 44 points down to 30 %: 11 kWh = 82 minutes."""
    schedule = _plan(monkeypatch, "04:15", soc=74.0)
    assert _precharges(schedule) == []
    assert not any(local_start(p).hour < 7 for p in schedule["charge"])  # no night charge at all
    sale = _morning_sale(schedule)
    assert sale is not None and local_start(sale).strftime("%H:%M") == "07:15" and sale["duration"] == 82


def test_the_buffer_target_is_the_start_soc_of_the_sale(monkeypatch, amsterdam_tz):
    """The target is sell_buffer_min_soc, not that value plus the sell hours (it was 100 % for two hours at 8 kW)."""
    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)
    schedule = _plan(monkeypatch, "04:15", soc=74.0, state=state)
    assert state.sell_buffer_required_soc == 40.0
    assert _precharges(schedule) == []


def test_below_the_start_soc_the_precharge_restores_it_at_the_cheapest_quarter_before_the_sale(monkeypatch, amsterdam_tz):
    """35 % at 03:30, the sale at 07:15: 5 points of 25 kWh at 8 kW are 10 minutes, bought in the cheapest quarter (04:15, 0.3323)."""
    schedule = _plan(monkeypatch, "03:30", soc=35.0)
    precharges = _precharges(schedule)
    assert len(precharges) == 1
    assert precharges[0]["power"] == 8000 and precharges[0]["duration"] == 10  # despite 0.33 above the 0.25 ceiling
    assert local_start(precharges[0]).strftime("%H:%M") == "04:15"


def test_the_precharge_waits_for_a_cheaper_stretch_before_the_sale(monkeypatch, amsterdam_tz):
    """With 05:00-06:00 at 0.318 (cheaper than the night, still no charge window of its own) the 57 minutes from 10 % to 40 % are bought there."""
    curve = real.import_curve()
    for entry in curve:
        if "T05:" in entry["start"]:
            entry["price"] = 0.318
    schedule = _plan(monkeypatch, "03:30", soc=10.0, curve=curve)
    precharge = _precharges(schedule)[0]
    assert local_start(precharge).strftime("%H:%M") == "05:00" and precharge["duration"] == 57


def test_the_climb_to_the_conservative_soc_is_not_sellable_energy(monkeypatch, amsterdam_tz):
    """From 20 % the precharge to 40 % (38 minutes) lifts the battery over the 30 % conservative SOC by only 10 points: 18 minutes of sale."""
    schedule = _plan(monkeypatch, "03:30", soc=20.0)
    assert _precharges(schedule)[0]["duration"] == 38
    sale = _morning_sale(schedule)
    assert sale is not None and sale["duration"] in (18, 19)  # 2.5 kWh at 8 kW; it was 38 minutes when the climb counted as sellable


def test_at_the_start_soc_there_is_nothing_to_restore(monkeypatch, amsterdam_tz):
    """Exactly 40 % is not under the start SOC."""
    assert _precharges(_plan(monkeypatch, "03:30", soc=40.0)) == []


def test_a_single_charge_slot_keeps_the_precharge_next_to_the_main_charge():
    """With one charge slot the precharge stays where it can coalesce with the main charge: it starts now."""
    from datetime import datetime, timezone

    now = datetime(2026, 10, 15, 1, 30, tzinfo=timezone.utc)
    deadline = datetime(2026, 10, 15, 5, 15, tzinfo=timezone.utc)
    curve = real.import_curve()
    assert bm_main._choose_precharge_start(curve, now, deadline, 10, 15, 1) == now
    assert bm_main._choose_precharge_start(curve, now, deadline, 10, 15, 3) != now  # the cheapest quarter is later
    assert bm_main._choose_precharge_start(curve, now, None, 10, 15, 3) == now  # no sale to aim for


# ---- 2026-10-15 08:33: SoC 57 % under the new 60 % start SOC, in the middle of the morning sale, planned 8000 W of charging


def _sale_state(monkeypatch, hhmm, soc):
    """Plan 2026-10-15 at ``hhmm`` with a 60 % start SOC and return (schedule, state)."""
    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)
    schedule = _plan(monkeypatch, hhmm, soc=soc, state=state, **{"soc.sell_buffer_min_soc": 60})
    return schedule, state


def test_the_pre_sell_check_does_not_run_while_the_sale_is_running(monkeypatch, amsterdam_tz):
    """The 07:15-08:45 window is running at 08:33: SoC 57 % is under the 60 % start SOC, but nothing is bought and discharge is not paused."""
    schedule, state = _sale_state(monkeypatch, "08:33", soc=57.0)
    assert _precharges(schedule) == []
    assert state.sell_buffer_required_soc is None  # no buffer protection either: it would pause the sale it protects
    assert any(p["window_type"] == "discharge" and local_start(p).hour < 11 for p in schedule["discharge"])


def test_the_gap_between_two_windows_of_the_same_sale_is_not_pre_sell(monkeypatch, amsterdam_tz):
    """08:45-09:00 lies between the 07:15 and the 09:00 window: still the same sale, so no precharge for the 09:00 window."""
    schedule, state = _sale_state(monkeypatch, "08:50", soc=50.0)
    assert _precharges(schedule) == []
    assert state.sell_buffer_required_soc is None


def test_before_the_sale_the_pre_sell_check_still_runs(monkeypatch, amsterdam_tz):
    """The same 57 % at 03:30, before the first window: the check runs and the battery is charged up to 60 %."""
    schedule, state = _sale_state(monkeypatch, "03:30", soc=57.0)
    assert _precharges(schedule) and state.sell_buffer_required_soc == 60.0


def _window(start, end):
    """A sell window between two datetimes."""
    return {"start": start, "end": end, "avg_price": 0.47}


def test_a_sale_of_an_earlier_day_does_not_switch_off_the_check_for_the_next_one():
    """Yesterday evening's window ended 12 hours ago (lead 4 h): it belongs to another sale, so the morning check is active."""
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc)
    main_charge = now + timedelta(hours=8)
    evening = _window(now - timedelta(hours=14), now - timedelta(hours=12))
    morning = _window(now + timedelta(hours=2), now + timedelta(hours=4))
    config = make_config(**USER_SETTINGS)
    target, _hours, _until = bm_main._calculate_dynamic_sell_buffer_soc(
        {"charge": [{"start": main_charge, "end": main_charge + timedelta(hours=4)}], "discharge": [evening, morning]}, now, config)
    assert target == 40.0
    # the same morning window, started 1 hour ago: the sale is running, no check
    running = _window(now - timedelta(hours=1), now + timedelta(hours=1))
    target, _hours, _until = bm_main._calculate_dynamic_sell_buffer_soc(
        {"charge": [{"start": main_charge, "end": main_charge + timedelta(hours=4)}], "discharge": [running]}, now, config)
    assert target is None


# ---- 2026-10-20: the pre-sell charge bought 2.7 kWh at 0.337 and 1 kWh at 0.387 for a 0.443 sale, outside the margin


def _plan_oct_20(monkeypatch, hhmm, soc, state=None, **overrides):
    """Plan 2026-10-20 at local ``hhmm`` with the settings of that morning (60 % start SOC, margin 0.12, efficiency 0.9)."""
    settings = {**USER_SETTINGS, "soc.sell_buffer_min_soc": 60, "heuristics.min_profit_threshold": 0.12, **overrides}
    return replay(monkeypatch, hhmm, soc=soc, remaining_solar=7.84, day=20, state=state,
                  import_curve=oct_20.import_curve(), export_curve=oct_20.export_curve(), config=make_config(**settings))


def _oct_20_state():
    """A fresh runtime state whose ``last_decision`` carries the trace of the plan."""
    return bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)


def test_a_precharge_that_does_not_earn_the_margin_is_not_bought(monkeypatch, amsterdam_tz):
    """49.8 % at 05:30: the 20 minutes cost 0.338 against a sale of 0.443 x 0.9 = 0.399, a margin of 0.061 under 0.12."""
    state = _oct_20_state()
    schedule = _plan_oct_20(monkeypatch, "05:30", soc=49.8, state=state)
    assert _precharges(schedule) == []
    precharge = state.last_decision["precharge"]
    assert precharge["decision"] == "skipped" and not precharge["allowed"]
    assert precharge["margin"] == pytest.approx(0.061, abs=1e-3)
    sale = _morning_sale(schedule)
    assert sale is not None and local_start(sale).strftime("%H:%M") == "07:30"  # the sale goes on with what the battery holds


def test_the_precharge_is_judged_on_its_own_price_not_on_the_cheapest_price_of_the_day(monkeypatch, amsterdam_tz):
    """The midday charge costs 0.243, the precharge 0.338: the margin and the trace use the price of the quarters it would buy."""
    state = _oct_20_state()
    _plan_oct_20(monkeypatch, "05:30", soc=49.8, state=state)
    precharge = state.last_decision["precharge"]
    assert precharge["charge_price"] == pytest.approx(0.3376, abs=1e-3)
    assert precharge["expected_sell_price"] == pytest.approx(0.4432, abs=1e-3)


def test_the_top_up_at_0387_for_the_same_sale_is_not_bought_either(monkeypatch, amsterdam_tz):
    """56 % at 07:00: 8 minutes at 0.387 against 0.443 x 0.9 is a margin of 0.012, with or without a looser efficiency."""
    for settings in ({}, {"heuristics.round_trip_efficiency": 1.0, "heuristics.min_profit_threshold": 0.10}):
        schedule = _plan_oct_20(monkeypatch, "07:00", soc=56.0, state=_oct_20_state(), **settings)
        assert _precharges(schedule) == []


def test_a_precharge_that_earns_the_margin_is_still_bought(monkeypatch, amsterdam_tz):
    """With efficiency 1.0 and margin 0.10 the 05:30 charge earns 0.443 - 0.338 = 0.105: restored to 60 % as before."""
    state = _oct_20_state()
    schedule = _plan_oct_20(monkeypatch, "05:30", soc=49.8, state=state,
                            **{"heuristics.round_trip_efficiency": 1.0, "heuristics.min_profit_threshold": 0.10})
    precharges = _precharges(schedule)
    assert len(precharges) == 1 and precharges[0]["duration"] == 20
    assert state.last_decision["precharge"]["decision"] == "added" and state.last_decision["precharge"]["allowed"]
