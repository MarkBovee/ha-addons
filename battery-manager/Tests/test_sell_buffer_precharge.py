"""2026-10-15: a battery at 74 % SoC was charged to 100 % at 04:15 for the morning sale (incident).

The sell buffer targeted 100 % (40 % floor + two hours at 8 kW). At 0.33 the margin gate approved the charge although the price
was above the 0.25 ceiling, and 0.9.0 let that approval overrule the ceiling. ``sell_buffer_min_soc`` is the value the battery
must not sit under: below it the precharge restores it, above it the buffer target is no reason to buy at an expensive price.
"""

from datetime import datetime, timezone

from app import main as bm_main
from Tests import curves_2026_10_15 as real
from Tests.plan_replay import amsterdam_tz, local_start, make_config, replay  # noqa: F401

# Mark's settings of 2026-10-15
USER_SETTINGS = {
    "soc.min_soc": 5,
    "soc.conservative_soc": 30,
    "soc.max_soc": 100,
    "soc.sell_buffer_min_soc": 40,
    "soc.sell_buffer_rounding_step_pct": 10,
    "soc.sell_buffer_activation_hours_before_sell": 4,
    "heuristics.min_profit_threshold": 0.08,
    "heuristics.top_x_charge_hours": 4,
    "heuristics.charge_spread_max_price_delta": 0.02,
    "power.min_scaled_power": 6500,
}


def _plan(monkeypatch, hhmm, soc):
    """Plan 2026-10-15 at local ``hhmm`` with ``soc`` percent and Mark's settings."""
    return replay(monkeypatch, hhmm, soc=soc, remaining_solar=3.4, day=15,
                  import_curve=real.import_curve(), export_curve=real.export_curve(), config=make_config(**USER_SETTINGS))


def _precharges(schedule):
    """The precharge periods of a schedule."""
    return [p for p in schedule["charge"] if p["window_type"] == "precharge"]


def test_a_battery_at_74_percent_is_not_charged_for_the_buffer_at_0_33(monkeypatch, amsterdam_tz):
    """74 % is 34 points above the floor; 0.33 is above the 0.25 ceiling, so nothing is bought for the buffer."""
    schedule = _plan(monkeypatch, "04:15", soc=74.0)
    assert _precharges(schedule) == []
    assert not any(p["start"] and local_start(p).hour < 7 for p in schedule["charge"])  # no night charge at all


def test_the_buffer_target_stays_above_the_battery_without_charging_it(monkeypatch, amsterdam_tz):
    """The target is still 100 % (it holds adaptive discharge); it just no longer buys energy above the floor."""
    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)
    _plan_state = replay(monkeypatch, "04:15", soc=74.0, remaining_solar=3.4, day=15, import_curve=real.import_curve(),
                         export_curve=real.export_curve(), config=make_config(**USER_SETTINGS), state=state)
    assert state.sell_buffer_required_soc == 100.0
    assert _precharges(_plan_state) == []


def test_below_the_floor_the_precharge_restores_the_floor_and_not_the_buffer_target(monkeypatch, amsterdam_tz):
    """35 % is 5 points under the 40 % floor: 5 pp of 25 kWh at 8 kW is 10 minutes, not the 65 points up to 100 %."""
    schedule = _plan(monkeypatch, "04:15", soc=35.0)
    precharges = _precharges(schedule)
    assert len(precharges) == 1
    assert precharges[0]["power"] == 8000 and precharges[0]["duration"] == 10  # despite 0.33 above the 0.25 ceiling


def test_at_the_floor_there_is_nothing_to_restore(monkeypatch, amsterdam_tz):
    """Exactly 40 % is not under the floor."""
    assert _precharges(_plan(monkeypatch, "04:15", soc=40.0)) == []
