"""Regression tests for reduced-mode adaptive behavior in main loop."""

import os
import sys
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from typing import Any, cast

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import main as bm_main


class _SolarMonitorStub:
    def check_passive_state(self, _ha_api):
        return False


class _GapSchedulerStub:
    def generate_passive_gap_schedule(self):
        return {"charge": [], "discharge": []}


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

    assert published, "Expected generated schedule to be restored after stabilizer clears"
    assert published[-1][0] == state.schedule
    assert state.max_soc_stabilizer_until is None
    assert state.last_effective_discharge_power == 0

    last_power_updates = [
        call for call in entity_updates
        if call[0][1] == bm_main.ENTITY_EFFECTIVE_DISCHARGE_POWER
    ]
    assert last_power_updates
    assert last_power_updates[-1][0][2] == "0"
    assert last_power_updates[-1][0][3]["active_window_type"] == "none"
