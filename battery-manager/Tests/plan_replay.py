"""Replay helpers: run generate_schedule against the 2026-10-07/08 curves."""

import os
import sys
import time
from copy import deepcopy
from datetime import timezone
from typing import Any, Dict, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import main as bm_main  # noqa: E402
from Tests import curves_2026_10_07 as curves  # noqa: E402


@pytest.fixture
def amsterdam_tz():
    """Run with Europe/Amsterdam as the local zone (plans use local dates)."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Amsterdam"
    time.tzset()
    yield
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    time.tzset()


def make_config(**overrides: Any) -> Dict[str, Any]:
    """Production-like config; overrides use ``section.key`` names."""
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config["dry_run"] = True
    config["soc"]["conservative_soc"] = 25
    config["power"]["min_scaled_power"] = 4000
    config["heuristics"]["adaptive_price_threshold"] = 0.25
    config["heuristics"]["charge_spread_max_price_delta"] = 0.01
    config["heuristics"]["sell_wait_for_better_morning_enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["heuristics"]["top_x_discharge_hours"] = 2
    for key, value in overrides.items():
        section, name = key.split(".")
        config[section][name] = value
    return config


def replay(
    monkeypatch,
    hhmm: str,
    soc: float,
    remaining_solar: Optional[float] = None,
    state: Optional["bm_main.RuntimeState"] = None,
    day: int = 7,
    import_curve=None,
    export_curve=None,
    config: Optional[Dict[str, Any]] = None,
    pv_power_w: float = 0.0,
    entity_updates: Optional[list] = None,
) -> Dict[str, Any]:
    """Generate the plan for 2026-10-<day> at local ``hhmm``."""
    now = curves.at(day, hhmm).astimezone(timezone.utc)
    monkeypatch.setattr(bm_main, "_utcnow", lambda: now)
    monkeypatch.setattr(bm_main, "_get_price_curve", lambda *_: import_curve or curves.import_curve())
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda *_: export_curve or curves.export_curve())
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *a, **k: soc)
    monkeypatch.setattr(
        bm_main, "_get_sensor_float",
        lambda _ha, entity_id: pv_power_w if entity_id.endswith("pv_power") else 12.0,
    )
    monkeypatch.setattr(bm_main, "_get_remaining_solar_energy_kwh", lambda *_: remaining_solar)
    monkeypatch.setattr(bm_main, "_get_schedule_slot_limits", lambda *_: (4, 8))
    monkeypatch.setattr(
        bm_main, "update_entity",
        (lambda _m, entity, st, attrs=None, dry_run=False: entity_updates.append((entity, st, attrs)))
        if entity_updates is not None
        else (lambda *a, **k: None),
    )
    schedule = bm_main.generate_schedule(config or make_config(), object(), None, state)
    if state is not None:
        state.schedule = schedule
    return schedule


def local_hhmm(period: Dict[str, Any], day_offset: bool = False) -> str:
    from dateutil.parser import isoparse
    start = isoparse(period["start"]).astimezone(curves.CEST)
    return start.strftime("%d %H:%M") if day_offset else start.strftime("%H:%M")


def local_start(period: Dict[str, Any]):
    from dateutil.parser import isoparse
    return isoparse(period["start"]).astimezone(curves.CEST)
