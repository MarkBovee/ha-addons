"""Task E: charge power is held for an hour unless SoC or the solar forecast moves."""

import logging
from datetime import datetime, timedelta, timezone

from app import main as bm_main
from app.plan_stability import (
    ChargePowerLock,
    apply_charge_power_locks,
    diff_plan_powers,
    forecast_changed,
    project_soc,
)
from Tests.plan_replay import amsterdam_tz, local_start, replay  # noqa: F401

NOW = datetime(2026, 10, 7, 10, 15, tzinfo=timezone.utc)


def _period(power, start=NOW, minutes=240, **extra):
    return {
        "start": start.isoformat(), "duration": minutes, "power": power,
        "window_type": "charge", "base_power": 8000, **extra,
    }


def _lock(power=1000, age_min=15, soc=36.0, remaining=15.0, pv=0.0):
    return ChargePowerLock(power, NOW - timedelta(minutes=age_min), soc, remaining, pv)


def _apply(period, lock, soc=38.0, remaining=15.0, pv=0.0, previous=None):
    # Locks are keyed by the window end (UTC): 14:15 for a 240 min window from 10:15.
    period_end = NOW + timedelta(minutes=240)
    locks = {period_end.astimezone(timezone.utc).isoformat(): lock} if lock else {}
    events = apply_charge_power_locks(
        [period], locks, NOW, soc, remaining, pv, previous, 25.0,
    )
    return events, locks


def test_power_is_held_while_inputs_follow_the_projection():
    plan = {"charge": [_period(1000, NOW - timedelta(minutes=15))], "discharge": []}
    period = _period(1147)
    events, _ = _apply(period, _lock(), soc=38.0, previous=plan)

    assert period["power"] == 1000
    assert events[0]["action"] == "kept" and events[0]["recomputed_power"] == 1147


def test_soc_deviation_over_5pp_releases_the_lock_and_is_logged():
    plan = {"charge": [_period(1000, NOW - timedelta(minutes=15))], "discharge": []}
    period = _period(2029)
    events, locks = _apply(period, _lock(), soc=29.0, previous=plan)  # projected ~37

    assert period["power"] == 2029
    assert events[0]["action"] == "recomputed" and "SoC" in events[0]["reason"]
    assert list(locks.values())[0].power == 2029


def test_forecast_change_over_25pct_releases_the_lock():
    plan = {"charge": [_period(1000, NOW - timedelta(minutes=15))], "discharge": []}
    period = _period(2500)
    events, _ = _apply(period, _lock(remaining=15.0), soc=37.0, remaining=8.0, previous=plan)

    assert period["power"] == 2500
    assert "solar forecast" in events[0]["reason"]


def test_normal_depletion_of_remaining_solar_is_not_a_forecast_change():
    lock = _lock(remaining=15.0, age_min=60 - 1, pv=4000)
    # 4 kW for ~1h consumed ~4 kWh of the remaining budget: 15 -> 11
    assert not forecast_changed(lock, 11.0, 4000, NOW)
    assert forecast_changed(lock, 6.0, 4000, NOW)
    assert forecast_changed(lock, 19.5, 4000, NOW)  # revised up by >25%


def test_lock_expires_after_one_hour():
    period = _period(1147)
    events, locks = _apply(period, _lock(age_min=61), soc=38.0, previous=None)

    assert period["power"] == 1147
    assert events[0]["action"] == "recomputed" and "older than" in events[0]["reason"]


def test_new_window_is_locked_without_an_event_and_other_types_are_ignored():
    period = _period(1147)
    precharge = {**_period(8000), "window_type": "precharge"}
    locks = {}
    events = apply_charge_power_locks([period, precharge], locks, NOW, 38.0, 15.0, 0.0, None, 25.0)

    assert events == [] and len(locks) == 1 and precharge["power"] == 8000


def test_project_soc_adds_grid_and_pv_and_subtracts_scheduled_sells():
    plan = {
        "charge": [{"start": NOW.isoformat(), "duration": 60, "power": 2000, "forecast_solar_kwh": 3.0}],
        "discharge": [
            {"start": (NOW + timedelta(hours=1)).isoformat(), "duration": 30, "power": 5000,
             "window_type": "discharge"},
            {"start": (NOW + timedelta(hours=1)).isoformat(), "duration": 30, "power": 3000,
             "window_type": "adaptive"},
        ],
    }
    projected = project_soc(plan, 40.0, NOW, NOW + timedelta(hours=2), 25.0)

    assert round(projected, 1) == round(40 + (2.0 + 3.0 - 2.5) / 25 * 100, 1)


def test_diff_plan_powers_merges_quarters_into_runs():
    old = {"charge": [_period(1000, NOW, 60)], "discharge": []}
    new = {"charge": [_period(1500, NOW, 60)], "discharge": []}
    small = {"charge": [_period(1200, NOW, 60)], "discharge": []}

    runs = diff_plan_powers(old, new, NOW)
    assert len(runs) == 1 and runs[0]["quarters"] == 4
    assert (runs[0]["old_power"], runs[0]["new_power"]) == (1000, 1500)
    assert diff_plan_powers(old, small, NOW) == []  # 20% < 25%
    assert diff_plan_powers(None, new, NOW) == []


def test_regeneration_keeps_the_window_power_and_logs_when_it_releases(monkeypatch, amsterdam_tz, caplog):
    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)

    first = replay(monkeypatch, "12:00", 36, 15.0, state=state)
    held = replay(monkeypatch, "12:15", 38, 14.0, state=state, pv_power_w=3000)
    raw = replay(monkeypatch, "12:15", 38, 14.0, pv_power_w=3000)

    def midday(schedule):
        return next(p for p in schedule["charge"] if p["window_type"] == "charge" and local_start(p).day == 7)

    assert midday(held)["power"] == midday(first)["power"] == 1000
    assert midday(raw)["power"] != 1000  # without the lock it would creep

    with caplog.at_level(logging.INFO):
        released = replay(monkeypatch, "12:30", 30, 13.0, state=state, pv_power_w=3000)
    assert midday(released)["power"] > 1500
    assert any("recomputed" in r.message and "SoC" in r.message for r in caplog.records)
    assert any("Planned charge power changed >25%" in r.message for r in caplog.records)
