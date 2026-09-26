"""Regression tests for reduced-mode adaptive behavior in main loop."""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from typing import Any, cast

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import main as bm_main


class _SolarMonitorStub:
    def check_passive_state(self, _ha_api):
        return False


class _ActiveSolarMonitorStub:
    # Represent active solar surplus without consulting HA sensor state.
    def check_passive_state(self, _ha_api):
        return True


class _GapSchedulerStub:
    def generate_passive_gap_schedule(self):
        return {"charge": [], "discharge": []}


class _FakeMqttClient:
    def __init__(self):
        self.published = []

    def is_connected(self):
        return True

    def publish_raw(self, topic, payload, retain=False):
        self.published.append({"topic": topic, "payload": deepcopy(payload), "retain": retain})
        return True


def test_reduced_mode_uses_adaptive_power(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 30
    config["soc"]["min_soc"] = 5
    config["power"]["min_discharge_power"] = 0
    config["power"]["max_discharge_power"] = 8000
    config["timing"]["adaptive_power_grace_seconds"] = 60

    now = datetime.now(timezone.utc)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [],
            "discharge": [
                {
                    "start": (now - timedelta(minutes=10)).isoformat(),
                    "duration": 60,
                    "power": 6000,
                    "window_type": "discharge",
                }
            ],
        },
        schedule_generated_at=now,
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 30.0,
        config["entities"]["grid_power_entity"]: 138.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 120.0,
        config["entities"]["battery_power_entity"]: 119.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 13.0,
    }

    published = []
    entity_updates = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append((schedule, force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert published, "Expected reduced/adaptive override schedule to be published"

    override_schedule = published[-1][0]
    active_period = override_schedule["discharge"][0]

    assert active_period["window_type"] == "adaptive"
    assert active_period["power"] == 300
    assert state.last_effective_discharge_power == 300
    assert state.published_schedule == override_schedule

    last_power_updates = [
        call for call in entity_updates
        if call[0][1] == bm_main.ENTITY_EFFECTIVE_DISCHARGE_POWER
    ]
    assert last_power_updates, "Expected ENTITY_EFFECTIVE_DISCHARGE_POWER to be updated"
    assert last_power_updates[-1][0][2] == "300"
    assert last_power_updates[-1][0][3]["active_window_type"] == "adaptive"


# Ensure an active safety pause keeps later profitable windows in the plan.
# Suspend published discharges without mutating the generated plan for recovery.
def test_pause_schedule_suspends_discharge_without_mutating_source_plan():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    current_period = {
        "start": (now - timedelta(minutes=10)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    future_period = {
        "start": (now + timedelta(minutes=20)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    charge_period = {
        "start": (now + timedelta(hours=2)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "charge",
    }

    schedule = {"charge": [charge_period], "discharge": [current_period, future_period]}
    paused = bm_main._build_pause_schedule(schedule)

    assert paused["charge"] == [charge_period]
    assert paused["discharge"] == []
    assert schedule["discharge"] == [current_period, future_period]


# Exercise pause recovery with EV hold and unavailable SOC inputs.
@pytest.mark.parametrize(("soc_value", "ev_power"), [(70.0, 700.0), (None, 0.0)])
def test_pause_preserves_future_windows_with_ev_hold_or_missing_soc(monkeypatch, soc_value, ev_power):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["ev_charger"]["enabled"] = True

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    current_period = {
        "start": (now - timedelta(minutes=10)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    future_period = {
        "start": (now + timedelta(minutes=30)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    main_charge_period = {
        "start": (now + timedelta(hours=1)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "charge",
    }
    post_charge_period = {
        "start": (now + timedelta(hours=2)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    state = bm_main.RuntimeState(
        schedule={
            "charge": [main_charge_period],
            "discharge": [current_period, future_period, post_charge_period],
        },
        schedule_generated_at=now,
        sell_buffer_required_soc=80.0,
    )
    sensor_values = {
        config["entities"]["soc_entity"]: soc_value,
        config["entities"]["grid_power_entity"]: 100.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 400.0,
        config["entities"]["battery_power_entity"]: 8000.0,
        config["ev_charger"]["entity_id"]: ev_power,
        config["entities"]["temperature_entity"]: 15.0,
    }
    published = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            published.append(deepcopy(schedule)),
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert published
    assert published[-1]["discharge"] == []
    assert state.schedule["discharge"] == [current_period, future_period, post_charge_period]
    assert state.schedule_pause_active

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert state.schedule_pause_active
    assert state.published_schedule["discharge"] == []


# Restore the unfiltered plan when a prior protective hold clears.
@pytest.mark.parametrize("soc_value", [85.0, 30.0])
def test_monitor_restores_generated_windows_when_protection_clears(monkeypatch, soc_value):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["ev_charger"]["enabled"] = True

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    current_period = {
        "start": (now - timedelta(minutes=10)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    future_period = {
        "start": (now + timedelta(minutes=30)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": [current_period, future_period]},
        schedule_generated_at=now,
        schedule_pause_active=True,
        sell_buffer_required_soc=20.0,
        sell_buffer_valid_until=now + timedelta(hours=2),
    )
    sensor_values = {
        config["entities"]["soc_entity"]: soc_value,
        config["entities"]["grid_power_entity"]: 100.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 400.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 15.0,
    }
    published = []
    publish_results = [False, True]

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            published.append(deepcopy(schedule)),
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None and publish_results[0] else None,
            publish_results.pop(0),
        )[-1],
    )

    for _ in range(2):
        bm_main.monitor_and_adjust_active_period(
            config,
            ha_api=cast(Any, object()),
            mqtt_client=None,
            state=state,
            solar_monitor=cast(Any, _SolarMonitorStub()),
            gap_scheduler=cast(Any, _GapSchedulerStub()),
        )

    expected_schedule = bm_main._build_pause_recovery_schedule(
        state.schedule,
        soc_value,
        config["soc"]["conservative_soc"],
        state.sell_buffer_valid_until,
    )
    assert published == [expected_schedule, expected_schedule]
    if soc_value <= config["soc"]["conservative_soc"]:
        assert [period["window_type"] for period in published[-1]["discharge"]] == [
            "adaptive",
            "adaptive",
            "discharge",
        ]
        assert [period["power"] for period in published[-1]["discharge"]] == [0, 0, 8000]
    assert not state.schedule_pause_active


# Expire the dynamic reserve when its associated main charge begins.
def test_sell_buffer_target_expires_at_main_charge_start():
    now = datetime.now(timezone.utc)
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": []},
        schedule_generated_at=now,
        sell_buffer_required_soc=80.0,
        sell_buffer_valid_until=now,
    )

    assert bm_main._get_active_sell_buffer_soc(state, now) is None


def test_monitor_uses_published_adaptive_schedule_for_mode_and_power(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 30

    now = datetime.now(timezone.utc)
    original_schedule = {
        "charge": [],
        "discharge": [
            {
                "start": (now - timedelta(minutes=10)).isoformat(),
                "duration": 60,
                "power": 6000,
                "window_type": "discharge",
            }
        ],
    }
    published_schedule = {
        "charge": [],
        "discharge": [
            {
                "start": (now - timedelta(minutes=10)).isoformat(),
                "duration": 60,
                "power": 300,
                "window_type": "adaptive",
            }
        ],
    }
    state = bm_main.RuntimeState(
        schedule=original_schedule,
        published_schedule=published_schedule,
        schedule_generated_at=now,
        last_price_range="passive",
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 45.0,
        config["entities"]["grid_power_entity"]: 80.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 200.0,
        config["entities"]["battery_power_entity"]: 290.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 12.0,
    }

    entity_updates = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "passive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, _schedule, _dry_run, state=None, force=False: True,
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    assert mode_updates[-1][0][2] == "adaptive"

    action_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_CURRENT_ACTION]
    assert action_updates
    assert action_updates[-1][0][2] == "Adaptive 400W"

    power_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_EFFECTIVE_DISCHARGE_POWER]
    assert power_updates
    assert power_updates[-1][0][2] == "400"
    assert power_updates[-1][0][3]["active_window_type"] == "adaptive"


def test_zero_power_adaptive_placeholder_does_not_pause_or_clear_future_discharge(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 30

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [],
            "discharge": [
                {
                    "start": (now - timedelta(minutes=10)).isoformat(),
                    "duration": 60,
                    "power": 0,
                    "window_type": "adaptive",
                },
                {
                    "start": (now + timedelta(minutes=20)).isoformat(),
                    "duration": 90,
                    "power": 8000,
                    "window_type": "discharge",
                },
            ],
        },
        schedule_generated_at=now,
        sell_buffer_required_soc=80.0,
        last_price_range="discharge",
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 86.7,
        config["entities"]["grid_power_entity"]: 863.0,
        config["entities"]["solar_power_entity"]: 97.0,
        config["entities"]["house_load_entity"]: 399.0,
        config["entities"]["battery_power_entity"]: 111.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 22.0,
    }

    entity_updates = []
    published = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "adaptive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            published.append((deepcopy(schedule), force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert published
    assert any(
        p.get("window_type") == "discharge" and p.get("power") == 8000
        for p in published[-1][0]["discharge"]
    )

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    assert mode_updates[-1][0][2] == "adaptive"

    action_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_CURRENT_ACTION]
    assert action_updates
    assert "Adaptive" in action_updates[-1][0][2]


def test_idle_current_action_shows_next_scheduled_window(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    next_charge_start = now + timedelta(hours=2)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [
                {
                    "start": next_charge_start.isoformat(),
                    "duration": 60,
                    "power": 8000,
                    "window_type": "charge",
                }
            ],
            "discharge": [],
        },
        published_schedule={
            "charge": [
                {
                    "start": next_charge_start.isoformat(),
                    "duration": 60,
                    "power": 8000,
                    "window_type": "charge",
                }
            ],
            "discharge": [],
        },
        schedule_generated_at=now,
        last_price_range="discharge",
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 12.0,
        config["entities"]["grid_power_entity"]: -97.0,
        config["entities"]["solar_power_entity"]: 1254.0,
        config["entities"]["house_load_entity"]: 1201.0,
        config["entities"]["battery_power_entity"]: -53.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 12.0,
    }

    entity_updates = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "adaptive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: True)

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    action_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_CURRENT_ACTION]
    assert action_updates
    assert action_updates[-1][0][2].startswith("Idle | Next: Charge 8000W at")
    assert action_updates[-1][0][3]["next_event"].startswith("Next: Charge 8000W at")

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    assert mode_updates[-1][0][2] == "idle"
    assert mode_updates[-1][0][3]["price_range"] == "adaptive"


def test_discharge_feasibility_truncates_second_window_to_thirty_minutes():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 20
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 5
    config["soc"]["sell_buffer_enabled"] = False
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000

    now = datetime(2026, 4, 10, 17, 0, tzinfo=timezone.utc)
    discharge_windows = [
        {
            "start": datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc),
            "avg_price": 0.412,
        },
        {
            "start": datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 4, 10, 21, 0, tzinfo=timezone.utc),
            "avg_price": 0.401,
        },
    ]

    feasible = bm_main._filter_supported_discharge_windows(
        discharge_windows,
        charge_schedule=[],
        soc=55.0,
        config=config,
        not_before=now,
        top_x_discharge_count=2,
        min_scaled_power=4000,
    )

    assert len(feasible) == 2
    assert feasible[0] == discharge_windows[0]
    assert feasible[1]["start"] == discharge_windows[1]["start"]
    assert feasible[1]["end"] - feasible[1]["start"] == timedelta(minutes=30)


def test_discharge_feasibility_truncates_to_one_point_five_hours_on_conservative_floor():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 20
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 40
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_scaled_power"] = 8000

    now = datetime(2026, 4, 10, 17, 0, tzinfo=timezone.utc)
    discharge_windows = [
        {
            "start": datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 4, 10, 21, 0, tzinfo=timezone.utc),
            "avg_price": 0.412,
        },
    ]

    feasible = bm_main._filter_supported_discharge_windows(
        discharge_windows,
        charge_schedule=[],
        soc=100.0,
        config=config,
        not_before=now,
        top_x_discharge_count=1,
        min_scaled_power=8000,
    )

    assert len(feasible) == 1
    assert feasible[0]["end"] - feasible[0]["start"] == timedelta(minutes=90)


def test_discharge_feasibility_respects_conservative_soc_floor():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 10
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 60
    config["power"]["max_discharge_power"] = 5000
    config["power"]["min_scaled_power"] = 5000

    now = datetime(2026, 4, 10, 17, 0, tzinfo=timezone.utc)
    discharge_windows = [
        {
            "start": datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc),
            "avg_price": 0.412,
        },
    ]

    feasible = bm_main._filter_supported_discharge_windows(
        discharge_windows,
        charge_schedule=[],
        soc=100.0,
        config=config,
        not_before=now,
        top_x_discharge_count=1,
        min_scaled_power=5000,
    )

    assert len(feasible) == 1
    assert feasible[0]["end"] - feasible[0]["start"] == timedelta(minutes=48)


# A saturated dynamic target still permits profitable selling while preserving sell_buffer_min_soc.
def test_saturated_sell_buffer_truncates_sales_at_configured_safety_floor():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 30
    config["soc"]["sell_buffer_min_soc"] = 40
    config["soc"]["sell_buffer_enabled"] = True
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_scaled_power"] = 8000

    now = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)
    window = {
        "start": now,
        "end": now + timedelta(hours=3),
        "avg_price": 0.398,
    }

    feasible = bm_main._filter_supported_discharge_windows(
        [window],
        charge_schedule=[],
        soc=100.0,
        config=config,
        not_before=now,
        top_x_discharge_count=1,
        min_scaled_power=8000,
    )

    assert len(feasible) == 1
    assert feasible[0]["start"] == now
    assert feasible[0]["end"] - feasible[0]["start"] == timedelta(minutes=112)


# Schedule the affordable portion of a profitable sell when the buffer target saturates at 100%.
def test_generate_schedule_allows_profitable_sell_when_saturated_buffer_equals_full_soc(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = True
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 30
    config["soc"]["sell_buffer_min_soc"] = 40
    config["soc"]["sell_buffer_rounding_step_pct"] = 10
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 0.25
    config["heuristics"]["top_x_discharge_hours"] = 3
    config["heuristics"]["min_profit_threshold"] = 0.08
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 0.25

    now = datetime.now(timezone.utc)
    curve_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    import_prices = [0.40] * 12 + [0.35, 0.30, 0.25, 0.10]
    export_prices = [0.60] * 12 + [0.35, 0.30, 0.25, 0.10]
    import_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: export_curve)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_args, **_kwargs: 100.0)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, _entity_id: 15.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    assert not schedule["charge"]
    assert schedule["discharge"]
    assert any(period["window_type"] == "discharge" for period in schedule["discharge"])
    sell = next(period for period in schedule["discharge"] if period["window_type"] == "discharge")
    assert sell["duration"] == 112


# Keep publish-time sell power ranks aligned with energy-feasibility calculations.
def test_generate_schedule_preserves_price_ranks_after_chronological_filtering(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 40
    config["soc"]["sell_buffer_enabled"] = False
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 1
    config["heuristics"]["top_x_discharge_hours"] = 2
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 1.0

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    curve_start = now + timedelta(hours=1)
    import_prices = [0.30, 0.31, 0.32, 0.10]
    export_prices = [0.60, 0.20, 0.90, 0.10]
    import_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: export_curve)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_args, **_kwargs: 80.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    sells = sorted(schedule["discharge"], key=lambda period: period["start"])
    assert len(sells) == 2
    assert sells[0]["power"] == 4000
    assert sells[0]["duration"] == 60
    assert sells[1]["power"] == 8000
    planned_energy_kwh = sum(
        period["power"] * period["duration"] / 60 / 1000
        for period in sells
    )
    assert planned_energy_kwh <= 10.0


def test_discharge_feasibility_price_order_does_not_starve_earlier_time_window():
    """Regression: windows sorted by price-desc must not deduct tomorrow's discharge energy
    from today's available balance.  A high-price window tomorrow (rank 1) was consuming
    the full usable kWh, leaving today's (lower-priced but earlier) window with almost
    nothing even though today's window starts before tomorrow's charge replenishes the
    battery."""
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000

    now = datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)
    # High price tomorrow (rank 1 when sorted by price desc) — starts 26 h from now
    tomorrow_window = {
        "start": datetime(2026, 5, 2, 17, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 5, 2, 21, 0, tzinfo=timezone.utc),
        "avg_price": 0.356,
    }
    # Lower price today (rank 2) — starts 2 h from now
    today_window = {
        "start": datetime(2026, 5, 1, 17, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 5, 1, 21, 0, tzinfo=timezone.utc),
        "avg_price": 0.335,
    }
    # Charge tomorrow morning — replenishes 19.5 kWh but only AFTER today's window
    tomorrow_charge = [
        {"start": datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc).isoformat(), "power": 6500, "duration": 60},
        {"start": datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc).isoformat(), "power": 6500, "duration": 60},
        {"start": datetime(2026, 5, 2, 11, 0, tzinfo=timezone.utc).isoformat(), "power": 6500, "duration": 60},
    ]

    # Pass windows in price-descending order (as the real caller does)
    discharge_windows = [tomorrow_window, today_window]

    feasible = bm_main._filter_supported_discharge_windows(
        discharge_windows,
        charge_schedule=tomorrow_charge,
        soc=97.9,
        config=config,
        not_before=now,
        top_x_discharge_count=2,
        min_scaled_power=4000,
    )

    # SOC 97.9% with 25kWh capacity, 25% floor => (97.9-25)/100*25 = 18.23 kWh usable.
    # Today's window starts BEFORE the charge, so it should get the full ~18 kWh.
    # At 8000W that supports ~136 min — the window must NOT be skipped or reduced to ~42 min.
    assert len(feasible) == 2
    today_result = next(w for w in feasible if w["start"] == today_window["start"])
    duration_today = (today_result["end"] - today_result["start"]).total_seconds() / 60
    # Expect close to full 240 min (may be truncated slightly due to floor, but well above 42)
    assert duration_today >= 120, f"Today's window was wrongly truncated to {duration_today:.0f} min"


def test_generate_schedule_uses_exact_top_discharge_hours_when_soc_supports_them(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 30
    config["soc"]["sell_buffer_enabled"] = False
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 1
    config["heuristics"]["top_x_discharge_hours"] = 2
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 1.0

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    curve_start = now + timedelta(hours=1)

    import_prices = [0.20, 0.21, 0.22, 0.23, 0.24, 0.25]
    export_prices = [0.30, 0.31, 0.41, 0.58, 0.57, 0.32]

    import_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: export_curve)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, _e: 12.0)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 99.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    discharge = schedule.get("discharge", [])
    assert len(discharge) == 1

    expected_start = curve_start + timedelta(hours=3)
    assert discharge[0]["start"] == expected_start.isoformat()
    assert discharge[0]["duration"] == 120
    assert discharge[0]["window_type"] == "discharge"


# Allow a profitable sell down to the configured reserve when precharge is costly.
def test_generate_schedule_limits_sell_to_safety_floor_when_precharge_is_too_expensive(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["soc"]["sell_buffer_min_soc"] = 40
    config["soc"]["sell_buffer_rounding_step_pct"] = 10
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 0.25
    config["heuristics"]["top_x_discharge_hours"] = 1
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 0.25

    now = datetime.now(timezone.utc)
    curve_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    import_prices = [0.40, 0.40, 0.40, 0.40, 0.10]
    export_prices = [0.50, 0.50, 0.50, 0.50, 0.20]
    import_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: export_curve)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 43.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    # 40% safety + the remaining 54 minutes at 8kW on a 25kWh battery
    # rounds to a 70% target.
    # The current price blocks precharging, but the profitable sell is still
    # scheduled and runtime SOC protection preserves the configured floor.
    assert schedule["charge"]
    assert schedule["charge"][0]["start"] == (curve_start + timedelta(hours=1)).isoformat()
    sell = next(
        period for period in schedule["discharge"]
        if period.get("window_type") == "discharge"
    )
    assert sell["duration"] == 5


# Do not let the current adaptive fallback bypass a pending sell-buffer hold.
@pytest.mark.parametrize(("soc_value", "expect_sell"), [(43.0, False), (50.0, True)])
def test_generate_schedule_respects_buffer_target_without_blocking_at_equality(
    monkeypatch,
    soc_value,
    expect_sell,
):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = True
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["soc"]["sell_buffer_min_soc"] = 40
    config["soc"]["sell_buffer_rounding_step_pct"] = 10
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 0.25
    config["heuristics"]["top_x_discharge_hours"] = 0.25
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 0.25

    now = datetime.now(timezone.utc)
    curve_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    import_prices = [0.30, 0.40, 0.35, 0.10]
    export_prices = [0.30, 0.60, 0.20, 0.10]
    import_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: export_curve)
    monkeypatch.setattr(
        bm_main,
        "_get_schedule_generation_soc",
        lambda *_args, **_kwargs: soc_value,
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, _entity_id: 15.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    assert schedule["charge"]
    assert schedule["discharge"]
    assert all(period["window_type"] == "discharge" for period in schedule["discharge"])
    if not expect_sell:
        assert schedule["charge"][0]["start"] == (curve_start + timedelta(minutes=45)).isoformat()


# Cap emergency precharge duration and fit it to provider charge-slot limits.
@pytest.mark.parametrize("max_charge_periods", [1, 3])
def test_generate_schedule_caps_precharge_at_main_charge_start(monkeypatch, max_charge_periods):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["soc"]["sell_buffer_rounding_step_pct"] = 10
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 0.25
    config["heuristics"]["top_x_discharge_hours"] = 1
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 0.25

    now = datetime.now(timezone.utc)
    curve_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    config["soc"]["sell_buffer_min_soc"] = 40
    import_prices = [0.40, 0.40, 0.40, 0.40, 0.10]
    export_prices = [0.50, 0.50, 0.50, 0.50, 0.20]
    import_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: export_curve)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 10.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)
    monkeypatch.setattr(bm_main, "_get_schedule_slot_limits", lambda *_args, **_kwargs: (max_charge_periods, 6))

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    # The requested precharge would take longer than the hour before the main
    # charge. It must end at the main charge start, not overlap it.
    assert schedule["charge"][0]["window_type"] == "precharge"
    assert schedule["charge"][0]["start"] == curve_start.isoformat()
    if max_charge_periods > 1:
        assert schedule["charge"][0]["duration"] == 60
        precharge_end = curve_start + timedelta(minutes=schedule["charge"][0]["duration"])
        assert precharge_end == curve_start + timedelta(hours=1)
        assert schedule["charge"][1]["start"] == precharge_end.isoformat()
    else:
        assert len(schedule["charge"]) == 1
        assert schedule["charge"][0]["duration"] == 75


# Prefer the adjacent main charge over a later negative slot when only one charge slot exists.
def test_single_charge_slot_coalesces_precharge_with_main_charge(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = True
    config["negative_price_charging"]["enabled"] = True
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["soc"]["sell_buffer_min_soc"] = 40
    config["soc"]["sell_buffer_rounding_step_pct"] = 10
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 0.5
    config["heuristics"]["top_x_discharge_hours"] = 0.25
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 0.25

    now = datetime.now(timezone.utc)
    curve_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    import_prices = [0.40, 0.10, -0.10, 0.20]
    export_prices = [0.60, 0.10, -0.10, 0.20]
    import_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(minutes=15 * index)).isoformat(),
            "end": (curve_start + timedelta(minutes=15 * (index + 1))).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    monkeypatch.setattr(bm_main, "_get_schedule_slot_limits", lambda *_args, **_kwargs: (1, 6))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: export_curve)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_args, **_kwargs: 10.0)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, _entity_id: 15.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    assert len(schedule["charge"]) == 1
    assert schedule["charge"][0]["window_type"] == "precharge"
    assert schedule["charge"][0]["start"] == curve_start.isoformat()
    assert schedule["charge"][0]["duration"] >= 30


# Keep new live sell periods paused when a rolling schedule is regenerated.
def test_generate_schedule_preserves_active_pause(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 25
    config["soc"]["sell_buffer_enabled"] = False
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 1
    config["heuristics"]["top_x_discharge_hours"] = 2
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 0.25

    now = datetime.now(timezone.utc)
    curve_start = now.replace(minute=0, second=0, microsecond=0)
    import_prices = [0.40, 0.35, 0.35, 0.20, 0.10]
    export_prices = [0.80, 0.20, 0.75, 0.20, 0.20]
    import_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": []},
        schedule_generated_at=now,
        schedule_pause_active=True,
    )
    published = []

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: export_curve)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, _entity_id: 15.0)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_args, **_kwargs: 99.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            published.append(deepcopy(schedule)),
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            True,
        )[-1],
    )

    generated = bm_main.generate_schedule(config, cast(Any, object()), None, state)

    assert len(generated["discharge"]) == 2
    assert published
    assert published[-1]["discharge"] == []
    assert any(
        bm_main._parse_schedule_period_bounds(period)[0] > now
        for period in generated["discharge"]
    )


# Keep the last usable recovery plan if the price feed disappears during a pause.
def test_generate_schedule_keeps_previous_plan_when_prices_are_missing(monkeypatch):
    future_period = {
        "start": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    previous_schedule = {"charge": [], "discharge": [future_period]}
    state = bm_main.RuntimeState(
        schedule=previous_schedule,
        schedule_generated_at=datetime.now(timezone.utc),
        schedule_pause_active=True,
    )

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)

    config = {
        "entities": {
            "price_curve_entity": "sensor.import",
            "export_price_curve_entity": "sensor.export",
        }
    }
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])

    generated = bm_main.generate_schedule(config, cast(Any, object()), None, state)

    assert generated == previous_schedule
    assert state.schedule == previous_schedule


def test_generate_schedule_caps_temperature_discharge_hours_at_configured_top_x(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["passive_solar"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 30
    config["soc"]["sell_buffer_enabled"] = False
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_discharge_power"] = 4000
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["top_x_charge_hours"] = 1
    config["heuristics"]["top_x_discharge_hours"] = 2
    config["heuristics"]["min_profit_threshold"] = 0.10
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["heuristics"]["adaptive_price_threshold"] = 1.0
    config["temperature_based_discharge"]["enabled"] = True
    config["temperature_based_discharge"]["thresholds"] = [
        {"temp_max": 10, "discharge_hours": 1},
        {"temp_max": 999, "discharge_hours": 3},
    ]

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    curve_start = now + timedelta(hours=1)

    import_prices = [0.20, 0.21, 0.22, 0.23, 0.24, 0.25]
    export_prices = [0.30, 0.31, 0.41, 0.58, 0.57, 0.32]

    import_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(import_prices)
    ]
    export_curve = [
        {
            "start": (curve_start + timedelta(hours=index)).isoformat(),
            "end": (curve_start + timedelta(hours=index + 1)).isoformat(),
            "price": price,
        }
        for index, price in enumerate(export_prices)
    ]

    def _sensor_value(_ha, entity_id):
        if entity_id == config["entities"]["temperature_entity"]:
            return 20.0
        return 12.0

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _e: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _e: export_curve)
    monkeypatch.setattr(bm_main, "_get_sensor_float", _sensor_value)
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *_a, **_kw: 99.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *_a, **_kw: None)

    schedule = bm_main.generate_schedule(config, cast(Any, object()), None)

    discharge = schedule.get("discharge", [])
    assert len(discharge) == 1

    expected_start = curve_start + timedelta(hours=3)
    assert discharge[0]["start"] == expected_start.isoformat()
    assert discharge[0]["duration"] == 120
    assert discharge[0]["window_type"] == "discharge"


# Verify live regeneration respects EV protection while recovering adaptive gaps.
@pytest.mark.parametrize(("ev_power", "expect_regen"), [(0.0, True), (700.0, False)])
def test_monitor_regenerates_schedule_for_live_adaptive_gap(monkeypatch, ev_power, expect_regen):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["timing"]["schedule_regen_cooldown_seconds"] = 0
    config["power"]["min_discharge_power"] = 4000

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    future_period = {
        "start": (now + timedelta(hours=6)).isoformat(),
        "duration": 60,
        "power": 8000,
        "window_type": "discharge",
    }
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": [future_period]},
        published_schedule={"charge": [], "discharge": [future_period]},
        schedule_generated_at=now - timedelta(minutes=10),
        last_schedule_publish=now - timedelta(minutes=10),
    )

    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.30,
    }
    regenerated_schedule = {
        "charge": [],
        "discharge": [
            {
                "start": now.isoformat(),
                "duration": 60,
                "power": 0,
                "window_type": "adaptive",
            }
        ],
    }
    sensor_values = {
        config["entities"]["soc_entity"]: 65.0,
        config["entities"]["grid_power_entity"]: 120.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 350.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: ev_power,
        config["entities"]["temperature_entity"]: 12.0,
    }

    regen_calls = []
    published = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "adaptive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            published.append(deepcopy(schedule)),
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            True,
        )[-1],
    )
    monkeypatch.setattr(
        bm_main,
        "generate_schedule",
        lambda *_args, **_kwargs: (regen_calls.append(True), regenerated_schedule)[1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    if expect_regen:
        assert regen_calls, "Expected adaptive gap to trigger schedule regeneration"
        assert state.schedule == regenerated_schedule
        assert state.schedule_generated_at is not None
        assert state.last_schedule_publish is not None
    else:
        assert not regen_calls, "EV protection must prevent schedule regeneration from publishing discharge"
        assert state.schedule == {"charge": [], "discharge": [future_period]}
        assert published
        assert published[-1]["discharge"] == []


def test_monitor_uses_today_only_range_curves(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    local_now = now.astimezone()
    today_start = local_now.replace(hour=6)
    tomorrow_start = (local_now + timedelta(days=1)).replace(hour=1)

    import_curve = [
        {
            "start": today_start.isoformat(),
            "end": (today_start + timedelta(hours=1)).isoformat(),
            "price": 0.21,
        },
        {
            "start": (today_start + timedelta(hours=1)).isoformat(),
            "end": (today_start + timedelta(hours=2)).isoformat(),
            "price": 0.22,
        },
        {
            "start": tomorrow_start.isoformat(),
            "end": (tomorrow_start + timedelta(hours=1)).isoformat(),
            "price": 0.08,
        },
    ]
    export_curve = [
        {
            "start": today_start.isoformat(),
            "end": (today_start + timedelta(hours=1)).isoformat(),
            "price": 0.31,
        },
        {
            "start": (today_start + timedelta(hours=1)).isoformat(),
            "end": (today_start + timedelta(hours=2)).isoformat(),
            "price": 0.32,
        },
        {
            "start": tomorrow_start.isoformat(),
            "end": (tomorrow_start + timedelta(hours=1)).isoformat(),
            "price": 0.45,
        },
    ]
    current_entry = import_curve[0]
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": []},
        published_schedule={"charge": [], "discharge": []},
        schedule_generated_at=now,
        last_price_range="passive",
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 55.0,
        config["entities"]["grid_power_entity"]: 0.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 250.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 11.0,
    }

    captured_ranges = {}

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: import_curve)
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: export_curve)
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)

    def _capture_ranges(import_prices, export_prices, *_args, **_kwargs):
        captured_ranges["import"] = [entry["price"] for entry in import_prices]
        captured_ranges["export"] = [entry["price"] for entry in export_prices]
        return None, None, None

    monkeypatch.setattr(bm_main, "calculate_price_ranges", _capture_ranges)
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "passive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: True)

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert captured_ranges["import"] == [0.21, 0.22]
    assert captured_ranges["export"] == [0.31, 0.32]


def test_generate_schedule_inserts_current_adaptive_window_when_missing(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["heuristics"]["adaptive_price_threshold"] = 0.27
    config["power"]["min_discharge_power"] = 0
    config["solar_aware_charging"]["enabled"] = False

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.30,
    }
    future_charge_window = {
        "start": now + timedelta(hours=2),
        "end": now + timedelta(hours=3),
        "avg_price": 0.21,
    }
    future_discharge_window = {
        "start": now + timedelta(hours=7),
        "end": now + timedelta(hours=8),
        "avg_price": 0.39,
    }

    published = []

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "adaptive")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [future_charge_window],
            "discharge": [future_discharge_window],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (50.0, 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append(schedule),
            True,
        )[-1],
    )

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert published, "Expected schedule publish"
    active_adaptive = [
        period for period in schedule["discharge"]
        if period["window_type"] == "adaptive" and bm_main._is_period_active(period, now)
    ]
    assert active_adaptive, "Expected current adaptive interval to be published when price band is adaptive"
    assert active_adaptive[0]["start"] == now.isoformat()


def test_generate_schedule_downgrades_current_discharge_band_to_adaptive_below_conservative(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 25
    config["soc"]["min_soc"] = 5
    config["heuristics"]["adaptive_price_threshold"] = 0.27
    config["power"]["min_discharge_power"] = 0
    config["solar_aware_charging"]["enabled"] = False

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.30,
    }
    future_charge_window = {
        "start": now + timedelta(hours=12),
        "end": now + timedelta(hours=13),
        "avg_price": 0.12,
    }
    future_discharge_window = {
        "start": now + timedelta(hours=20),
        "end": now + timedelta(hours=21),
        "avg_price": 0.39,
    }

    published = []

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [future_charge_window],
            "discharge": [future_discharge_window],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (23.7, 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append(schedule),
            True,
        )[-1],
    )

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert published, "Expected schedule publish"
    active_adaptive = [
        period for period in schedule["discharge"]
        if period["window_type"] == "adaptive" and bm_main._is_period_active(period, now)
    ]
    assert active_adaptive, (
        "Expected current adaptive interval when SOC is below conservative_soc "
        "but above min_soc and the raw price band is discharge"
    )
    assert active_adaptive[0]["start"] == now.isoformat()


def test_generate_schedule_uses_planned_schedule_for_entity_display(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["temperature_based_discharge"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["ev_charger"]["enabled"] = False

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.24,
    }
    charge_window = {
        "start": now + timedelta(hours=1),
        "end": now + timedelta(hours=2),
        "avg_price": 0.18,
    }
    discharge_today = {
        "start": now + timedelta(hours=3),
        "end": now + timedelta(hours=4),
        "avg_price": 0.42,
    }
    discharge_tomorrow = {
        "start": now + timedelta(days=1, hours=3),
        "end": now + timedelta(days=1, hours=4),
        "avg_price": 0.35,
    }

    entity_updates = []
    fake_mqtt = _FakeMqttClient()

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "passive")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [charge_window],
            "discharge": [discharge_today, discharge_tomorrow],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float",
        lambda _ha, entity_id: {
            config["entities"]["grid_power_entity"]: 0.0,
            config["entities"]["solar_power_entity"]: 0.0,
            config["entities"]["house_load_entity"]: 250.0,
            config["entities"]["battery_power_entity"]: 0.0,
            config["entities"]["temperature_entity"]: 15.0,
        }.get(entity_id),
    )
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (87.0, 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=fake_mqtt, state=state)

    assert len(schedule["discharge"]) == 2
    assert fake_mqtt.published, "Expected schedule publish"
    assert state.published_schedule is not None
    assert len(state.published_schedule["discharge"]) == 2

    published_payload = fake_mqtt.published[-1]["payload"]
    assert len(published_payload["charge"]) == 1
    assert len(published_payload["discharge"]) == 1

    schedule_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_SCHEDULE]
    assert schedule_updates, "Expected combined schedule entity update"
    schedule_markdown = schedule_updates[-1][0][3]["markdown"]
    assert "**Tomorrow**" in schedule_markdown
    assert schedule_markdown.count("💰 Discharge") == 2
    assert schedule_markdown.count("⚡ Charge") == 1
    assert "€0.420" in schedule_markdown
    assert "€0.350" in schedule_markdown


def test_generate_schedule_skips_unsupported_future_discharge_without_charge(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["temperature_based_discharge"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 10
    config["soc"]["min_soc"] = 20
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_scaled_power"] = 8000

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.24,
    }
    future_discharge_window = {
        "start": now + timedelta(hours=4),
        "end": now + timedelta(hours=5),
        "avg_price": 0.42,
    }

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "passive")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [],
            "discharge": [future_discharge_window],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float",
        lambda _ha, entity_id: 25.0 if entity_id == config["entities"]["soc_entity"] else None,
    )
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (25.0, 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: True)

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert schedule["discharge"] == []


def test_schedule_slot_limits_follow_battery_api_capabilities():
    config = deepcopy(bm_main.DEFAULT_CONFIG)

    class _FakeHaApi:
        def get_entity_state(self, entity_id):
            assert entity_id == config["entities"]["battery_api_status_entity"]
            return {
                "state": "Connected",
                "attributes": {
                    "capabilities": {
                        "max_charge_periods": 7,
                        "max_discharge_periods": 7,
                    }
                },
            }

    assert bm_main._get_schedule_slot_limits(_FakeHaApi(), config) == (7, 7)


def test_schedule_slot_limits_fallback_without_battery_api_status():
    config = deepcopy(bm_main.DEFAULT_CONFIG)

    assert bm_main._get_schedule_slot_limits(cast(Any, object()), config) == (
        bm_main.MAX_CHARGE_PERIODS,
        bm_main.MAX_DISCHARGE_PERIODS,
    )


def test_generate_schedule_keeps_future_discharge_when_charge_supports_it(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["temperature_based_discharge"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 10
    config["soc"]["min_soc"] = 20
    config["power"]["max_charge_power"] = 8000
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_scaled_power"] = 8000

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.24,
    }
    future_charge_window = {
        "start": now + timedelta(hours=1),
        "end": now + timedelta(hours=2),
        "avg_price": 0.18,
    }
    future_discharge_window = {
        "start": now + timedelta(hours=3),
        "end": now + timedelta(hours=4),
        "avg_price": 0.42,
    }

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "passive")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [future_charge_window],
            "discharge": [future_discharge_window],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float",
        lambda _ha, entity_id: 25.0 if entity_id == config["entities"]["soc_entity"] else None,
    )
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (25.0, 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: True)

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert len(schedule["charge"]) == 1
    assert len(schedule["discharge"]) == 1


def test_generate_schedule_keeps_future_discharge_when_schedule_soc_is_stale(monkeypatch, caplog):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["temperature_based_discharge"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["soc"]["battery_capacity_kwh"] = 10
    config["soc"]["min_soc"] = 20
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_scaled_power"] = 8000

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.24,
    }
    future_discharge_window = {
        "start": now + timedelta(hours=4),
        "end": now + timedelta(hours=5),
        "avg_price": 0.42,
    }

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "passive")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [],
            "discharge": [future_discharge_window],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (25.0, float(config["timing"]["max_soc_sensor_age_seconds"] + 1))
            if entity_id == config["entities"]["soc_entity"]
            else (None, None)
        ),
    )
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: True)

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)

    with caplog.at_level(logging.WARNING):
        schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert len(schedule["discharge"]) == 1
    assert "skipping discharge feasibility pruning" in caplog.text


def test_supported_discharge_skip_log_includes_energy_budget_breakdown(caplog):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 25
    config["soc"]["min_soc"] = 5
    config["power"]["max_discharge_power"] = 8000
    config["power"]["min_scaled_power"] = 4000

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    charge_schedule = [
        {
            "start": (now + timedelta(hours=1)).isoformat(),
            "duration": 60,
            "power": 5000,
        },
        {
            "start": (now + timedelta(hours=2)).isoformat(),
            "duration": 60,
            "power": 5000,
        },
    ]
    discharge_windows = [
        {
            "start": now + timedelta(hours=6),
            "end": now + timedelta(hours=8),
            "avg_price": 0.355,
        },
        {
            "start": now + timedelta(hours=17),
            "end": now + timedelta(hours=18),
            "avg_price": 0.350,
        },
        {
            "start": now + timedelta(hours=19),
            "end": now + timedelta(hours=22, minutes=45),
            "avg_price": 0.320,
        },
    ]

    with caplog.at_level(logging.INFO):
        feasible = bm_main._filter_supported_discharge_windows(
            discharge_windows,
            charge_schedule,
            soc=100.0,
            config=config,
            not_before=now,
            top_x_discharge_count=3,
            min_scaled_power=4000,
        )

    assert len(feasible) == 3
    skip_message = next(
        record.getMessage()
        for record in caplog.records
        if "Truncating discharge window" in record.getMessage()
    )
    assert "to 45m" in skip_message
    assert "needs 15.00kWh" in skip_message
    assert "only 3.00kWh available before start" in skip_message
    assert "SOC 100.0% => 15.00kWh usable above 40.0% reserve floor" in skip_message
    assert "min 5.0%, conservative 40.0%" in skip_message
    assert "scheduled charge +10.00kWh" in skip_message
    assert "earlier discharge -22.00kWh" in skip_message
    assert feasible[2]["end"] - feasible[2]["start"] == timedelta(minutes=45)


def test_generate_schedule_scales_charge_power_per_slot(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["heuristics"]["adaptive_price_threshold"] = 0.27
    config["heuristics"]["top_x_charge_hours"] = 3
    config["power"]["max_charge_power"] = 8000
    config["power"]["min_scaled_power"] = 4000
    config["power"]["min_discharge_power"] = 0
    config["solar_aware_charging"]["enabled"] = False

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.21,
    }
    grouped_charge_window = {
        "start": now,
        "end": now + timedelta(hours=3),
        "avg_price": 0.20,
        "slots": [
            {"start": now, "end": now + timedelta(hours=1), "price": 0.21},
            {"start": now + timedelta(hours=1), "end": now + timedelta(hours=2), "price": 0.20},
            {"start": now + timedelta(hours=2), "end": now + timedelta(hours=3), "price": 0.19},
        ],
    }

    published = []

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda hours, _interval: int(hours))
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "load")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [grouped_charge_window],
            "discharge": [],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (50.0, 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append(schedule),
            True,
        )[-1],
    )

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert published, "Expected schedule publish"
    assert len(schedule["charge"]) == 1
    assert schedule["charge"][0]["power"] == 8000
    assert schedule["charge"][0]["duration"] == 180


def test_generate_schedule_reduces_charge_power_with_remaining_solar(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["heuristics"]["adaptive_price_threshold"] = 0.27
    config["heuristics"]["top_x_charge_hours"] = 3
    config["power"]["max_charge_power"] = 8000
    config["power"]["min_scaled_power"] = 4000
    config["power"]["min_discharge_power"] = 0
    config["soc"]["max_soc"] = 100
    config["soc"]["battery_capacity_kwh"] = 12
    config["solar_aware_charging"]["enabled"] = True
    config["solar_aware_charging"]["forecast_safety_factor"] = 1.0
    config["solar_aware_charging"]["min_charge_power"] = 500

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.21,
    }
    grouped_charge_window = {
        "start": now,
        "end": now + timedelta(hours=3),
        "avg_price": 0.20,
        "slots": [
            {"start": now, "end": now + timedelta(hours=1), "price": 0.21},
            {"start": now + timedelta(hours=1), "end": now + timedelta(hours=2), "price": 0.20},
            {"start": now + timedelta(hours=2), "end": now + timedelta(hours=3), "price": 0.19},
        ],
    }

    published = []
    sensor_values = {
        config["entities"]["soc_entity"]: 50.0,
    }

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda hours, _interval: int(hours))
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "load")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [grouped_charge_window],
            "discharge": [],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (sensor_values[entity_id], 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(
        bm_main,
        "_get_entity_state",
        lambda _ha, entity_id: (
            {
                "state": "3000",
                "attributes": {"unit_of_measurement": "W"},
            }
            if entity_id == config["entities"]["remaining_solar_energy_entity"]
            else None
        ),
    )
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append(schedule),
            True,
        )[-1],
    )

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert published, "Expected schedule publish"
    assert len(schedule["charge"]) == 1
    assert schedule["charge"][0]["power"] == 1000
    assert schedule["charge"][0]["solar_aware"] is True


def test_generate_schedule_spreads_charge_power_across_nearly_equal_cheap_hours(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["heuristics"]["adaptive_price_threshold"] = 0.27
    config["heuristics"]["top_x_charge_hours"] = 3
    config["heuristics"]["charge_spread_enabled"] = True
    config["heuristics"]["charge_spread_max_price_delta"] = 0.02
    config["power"]["max_charge_power"] = 8000
    config["power"]["min_scaled_power"] = 4000
    config["power"]["min_discharge_power"] = 0
    config["soc"]["max_soc"] = 100
    config["soc"]["battery_capacity_kwh"] = 48
    config["solar_aware_charging"]["enabled"] = False
    config["solar_aware_charging"]["min_charge_power"] = 500

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.13,
    }
    grouped_charge_window = {
        "start": now,
        "end": now + timedelta(hours=6),
        "avg_price": 0.14,
        "slots": [
            {"start": now + timedelta(hours=index), "end": now + timedelta(hours=index + 1), "price": price}
            for index, price in enumerate((0.13, 0.13, 0.14, 0.14, 0.15, 0.15))
        ],
    }

    published = []
    sensor_values = {
        config["entities"]["soc_entity"]: 50.0,
    }

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda hours, _interval: int(hours))
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "find_profitable_discharge_starts", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(bm_main, "find_top_x_charge_starts", lambda *_args, **_kwargs: {current_entry["start"]})
    monkeypatch.setattr(
        bm_main,
        "expand_charge_starts_within_price_delta",
        lambda *_args, **_kwargs: {slot["start"].isoformat() for slot in grouped_charge_window["slots"]},
    )
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "load")
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(
        bm_main,
        "find_upcoming_windows",
        lambda *_args, **_kwargs: {
            "charge": [grouped_charge_window],
            "discharge": [],
            "adaptive": [],
        },
    )
    monkeypatch.setattr(bm_main, "_calculate_dynamic_sell_buffer_soc", lambda *_args, **_kwargs: (None, 0.0, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_tomorrow_story", lambda *_args, **_kwargs: "forecast")
    monkeypatch.setattr(bm_main, "build_windows_display", lambda *_args, **_kwargs: "windows")
    monkeypatch.setattr(bm_main, "build_combined_schedule_display", lambda *_args, **_kwargs: "combined")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (
            (sensor_values[entity_id], 0.0) if entity_id == config["entities"]["soc_entity"] else (None, None)
        ),
    )
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append(schedule),
            True,
        )[-1],
    )

    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=now)
    schedule = bm_main.generate_schedule(config, ha_api=cast(Any, object()), mqtt_client=None, state=state)

    assert published, "Expected schedule publish"
    assert len(schedule["charge"]) == 1
    assert schedule["charge"][0]["duration"] == 360
    assert schedule["charge"][0]["power"] == 4000


def test_active_discharge_pauses_when_soc_unavailable(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 40
    config["soc"]["min_soc"] = 5

    now = datetime.now(timezone.utc)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [],
            "discharge": [
                {
                    "start": (now - timedelta(minutes=10)).isoformat(),
                    "duration": 60,
                    "power": 6000,
                    "window_type": "discharge",
                }
            ],
        },
        schedule_generated_at=now,
    )

    sensor_values = {
        config["entities"]["grid_power_entity"]: 100.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 120.0,
        config["entities"]["battery_power_entity"]: 100.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 13.0,
    }

    published = []
    entity_updates = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, _entity_id, _now: (None, None),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append((schedule, force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert published, "Expected protective pause override schedule to be published"
    override_schedule = published[-1][0]
    assert override_schedule["discharge"] == []


def test_active_passive_gap_keeps_passive_solar_mode(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)

    now = datetime.now(timezone.utc)
    passive_gap_schedule = {
        "charge": [
            {
                "start": (now - timedelta(minutes=2)).isoformat(),
                "duration": 1,
                "power": 0,
            }
        ],
        "discharge": [
            {
                "start": (now - timedelta(minutes=1)).isoformat(),
                "duration": 2,
                "power": 4000,
                "window_type": "passive_gap",
            }
        ],
    }
    state = bm_main.RuntimeState(
        schedule=deepcopy(passive_gap_schedule),
        published_schedule=deepcopy(passive_gap_schedule),
        schedule_generated_at=now,
        passive_gap_active=True,
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 55.0,
        config["entities"]["grid_power_entity"]: -1400.0,
        config["entities"]["solar_power_entity"]: 2400.0,
        config["entities"]["house_load_entity"]: 200.0,
        config["entities"]["battery_power_entity"]: 6000.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 13.0,
    }

    published = []
    entity_updates = []

    class _PassiveSolarMonitorStub:
        def __init__(self):
            self.calls = 0

        def check_passive_state(self, _ha_api):
            self.calls += 1
            return True

    class _PassiveGapSchedulerStub:
        def __init__(self):
            self.calls = 0

        def generate_passive_gap_schedule(self):
            self.calls += 1
            return {"charge": [{"start": now.isoformat(), "duration": 1, "power": 0}], "discharge": []}

    solar_monitor = _PassiveSolarMonitorStub()
    gap_scheduler = _PassiveGapSchedulerStub()

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: published.append(_args[1]) or True)

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=solar_monitor,
        gap_scheduler=gap_scheduler,
    )

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    assert mode_updates[-1][0][2] == "passive_solar"
    assert not published
    assert gap_scheduler.calls == 0
    assert state.passive_gap_active is True


# A saturated target allows selling above the configured floor and pauses at that floor.
@pytest.mark.parametrize(("soc", "expect_pause"), [(100.0, False), (40.0, True), (39.0, True)])
def test_active_discharge_respects_safety_floor_with_saturated_sell_buffer(monkeypatch, soc, expect_pause):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 30
    config["soc"]["min_soc"] = 5
    config["soc"]["sell_buffer_min_soc"] = 40
    config["timing"]["max_ev_sensor_age_seconds"] = 180

    now = datetime.now(timezone.utc)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [],
            "discharge": [
                {
                    "start": (now - timedelta(minutes=10)).isoformat(),
                    "duration": 60,
                    "power": 6000,
                    "window_type": "discharge",
                }
            ],
        },
        schedule_generated_at=now,
        sell_buffer_required_soc=100.0,
        sell_buffer_valid_until=now + timedelta(hours=2),
    )

    sensor_values = {
        config["entities"]["soc_entity"]: soc,
        config["entities"]["grid_power_entity"]: 100.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 120.0,
        config["entities"]["battery_power_entity"]: 100.0,
        config["ev_charger"]["entity_id"]: 3200.0,
        config["entities"]["temperature_entity"]: 13.0,
    }

    published = []
    entity_updates = []

    def fake_sensor_with_age(_ha, entity_id, _now):
        if entity_id == config["ev_charger"]["entity_id"]:
            return sensor_values.get(entity_id), 600.0
        return sensor_values.get(entity_id), 0.0

    monkeypatch.setattr(bm_main, "_get_sensor_float_and_age_seconds", fake_sensor_with_age)
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "discharge")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append((schedule, force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    if expect_pause:
        assert published
        assert published[-1][0]["discharge"] == []
    else:
        assert not published, "A saturated planned target must not stop selling above the safety floor"

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    assert mode_updates[-1][0][2] == ("paused" if expect_pause else "discharge")


def test_max_soc_stabilizer_starts_5_minute_half_power_discharge(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["max_soc"] = 97
    config["power"]["max_discharge_power"] = 8000

    now = datetime.now(timezone.utc)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [
                {
                    "start": (now - timedelta(minutes=5)).isoformat(),
                    "duration": 30,
                    "power": 8000,
                    "window_type": "charge",
                }
            ],
            "discharge": [],
        },
        schedule_generated_at=now,
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 97.0,
        config["entities"]["grid_power_entity"]: 0.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 200.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 14.0,
    }

    published = []
    entity_updates = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append((schedule, force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert published, "Expected max-SOC stabilizer override schedule to be published"
    override_schedule = published[-1][0]
    assert override_schedule["charge"] == []
    assert len(override_schedule["discharge"]) == 1
    assert override_schedule["discharge"][0]["power"] == 4000
    assert override_schedule["discharge"][0]["duration"] == 5
    assert override_schedule["discharge"][0]["window_type"] == "max_soc_stabilizer"
    assert state.last_effective_discharge_power == 4000
    assert state.max_soc_stabilizer_until is not None
    assert state.published_schedule == override_schedule

    last_power_updates = [
        call for call in entity_updates
        if call[0][1] == bm_main.ENTITY_EFFECTIVE_DISCHARGE_POWER
    ]
    assert last_power_updates
    assert last_power_updates[-1][0][2] == "4000"


# Retry restoration of the generated plan even after the stabilizer deadline passes.
def test_max_soc_stabilizer_clears_below_hysteresis_floor(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["max_soc"] = 97

    now = datetime.now(timezone.utc)
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": []},
        schedule_generated_at=now,
        max_soc_stabilizer_until=now + timedelta(minutes=4),
        last_effective_discharge_power=4000,
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 95.5,
        config["entities"]["grid_power_entity"]: 0.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 200.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 14.0,
    }

    published = []
    publish_results = [False, True]
    entity_updates = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            published.append((schedule, force)),
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None and publish_results[0] else None,
            publish_results.pop(0),
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )
    assert state.max_soc_stabilizer_restore_pending
    state.max_soc_stabilizer_until = now - timedelta(seconds=1)
    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert published, "Expected generated schedule to be restored after stabilizer clears"
    assert len(published) == 2
    assert published[-1][0] == state.schedule
    assert state.max_soc_stabilizer_until is None
    assert not state.max_soc_stabilizer_restore_pending
    assert state.last_effective_discharge_power is None


def test_max_soc_stabilizer_overrides_passive_solar_and_resumes_gap(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["max_soc"] = 97
    config["power"]["max_discharge_power"] = 8000

    now = datetime.now(timezone.utc)
    passive_gap_schedule = {
        "charge": [{"start": (now + timedelta(minutes=1)).isoformat(), "duration": 1, "power": 0}],
        "discharge": [
            {
                "start": (now + timedelta(minutes=2)).isoformat(),
                "duration": 1,
                "power": 4000,
                "window_type": "passive_gap",
            }
        ],
    }
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": []},
        schedule_generated_at=now,
        published_schedule=deepcopy(passive_gap_schedule),
        passive_gap_active=True,
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 97.0,
        config["entities"]["grid_power_entity"]: -1500.0,
        config["entities"]["solar_power_entity"]: 2500.0,
        config["entities"]["house_load_entity"]: 200.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 14.0,
    }

    published = []
    entity_updates = []

    class _PassiveSolarMonitorStub:
        def check_passive_state(self, _ha_api):
            return True

    class _PassiveGapSchedulerStub:
        def generate_passive_gap_schedule(self):
            return deepcopy(passive_gap_schedule)

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append((deepcopy(schedule), force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _PassiveSolarMonitorStub()),
        gap_scheduler=cast(Any, _PassiveGapSchedulerStub()),
    )

    assert published, "Expected max-SOC stabilizer to override passive solar"
    override_schedule = published[-1][0]
    assert override_schedule["charge"] == []
    assert override_schedule["discharge"][0]["window_type"] == "max_soc_stabilizer"
    assert override_schedule["discharge"][0]["power"] == 4000
    assert override_schedule["discharge"][0]["duration"] == 5
    assert state.max_soc_stabilizer_until is not None
    assert state.passive_gap_active is False

    sensor_values[config["entities"]["soc_entity"]] = 95.5

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _PassiveSolarMonitorStub()),
        gap_scheduler=cast(Any, _PassiveGapSchedulerStub()),
    )

    assert len(published) >= 3
    assert published[-1][0] == passive_gap_schedule
    assert state.max_soc_stabilizer_until is None
    assert state.passive_gap_active is True


def test_adaptive_regen_triggers_when_soc_below_conservative(monkeypatch):
    """Regression: SOC below conservative_soc but above min_soc must still trigger
    adaptive schedule regeneration when price is in the adaptive band.

    Before the fix _should_regenerate_live_schedule used is_conservative=True, so
    it returned None (no regen) and the monitor settled on idle instead of starting
    adaptive discharge.
    """
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 25
    config["soc"]["min_soc"] = 5
    config["timing"]["schedule_regen_cooldown_seconds"] = 0

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    # No active discharge period in the current schedule
    state = bm_main.RuntimeState(
        schedule={"charge": [], "discharge": []},
        published_schedule={"charge": [], "discharge": []},
        schedule_generated_at=now - timedelta(minutes=10),
        last_schedule_publish=now - timedelta(minutes=10),
    )

    current_entry = {
        "start": now.isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
        "price": 0.30,
    }
    regenerated_schedule = {
        "charge": [],
        "discharge": [
            {
                "start": now.isoformat(),
                "duration": 60,
                "power": 0,
                "window_type": "adaptive",
            }
        ],
    }
    # SOC is 24% — below conservative_soc (25%) but above min_soc (5%)
    sensor_values = {
        config["entities"]["soc_entity"]: 24.0,
        config["entities"]["grid_power_entity"]: 300.0,
        config["entities"]["solar_power_entity"]: 0.0,
        config["entities"]["house_load_entity"]: 350.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: 0.0,
        config["entities"]["temperature_entity"]: 12.0,
    }

    regen_calls = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [current_entry])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(
        bm_main,
        "get_current_price_entry",
        lambda _curve, _now, _interval: current_entry,
    )
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "adaptive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bm_main, "_publish_schedule", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        bm_main,
        "generate_schedule",
        lambda *_args, **_kwargs: (regen_calls.append(True), regenerated_schedule)[1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(Any, _SolarMonitorStub()),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    assert regen_calls, (
        "Expected adaptive schedule regeneration when SOC is below conservative_soc "
        "but above min_soc during adaptive price band"
    )


# Enforce dynamic reserve protection without blocking adaptive operation above it.
@pytest.mark.parametrize(
    (
        "sell_buffer_required_soc",
        "ev_power",
        "passive_solar_active",
        "passive_gap_active",
        "expect_adaptive",
        "expect_pause_publish",
        "soc_value",
    ),
    [
        (10.0, 0.0, False, False, True, False, 17.0),
        (30.0, 0.0, False, False, False, True, 17.0),
        (10.0, 700.0, False, False, False, True, 17.0),
        (10.0, 700.0, True, False, False, True, 17.0),
        (10.0, 700.0, True, True, False, True, 17.0),
        (10.0, 0.0, True, False, False, True, None),
        (10.0, 0.0, True, True, False, True, None),
    ],
)
def test_zero_power_adaptive_placeholder_respects_sell_buffer(
    monkeypatch,
    sell_buffer_required_soc,
    ev_power,
    passive_solar_active,
    passive_gap_active,
    expect_adaptive,
    expect_pause_publish,
    soc_value,
):
    """Regression: active 0W adaptive placeholder must trigger adaptive power control
    even when SOC is below conservative_soc.

    A placeholder may start grid-following below conservative_soc when the dynamic
    sell-buffer target is already met, but it must stay idle when doing so would
    consume the reserve needed before the next main charge.
    """
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 40
    config["soc"]["min_soc"] = 5
    config["power"]["min_discharge_power"] = 0
    config["power"]["max_discharge_power"] = 8000
    config["timing"]["adaptive_power_grace_seconds"] = 60

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    state = bm_main.RuntimeState(
        schedule={
            "charge": [
                {
                    "start": (now + timedelta(hours=2)).isoformat(),
                    "duration": 240,
                    "power": 8000,
                    "window_type": "charge",
                }
            ],
            "discharge": [
                {
                    "start": (now - timedelta(minutes=10)).isoformat(),
                    "duration": 60,
                    "power": 0,
                    "window_type": "adaptive",
                },
                {
                    "start": (now + timedelta(hours=10)).isoformat(),
                    "duration": 120,
                    "power": 8000,
                    "window_type": "discharge",
                },
            ],
        },
        schedule_generated_at=now,
        sell_buffer_required_soc=sell_buffer_required_soc,
        passive_gap_active=passive_gap_active,
    )
    if passive_gap_active:
        state.published_schedule = {
            "charge": [],
            "discharge": [
                {
                    "start": (now + timedelta(minutes=2)).strftime("%H:%M"),
                    "duration": 1,
                    "power": 4000,
                    "window_type": "passive_gap",
                }
            ],
        }

    sensor_values = {
        config["entities"]["soc_entity"]: soc_value,
        config["entities"]["grid_power_entity"]: 200.0,  # Importing 200W
        config["entities"]["solar_power_entity"]: 300.0,
        config["entities"]["house_load_entity"]: 400.0,
        config["entities"]["battery_power_entity"]: 0.0,
        config["ev_charger"]["entity_id"]: ev_power,
        config["entities"]["temperature_entity"]: 17.0,
    }

    entity_updates = []
    published = []

    monkeypatch.setattr(
        bm_main,
        "_get_sensor_float_and_age_seconds",
        lambda _ha, entity_id, _now: (sensor_values.get(entity_id), 0.0),
    )
    monkeypatch.setattr(bm_main, "_get_sensor_float", lambda _ha, entity_id: sensor_values.get(entity_id))
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda _ha, _entity_id: [])
    monkeypatch.setattr(bm_main, "detect_interval_minutes", lambda _curve: 60)
    monkeypatch.setattr(bm_main, "calculate_top_x_count", lambda _hours, _interval: 1)
    monkeypatch.setattr(bm_main, "calculate_price_ranges", lambda *_args, **_kwargs: (None, None, None))
    monkeypatch.setattr(bm_main, "_determine_price_range", lambda *_args, **_kwargs: "adaptive")
    monkeypatch.setattr(bm_main, "build_today_story", lambda *_args, **_kwargs: "story")
    monkeypatch.setattr(bm_main, "build_status_message", lambda *_args, **_kwargs: "status")
    monkeypatch.setattr(bm_main, "update_entity", lambda *_args, **_kwargs: entity_updates.append((_args, _kwargs)))
    monkeypatch.setattr(
        bm_main,
        "_publish_schedule",
        lambda _mqtt, schedule, _dry_run, state=None, force=False: (
            setattr(state, "published_schedule", deepcopy(schedule)) if state is not None else None,
            published.append((deepcopy(schedule), force)),
            True,
        )[-1],
    )

    bm_main.monitor_and_adjust_active_period(
        config,
        ha_api=cast(Any, object()),
        mqtt_client=None,
        state=state,
        solar_monitor=cast(
            Any,
            _ActiveSolarMonitorStub() if passive_solar_active else _SolarMonitorStub(),
        ),
        gap_scheduler=cast(Any, _GapSchedulerStub()),
    )

    if expect_adaptive:
        assert published, "Expected adaptive power control after the sell buffer was met"
        active_period = published[-1][0]["discharge"][0]
        assert active_period["window_type"] == "adaptive"
        assert active_period["power"] > 0, (
            f"Expected adaptive power > 0W for grid=200W, got {active_period['power']}W"
        )
    elif expect_pause_publish:
        assert published
        assert published[-1][0]["discharge"] == []
    else:
        assert not published, "A protected adaptive placeholder must not publish discharge"

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    expected_mode = "adaptive" if expect_adaptive else (
        "paused" if expect_pause_publish and not passive_gap_active else "idle"
    )
    assert mode_updates[-1][0][2] == expected_mode

    if expect_adaptive:
        # Future discharge window must not be cleared by the adaptive override.
        assert any(
            p.get("window_type") == "discharge" and p.get("power") == 8000
            for p in published[-1][0]["discharge"]
        ), "Future discharge window must be preserved in the published schedule"
