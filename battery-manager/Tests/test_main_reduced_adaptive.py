"""Regression tests for reduced-mode adaptive behavior in main loop."""

import logging
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


def test_discharge_feasibility_keeps_one_hour_when_only_ten_kwh_available():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 20
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 5
    config["soc"]["target_eod_soc"] = 5
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

    assert feasible == [discharge_windows[0]]


def test_discharge_feasibility_respects_conservative_soc_floor():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 10
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 40
    config["soc"]["target_eod_soc"] = 20
    config["power"]["max_discharge_power"] = 7000
    config["power"]["min_scaled_power"] = 7000

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
        min_scaled_power=7000,
    )

    assert feasible == []


def test_discharge_feasibility_respects_target_eod_soc_floor():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["battery_capacity_kwh"] = 10
    config["soc"]["min_soc"] = 5
    config["soc"]["conservative_soc"] = 20
    config["soc"]["target_eod_soc"] = 60
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

    assert feasible == []


def test_monitor_regenerates_schedule_for_live_adaptive_gap(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["timing"]["schedule_regen_cooldown_seconds"] = 0

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

    assert regen_calls, "Expected adaptive gap to trigger schedule regeneration"
    assert state.schedule == regenerated_schedule
    assert state.schedule_generated_at is not None
    assert state.last_schedule_publish is not None


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

    assert len(feasible) == 2
    skip_message = next(
        record.getMessage()
        for record in caplog.records
        if "Skipping discharge window" in record.getMessage()
    )
    assert "needs 15.00kWh" in skip_message
    assert "only 3.00kWh available before start" in skip_message
    assert "SOC 100.0% => 15.00kWh usable above 40.0% reserve floor" in skip_message
    assert "min 5.0%, conservative 40.0%, target EOD 20.0%" in skip_message
    assert "scheduled charge +10.00kWh" in skip_message
    assert "earlier discharge -22.00kWh" in skip_message


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
    assert [period["power"] for period in schedule["charge"]] == [4000, 6000, 8000]


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
    assert [period["power"] for period in schedule["charge"]] == [1000, 1000, 1000]
    assert all(period["solar_aware"] is True for period in schedule["charge"])


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


def test_active_discharge_ignores_stale_ev_sensor(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["conservative_soc"] = 40
    config["soc"]["min_soc"] = 5
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
    )

    sensor_values = {
        config["entities"]["soc_entity"]: 55.0,
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

    assert not published, "Did not expect stale EV power to trigger a pause override"

    mode_updates = [call for call in entity_updates if call[0][1] == bm_main.ENTITY_MODE]
    assert mode_updates
    assert mode_updates[-1][0][2] == "discharge"


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


def test_max_soc_stabilizer_overrides_passive_solar_and_resumes_gap(monkeypatch):
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["soc"]["max_soc"] = 97
    config["power"]["max_discharge_power"] = 8000

    now = datetime.now(timezone.utc)
    passive_gap_schedule = {
        "charge": [{"start": (now + timedelta(minutes=1)).isoformat(), "duration": 1, "power": 0}],
        "discharge": [{"start": (now + timedelta(minutes=2)).isoformat(), "duration": 1, "power": 4000}],
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
