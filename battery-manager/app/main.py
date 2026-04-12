"""Battery Manager add-on main entry point."""

from __future__ import annotations

import json
import logging
import math
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dateutil.parser import isoparse

from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.ha_api import HomeAssistantApi
from shared.config_loader import get_run_once_mode
from shared.mqtt_setup import setup_mqtt_client
from shared.ha_mqtt_discovery import MqttDiscovery

from .ev_charger_monitor import should_pause_discharge
from .power_calculator import calculate_rank_scaled_power
from .price_analyzer import (
    calculate_discharge_top_x_count,
    PriceRange,
    calculate_price_ranges,
    calculate_top_x_count,
    detect_interval_minutes,
    find_profitable_discharge_starts,
    get_current_period_rank,
    get_current_price_entry,
)
from .solar_monitor import SolarMonitor
from .solar_charge_optimizer import (
    SolarAwareChargeAllocation,
    allocate_solar_aware_charge_powers,
    calculate_charge_deficit_kwh,
    parse_remaining_solar_energy_kwh,
)
from .gap_scheduler import GapScheduler
from .soc_guardian import calculate_sell_buffer_soc, can_charge, can_discharge
from .temperature_advisor import get_discharge_hours
from .status_reporter import (
    ENTITY_CHARGE_SCHEDULE,
    ENTITY_CURRENT_ACTION,
    ENTITY_DISCHARGE_SCHEDULE,
    ENTITY_EFFECTIVE_DISCHARGE_POWER,
    ENTITY_FORECAST,
    ENTITY_MODE,
    ENTITY_PRICE_RANGES,
    ENTITY_REASONING,
    ENTITY_SCHEDULE,
    ENTITY_SCHEDULE_2,
    ENTITY_STATUS,
    _serialize_windows,
    build_combined_schedule_display,
    build_next_event_summary,
    build_price_ranges_display,
    build_status_message,
    build_today_story,
    build_tomorrow_story,
    build_windows_display,
    find_upcoming_windows,
    get_temperature_icon,
    publish_all_entities,
    update_entity,
)

if "ENTITY_SCHEDULE_2" not in globals():
    ENTITY_SCHEDULE_2 = "schedule_part_2"

logger = setup_logging(name=__name__)


DEFAULT_CONFIG = {
    "enabled": True,
    "dry_run": False,
    "entities": {
        "price_curve_entity": "sensor.energy_prices_electricity_import_price",
        "export_price_curve_entity": "sensor.energy_prices_electricity_export_price",
        "remaining_solar_energy_entity": "sensor.energy_production_today_remaining",
        "soc_entity": "sensor.battery_api_battery_soc",
        "grid_power_entity": "sensor.power_usage",
        "solar_power_entity": "sensor.battery_api_pv_power",
        "house_load_entity": "sensor.battery_api_load_power",
        "battery_power_entity": "sensor.battery_api_battery_power",
        "battery_mode_entity": "select.battery_api_battery_mode",
        "temperature_entity": "sensor.weather_forecast_temperature",
    },
    "timing": {
        "update_interval": 3600,
        "monitor_interval": 60,
        "adaptive_power_grace_seconds": 60,
        "schedule_regen_cooldown_seconds": 60,
        "max_soc_sensor_age_seconds": 900,
        "max_ev_sensor_age_seconds": 180,
    },
    "power": {
        "charging_power_limit": 1000,
        "max_charge_power": 8000,
        "max_discharge_power": 8000,
        "min_discharge_power": 0,
        "min_scaled_power": 2500,
    },
    "adaptive": {
        "enabled": True,
    },
    "solar_aware_charging": {
        "enabled": True,
        "forecast_safety_factor": 0.8,
        "min_charge_power": 500,
    },
    "passive_solar": {
        "enabled": True,
        "entry_threshold": 1000,
        "exit_threshold": 200,
        "min_solar_entry_power": 200,
    },
    "soc": {
        "min_soc": 5,
        "conservative_soc": 40,
        "target_eod_soc": 20,
        "max_soc": 100,
        "battery_capacity_kwh": 25,
        "sell_buffer_enabled": True,
        "sell_buffer_min_soc": 20,
        "sell_buffer_activation_hours_before_sell": 3,
    },
    "heuristics": {
        "adaptive_price_threshold": 0.26,
        "top_x_charge_hours": 3,
        "top_x_discharge_hours": 2,
        "min_profit_threshold": 0.1,
        "overnight_wait_threshold": 0.02,
        "sell_wait_for_better_morning_enabled": False,
        "sell_wait_horizon_hours": 20,
        "sell_wait_min_gain_threshold": 0.02,
        "sell_wait_morning_start_hour": 0,
        "sell_wait_morning_end_hour": 10,
    },
    "temperature_based_discharge": {
        "enabled": True,
        "thresholds": [
            {"temp_max": 0, "discharge_hours": 1},
            {"temp_max": 8, "discharge_hours": 1.5},
            {"temp_max": 12, "discharge_hours": 2},
            {"temp_max": 16, "discharge_hours": 2.5},
            {"temp_max": 999, "discharge_hours": 3},
        ],
    },
    "ev_charger": {
        "enabled": True,
        "charging_threshold": 500,
        "entity_id": "sensor.charge_amps_monitor_charger_current_power",
    },
    "mqtt_host": "core-mosquitto",
    "mqtt_port": 1883,
    "mqtt_user": "",
    "mqtt_password": "",
}


@dataclass
class RuntimeState:
    schedule: Dict[str, Any]
    schedule_generated_at: Optional[datetime]
    published_schedule: Optional[Dict[str, Any]] = None
    last_price_curve: Optional[List[Dict[str, Any]]] = None
    last_curve_length: int = 0
    warned_missing_price: bool = False
    warned_missing_temperature: bool = False
    warned_missing_ev: bool = False
    warned_stale_ev: bool = False
    warned_missing_soc: bool = False
    warned_stale_soc: bool = False
    warned_schedule_missing_soc: bool = False
    warned_schedule_stale_soc: bool = False
    warned_missing_grid: bool = False
    warned_missing_solar: bool = False
    last_schedule_publish: Optional[datetime] = None
    last_power_adjustment: Optional[datetime] = None
    last_effective_discharge_power: Optional[int] = None
    last_price_range: Optional[str] = None
    last_effective_mode: Optional[str] = None
    last_published_payload: Optional[str] = None
    last_monitor_status: Optional[str] = None
    sell_buffer_required_soc: Optional[float] = None
    sell_buffer_discharge_hours: float = 0.0
    passive_gap_active: bool = False
    reduced_override_active: bool = False
    max_soc_stabilizer_until: Optional[datetime] = None


def _load_config() -> Dict[str, Any]:
    # Support CONFIG_PATH env var for local dry-run
    config_path = os.getenv("CONFIG_PATH", "/data/options.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return _merge_dicts(DEFAULT_CONFIG, data)

    logger.warning("Config file %s not found, using defaults", config_path)
    return DEFAULT_CONFIG.copy()


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _get_entity_state(ha_api: HomeAssistantApi, entity_id: str) -> Optional[Dict[str, Any]]:
    return ha_api.get_entity_state(entity_id)


def _get_sensor_float(ha_api: HomeAssistantApi, entity_id: str) -> Optional[float]:
    state = _get_entity_state(ha_api, entity_id)
    if not state:
        return None
    value = state.get("state")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_remaining_solar_energy_kwh(
    ha_api: HomeAssistantApi,
    entity_id: Optional[str],
) -> Optional[float]:
    if not entity_id:
        return None
    return parse_remaining_solar_energy_kwh(_get_entity_state(ha_api, entity_id))


def _parse_ha_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = isoparse(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _get_sensor_float_and_age_seconds(
    ha_api: HomeAssistantApi,
    entity_id: str,
    now: datetime,
) -> tuple[Optional[float], Optional[float]]:
    """Return sensor float value and age in seconds from HA timestamps when available."""
    state = _get_entity_state(ha_api, entity_id)
    if not state:
        return None, None

    value = state.get("state")
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = None

    updated_at = _parse_ha_timestamp(state.get("last_updated"))
    changed_at = _parse_ha_timestamp(state.get("last_changed"))
    ref_dt = updated_at or changed_at
    if ref_dt is None:
        return number, None

    age_seconds = (now - ref_dt).total_seconds()
    return number, max(0.0, age_seconds)


def _get_schedule_generation_soc(
    ha_api: HomeAssistantApi,
    config: Dict[str, Any],
    now: datetime,
    state: Optional[RuntimeState],
) -> Optional[float]:
    """Return SOC for schedule generation, ignoring stale readings."""

    soc_entity = config["entities"]["soc_entity"]
    soc, soc_age_seconds = _get_sensor_float_and_age_seconds(ha_api, soc_entity, now)
    max_soc_sensor_age = max(0, int(config.get("timing", {}).get("max_soc_sensor_age_seconds", 900)))

    if soc_age_seconds is not None and max_soc_sensor_age > 0 and soc_age_seconds > max_soc_sensor_age:
        if state is None or not state.warned_schedule_stale_soc:
            logger.warning(
                "⚠️ SOC sensor stale during schedule generation (age %.0fs > %ss); skipping discharge feasibility pruning",
                soc_age_seconds,
                max_soc_sensor_age,
            )
        if state is not None:
            state.warned_schedule_stale_soc = True
            state.warned_schedule_missing_soc = False
        return None

    if soc is None:
        if state is None or not state.warned_schedule_missing_soc:
            logger.warning(
                "⚠️ SOC sensor unavailable during schedule generation; skipping discharge feasibility pruning"
            )
        if state is not None:
            state.warned_schedule_missing_soc = True
            state.warned_schedule_stale_soc = False
        return None

    if state is not None:
        state.warned_schedule_missing_soc = False
        state.warned_schedule_stale_soc = False

    return soc


def _get_first_available_entity(ha_api: HomeAssistantApi, entity_ids: List[str]) -> Optional[Dict[str, Any]]:
    for entity_id in entity_ids:
        state = _get_entity_state(ha_api, entity_id)
        if state:
            return state
    return None


def _get_price_curve(ha_api: HomeAssistantApi, entity_id: str) -> Optional[List[Dict[str, Any]]]:
    candidates = [
        entity_id,
        "sensor.ep_price_import",
        "sensor.energy_prices_electricity_import_price",
    ]
    entity = _get_first_available_entity(ha_api, candidates)
    if not entity:
        return None

    attributes = entity.get("attributes", {})
    return attributes.get("price_curve") or attributes.get("price_curve_import")


def _get_export_price_curve(ha_api: HomeAssistantApi, entity_id: str) -> Optional[List[Dict[str, Any]]]:
    entity = _get_entity_state(ha_api, entity_id)
    if not entity:
        return None

    attributes = entity.get("attributes", {})
    return attributes.get("price_curve") or attributes.get("price_curve_export")


def _duration_minutes(period: Dict[str, Any], fallback: int) -> int:
    start = period.get("start")
    end = period.get("end")
    if not start or not end:
        return fallback
    try:
        start_dt = isoparse(start)
        end_dt = isoparse(end)
        return max(int((end_dt - start_dt).total_seconds() / 60), fallback)
    except Exception:
        return fallback


def _format_schedule_for_api(schedule: Dict[str, Any]) -> Dict[str, Any]:
    """Convert internal ISO schedule to API format (HH:MM).

    SAJ schedule slots are time-of-day based (no date). To avoid collisions,
    only periods for the local current date are published to battery-api.
    """

    def _parse_start_local(start_value: Any) -> tuple[str | None, datetime | None]:
        if not isinstance(start_value, str) or not start_value:
            return None, None

        # Already in HH:MM format
        if len(start_value) == 5 and start_value[2] == ":":
            try:
                int(start_value[:2])
                int(start_value[3:])
                return start_value, None
            except (TypeError, ValueError):
                return None, None

        try:
            parsed = isoparse(start_value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            local_dt = parsed.astimezone()
            return local_dt.strftime("%H:%M"), local_dt
        except Exception:
            return None, None

    def _minutes_of_day(hhmm: str) -> int:
        return int(hhmm[:2]) * 60 + int(hhmm[3:])

    def _sanitize_periods(periods: List[Dict[str, Any]], period_type: str) -> List[Dict[str, Any]]:
        dedup: Dict[str, Dict[str, Any]] = {}

        # Keep latest entry per start time, then remove overlaps.
        for period in periods:
            dedup[period["start"]] = period

        sorted_periods = sorted(dedup.values(), key=lambda item: _minutes_of_day(item["start"]))

        sanitized: List[Dict[str, Any]] = []
        last_end = -1
        for period in sorted_periods:
            start_min = _minutes_of_day(period["start"])
            end_min = min(start_min + int(period["duration"]), 24 * 60)
            if end_min <= start_min:
                continue

            if start_min < last_end:
                logger.warning(
                    "Skipping overlapping %s period for battery-api payload: %s +%sm",
                    period_type,
                    period["start"],
                    period["duration"],
                )
                continue

            sanitized.append(period)
            last_end = end_min

        return sanitized

    output: Dict[str, List[Dict[str, Any]]] = {"charge": [], "discharge": []}
    local_today = datetime.now().astimezone().date()

    for key in ["charge", "discharge"]:
        raw_periods = schedule.get(key, [])
        prepared: List[Dict[str, Any]] = []

        for raw in raw_periods:
            entry = dict(raw)
            start_hhmm, local_dt = _parse_start_local(entry.get("start"))
            if not start_hhmm:
                continue

            # For ISO schedules, keep only local-today windows.
            if local_dt is not None and local_dt.date() != local_today:
                continue

            try:
                duration = int(entry.get("duration", 0))
                power = int(entry.get("power", 0))
            except (TypeError, ValueError):
                continue

            if duration <= 0:
                continue

            prepared.append({
                "start": start_hhmm,
                "power": power,
                "duration": duration,
            })

        output[key] = _sanitize_periods(prepared, key)

    return output


# SAJ API period limits
MAX_CHARGE_PERIODS = 3
MAX_DISCHARGE_PERIODS = 6
MAX_SOC_STABILIZER_MINUTES = 5
MAX_SOC_STABILIZER_HYSTERESIS_PCT = 1.0


def _publish_schedule(
    mqtt_client: Optional[MqttDiscovery],
    schedule: Dict[str, Any],
    dry_run: bool,
    state: Optional["RuntimeState"] = None,
    force: bool = False,
) -> bool:
    """Publish schedule to battery-api via MQTT with retry on disconnect.

    Skips publishing if the payload is identical to the last published one,
    unless *force* is True (used for fresh schedule generation).
    Returns True if published (or skipped as duplicate), False on error.
    """
    api_schedule = _format_schedule_for_api(schedule)
    payload_json = json.dumps(api_schedule, sort_keys=True, ensure_ascii=False)

    # Dedup: skip if payload unchanged since last publish
    if not force and state and state.last_published_payload == payload_json:
        logger.debug("📡 Schedule unchanged, skipping publish")
        return True

    if dry_run:
        logger.info("📝 [Dry-Run] Schedule generated (not published)")
        logger.info("   Content: %s", payload_json)
        if state:
            state.published_schedule = deepcopy(schedule)
            state.last_published_payload = payload_json
        return True

    if mqtt_client is None:
        logger.warning("⚠️ MQTT unavailable, schedule not published")
        return False

    import time
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        if mqtt_client.is_connected():
            success = mqtt_client.publish_raw("battery_api/text/schedule/set", api_schedule, retain=False)
            if success:
                charge_count = len(api_schedule.get("charge", []))
                discharge_count = len(api_schedule.get("discharge", []))
                schedule_discharge = schedule.get("discharge", [])
                adaptive_periods = [
                    p for p in schedule_discharge if p.get("window_type") == "adaptive"
                ]
                adaptive_count = len(adaptive_periods)
                adaptive_powers = sorted(
                    {
                        int(p.get("power", 0))
                        for p in adaptive_periods
                        if isinstance(p.get("power"), (int, float))
                    }
                )

                if adaptive_count > 0:
                    adaptive_power_text = ",".join(f"{power}W" for power in adaptive_powers) if adaptive_powers else "unknown"
                    logger.info(
                        "📡 Schedule published: %d charge + %d discharge periods | adaptive discharging: %d (%s)",
                        charge_count,
                        discharge_count,
                        adaptive_count,
                        adaptive_power_text,
                    )
                else:
                    logger.info(
                        "📡 Schedule published: %d charge + %d discharge periods",
                        charge_count,
                        discharge_count,
                    )
                if state:
                    state.published_schedule = deepcopy(schedule)
                    state.last_published_payload = payload_json
                return True
            logger.warning("⚠️ MQTT publish failed (attempt %d/%d)", attempt, max_attempts)
        else:
            logger.warning("⚠️ MQTT disconnected, waiting for reconnect (attempt %d/%d)", attempt, max_attempts)
        if attempt < max_attempts:
            time.sleep(5)
    
    logger.error("❌ Failed to publish schedule after %d attempts", max_attempts)
    return False


def _build_max_soc_stabilizer_schedule(
    now: datetime,
    power: int,
    duration_minutes: int,
) -> Dict[str, Any]:
    return {
        "charge": [],
        "discharge": [
            {
                "start": now.isoformat(),
                "power": power,
                "duration": duration_minutes,
                "window_type": "max_soc_stabilizer",
            }
        ],
    }


def _get_max_soc_stabilizer_power(config: Dict[str, Any]) -> int:
    max_power = int(config.get("power", {}).get("max_discharge_power", 8000))
    return max(0, int(max_power / 2))


def _split_curve_by_date(
    curve: List[Dict[str, Any]],
    reference_time: Optional[datetime] = None,
) -> tuple[list[dict], list[dict]]:
    if reference_time is None:
        local_reference = datetime.now(timezone.utc).astimezone()
    else:
        local_reference = (
            reference_time.astimezone()
            if reference_time.tzinfo
            else reference_time.replace(tzinfo=timezone.utc).astimezone()
        )

    today = local_reference.date()
    tomorrow = today + timedelta(days=1)
    today_curve: List[Dict[str, Any]] = []
    tomorrow_curve: List[Dict[str, Any]] = []

    for entry in curve:
        start = entry.get("start")
        if not start:
            continue
        try:
            start_dt = isoparse(start)
        except Exception:
            continue
        local_start = start_dt.astimezone() if start_dt.tzinfo else start_dt.replace(tzinfo=timezone.utc).astimezone()
        if local_start.date() == today:
            today_curve.append(entry)
        elif local_start.date() == tomorrow:
            tomorrow_curve.append(entry)

    return today_curve, tomorrow_curve


def _determine_price_range(
    import_price: float,
    export_price: float,
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    adaptive_price_threshold: Optional[float] = None,
    adaptive_enabled: bool = True,
) -> str:
    """Classify the current price into load/discharge/adaptive/passive.

    When an adaptive_price_threshold is set, prices in the adaptive range
    that fall below the threshold are returned as "passive" — meaning the
    battery should neither charge nor actively discharge (house runs on grid).
    Prices at or above the threshold stay "adaptive" and the battery will
    discharge to bring grid export to 0W.
    """
    if load_range and load_range.min_price <= import_price <= load_range.max_price:
        return "load"
    if discharge_range and discharge_range.min_price <= export_price <= discharge_range.max_price:
        return "discharge"
    if adaptive_price_threshold is not None and import_price < adaptive_price_threshold:
        return "passive"
    if not adaptive_enabled:
        return "passive"
    return "adaptive"


def _should_regenerate_live_schedule(
    runtime_price_range: str,
    active_charge: bool,
    active_discharge: bool,
    import_curve: Optional[List[Dict[str, Any]]],
    soc: Optional[float],
    config: Dict[str, Any],
) -> Optional[str]:
    """Return the live price band that should trigger a schedule refresh."""

    if not import_curve:
        return None

    max_soc = float(config["soc"].get("max_soc", 100))
    if runtime_price_range == "load":
        if not active_charge and not (soc is not None and soc >= max_soc):
            return "load"
        return None

    if runtime_price_range != "adaptive" or active_charge or active_discharge or soc is None:
        return None

    min_soc = float(config["soc"].get("min_soc", 5))
    conservative_soc = float(config["soc"].get("conservative_soc", min_soc))
    if can_discharge(soc, min_soc, conservative_soc, True):
        return "adaptive"

    return None


def _update_effective_discharge_power(
    mqtt_client: Any,
    power: Optional[int],
    dry_run: bool,
    *,
    active_window_type: Optional[str] = None,
    price_range: Optional[str] = None,
    effective_price_range: Optional[str] = None,
    soc: Optional[float] = None,
    grid_power: Optional[float] = None,
) -> None:
    sensor_state = "unknown" if power is None else f"{int(power)}"
    attributes = {
        "active_window_type": active_window_type,
        "price_range": price_range,
        "effective_price_range": effective_price_range,
        "soc": soc,
        "grid_power": grid_power,
    }
    update_entity(
        mqtt_client,
        ENTITY_EFFECTIVE_DISCHARGE_POWER,
        sensor_state,
        {key: value for key, value in attributes.items() if value is not None} or None,
        dry_run=dry_run,
    )


def _update_mode_entity(
    mqtt_client: Any,
    state: RuntimeState,
    mode: str,
    dry_run: bool,
    *,
    price_range: Optional[str] = None,
) -> None:
    if state.last_effective_mode == mode:
        return
    attributes = {"price_range": price_range} if price_range is not None else None
    update_entity(mqtt_client, ENTITY_MODE, mode, attributes, dry_run=dry_run)
    state.last_effective_mode = mode


def _interval_window(now: datetime, interval_minutes: int) -> tuple[datetime, datetime]:
    interval_minutes = max(interval_minutes, 1)
    rounded = now.replace(
        minute=(now.minute // interval_minutes) * interval_minutes, second=0, microsecond=0
    )
    return rounded, rounded + timedelta(minutes=interval_minutes)


def _minutes_until_end_of_day(start_dt: datetime) -> int:
    end_dt = start_dt.replace(hour=23, minute=59, second=0, microsecond=0)
    minutes = int((end_dt - start_dt).total_seconds() / 60)
    return max(minutes, 1)


def _split_state_for_ha(state_text: str, max_len: int = 255) -> tuple[str, str]:
    """Split long state text without cutting through markdown rows when possible."""
    if len(state_text) <= max_len:
        return state_text, " "

    cut_idx = state_text.rfind("\n", 0, max_len)
    if cut_idx <= 0:
        cut_idx = max_len

    first = state_text[:cut_idx]
    second = state_text[cut_idx + 1 :] if cut_idx < len(state_text) else " "
    if not second:
        second = " "
    return first, second


def _should_wait_for_overnight(
    today_curve: List[Dict[str, Any]],
    tomorrow_curve: List[Dict[str, Any]],
    threshold: float,
) -> bool:
    if not today_curve or not tomorrow_curve:
        return False

    evening_prices = []
    overnight_prices = []

    for entry in today_curve:
        start = entry.get("start")
        price = entry.get("price")
        if not start or price is None:
            continue
        try:
            start_dt = isoparse(start)
        except Exception:
            continue
        if start_dt.hour >= 20:
            evening_prices.append(float(price))

    for entry in tomorrow_curve:
        start = entry.get("start")
        price = entry.get("price")
        if not start or price is None:
            continue
        try:
            start_dt = isoparse(start)
        except Exception:
            continue
        if start_dt.hour < 6:
            overnight_prices.append(float(price))

    if not evening_prices or not overnight_prices:
        return False

    evening_avg = sum(evening_prices) / len(evening_prices)
    overnight_avg = sum(overnight_prices) / len(overnight_prices)
    return (evening_avg - overnight_avg) >= threshold


def _get_sell_wait_decision(
    discharge_windows: List[Dict[str, Any]],
    now: datetime,
    heuristics: Dict[str, Any],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a discharge wait decision when a better near-term morning sell window exists."""

    def _set_diag(reason: str, **extra: Any) -> None:
        if diagnostics is None:
            return
        diagnostics.clear()
        diagnostics.update({"reason": reason, **extra})

    if not heuristics.get("sell_wait_for_better_morning_enabled", False):
        _set_diag("disabled")
        return None

    horizon_hours = max(0.0, float(heuristics.get("sell_wait_horizon_hours", 12)))
    min_gain = float(heuristics.get("sell_wait_min_gain_threshold", 0.02))
    morning_start = int(heuristics.get("sell_wait_morning_start_hour", 5)) % 24
    morning_end = int(heuristics.get("sell_wait_morning_end_hour", 10)) % 24

    if horizon_hours <= 0:
        _set_diag("invalid_horizon", horizon_hours=horizon_hours)
        return None

    horizon_end = now + timedelta(hours=horizon_hours)

    def _in_target_window(start_dt: datetime) -> bool:
        hour = start_dt.astimezone().hour
        if morning_start == morning_end:
            return True
        if morning_start < morning_end:
            return morning_start <= hour < morning_end
        return hour >= morning_start or hour < morning_end

    future_candidates = []
    for window in discharge_windows:
        start_dt = window.get("start")
        avg_price = window.get("avg_price")
        if not isinstance(start_dt, datetime) or avg_price is None:
            continue
        if start_dt <= now or start_dt > horizon_end:
            continue
        if not _in_target_window(start_dt):
            continue
        future_candidates.append(window)

    if not future_candidates:
        _set_diag(
            "no_target_window_candidate",
            horizon_hours=horizon_hours,
            morning_start=morning_start,
            morning_end=morning_end,
            discharge_window_count=len(discharge_windows),
        )
        return None

    best_candidate = max(
        future_candidates,
        key=lambda w: (
            float(w.get("avg_price", 0.0)),
            -(w.get("start").timestamp() if isinstance(w.get("start"), datetime) else 0.0),
        ),
    )
    candidate_start = best_candidate.get("start")
    candidate_price = float(best_candidate.get("avg_price", 0.0))
    if not isinstance(candidate_start, datetime):
        _set_diag("invalid_candidate")
        return None

    pre_target_prices: List[float] = []
    for window in discharge_windows:
        start_dt = window.get("start")
        end_dt = window.get("end")
        avg_price = window.get("avg_price")
        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime) or avg_price is None:
            continue
        if end_dt <= now:
            continue
        if start_dt >= candidate_start:
            continue
        pre_target_prices.append(float(avg_price))

    if not pre_target_prices:
        _set_diag(
            "no_pre_target_windows",
            candidate_start=candidate_start.isoformat(),
            candidate_price=candidate_price,
            candidate_count=len(future_candidates),
        )
        return None

    best_pre_target_price = max(pre_target_prices)
    gain = candidate_price - best_pre_target_price
    if gain + 1e-9 < min_gain:
        _set_diag(
            "gain_below_threshold",
            candidate_start=candidate_start.isoformat(),
            candidate_price=candidate_price,
            best_pre_target_price=best_pre_target_price,
            gain=gain,
            min_gain=min_gain,
        )
        return None

    _set_diag(
        "decision",
        candidate_start=candidate_start.isoformat(),
        candidate_price=candidate_price,
        best_pre_target_price=best_pre_target_price,
        gain=gain,
        min_gain=min_gain,
    )

    return {
        "wait_until": candidate_start,
        "best_future_price": candidate_price,
        "best_price_before_wait": best_pre_target_price,
        "gain": gain,
    }


def _calculate_adaptive_power(
    grid_power: Optional[float],
    current_power: int,
    min_discharge_power: int,
    max_power: int,
    adjustment_threshold: int = 50,
) -> Optional[int]:
    if grid_power is None:
        return None

    if abs(grid_power) <= adjustment_threshold:
        return None

    raw_target = int(current_power + grid_power)
    if raw_target < min_discharge_power:
        target = 0
    else:
        rounded = int(round(raw_target / 100.0)) * 100
        target = min(rounded, max_power)

    if abs(target - current_power) >= 100:
        return target
    return None


def _is_period_active(period: Dict[str, Any], now: datetime) -> bool:
    bounds = _parse_schedule_period_bounds(period)
    if bounds is None:
        return False

    start_dt, end_dt = bounds
    return start_dt <= now < end_dt


def _parse_schedule_period_bounds(period: Dict[str, Any]) -> Optional[tuple[datetime, datetime]]:
    start_str = period.get("start")
    duration = period.get("duration", 0)
    if not start_str or not duration:
        return None
    try:
        start_dt = isoparse(start_str)
        end_dt = start_dt + timedelta(minutes=int(duration))
    except Exception:
        return None

    return start_dt, end_dt


def _period_energy_kwh(power_watts: float, duration_minutes: int) -> float:
    if power_watts <= 0 or duration_minutes <= 0:
        return 0.0
    return (float(power_watts) / 1000.0) * (duration_minutes / 60.0)


def _sum_discharge_hours_before_main_charge(
    discharge_windows: List[Dict[str, Any]],
    main_charge_start: datetime,
    now: datetime,
) -> float:
    """Return total discharge hours between now and the main charge start."""

    total_hours = 0.0
    for window in discharge_windows:
        start_dt = window.get("start")
        end_dt = window.get("end")
        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
            continue
        if start_dt >= main_charge_start:
            continue

        effective_start = max(start_dt, now)
        effective_end = min(end_dt, main_charge_start)
        if effective_end <= effective_start:
            continue

        total_hours += (effective_end - effective_start).total_seconds() / 3600.0

    return total_hours


def _filter_supported_discharge_windows(
    discharge_windows: List[Dict[str, Any]],
    charge_schedule: List[Dict[str, Any]],
    soc: Optional[float],
    config: Dict[str, Any],
    not_before: datetime,
    top_x_discharge_count: int,
    min_scaled_power: int,
) -> List[Dict[str, Any]]:
    """Keep only future discharge windows that current/planned energy can support."""

    if soc is None or not discharge_windows:
        return discharge_windows

    battery_capacity_kwh = float(config["soc"].get("battery_capacity_kwh", 25))
    min_soc = float(config["soc"].get("min_soc", 5))
    if battery_capacity_kwh <= 0:
        return discharge_windows

    base_available_energy_kwh = max(0.0, (float(soc) - min_soc) / 100.0 * battery_capacity_kwh)
    available_energy_kwh = base_available_energy_kwh
    charge_periods: List[tuple[datetime, datetime, int]] = []
    for period in charge_schedule:
        bounds = _parse_schedule_period_bounds(period)
        if bounds is None:
            continue
        charge_periods.append((bounds[0], bounds[1], int(period.get("power", 0))))

    charge_periods.sort(key=lambda item: item[0])
    charge_index = 0
    feasible_windows: List[Dict[str, Any]] = []
    max_rank = max(top_x_discharge_count, 1)
    charged_before_start_kwh = 0.0
    reserved_before_start_kwh = 0.0

    for rank, window in enumerate(discharge_windows, start=1):
        start_dt = window.get("start")
        end_dt = window.get("end")
        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
            continue

        effective_start = max(start_dt, not_before)
        duration_minutes = int((end_dt - effective_start).total_seconds() / 60)
        if duration_minutes <= 0:
            continue

        while charge_index < len(charge_periods) and charge_periods[charge_index][1] <= effective_start:
            charge_start, charge_end, charge_power = charge_periods[charge_index]
            charge_duration = int((charge_end - charge_start).total_seconds() / 60)
            charge_energy_kwh = _period_energy_kwh(charge_power, charge_duration)
            available_energy_kwh += charge_energy_kwh
            charged_before_start_kwh += charge_energy_kwh
            charge_index += 1

        planned_power = calculate_rank_scaled_power(
            rank,
            max_rank,
            config["power"]["max_discharge_power"],
            min_scaled_power,
        )
        required_energy_kwh = _period_energy_kwh(planned_power, duration_minutes)
        if required_energy_kwh <= available_energy_kwh + 1e-6:
            available_energy_kwh = max(0.0, available_energy_kwh - required_energy_kwh)
            reserved_before_start_kwh += required_energy_kwh
            feasible_windows.append(window)
            continue

        logger.info(
            "⛔ Skipping discharge window %s @€%.3f: needs %.2fkWh, only %.2fkWh available before start (SOC %.1f%% => %.2fkWh usable above %.1f%% min, scheduled charge +%.2fkWh, earlier discharge -%.2fkWh)",
            effective_start.astimezone().strftime("%H:%M"),
            float(window.get("avg_price", 0.0)),
            required_energy_kwh,
            available_energy_kwh,
            float(soc),
            base_available_energy_kwh,
            min_soc,
            charged_before_start_kwh,
            reserved_before_start_kwh,
        )

    return feasible_windows


def _calculate_dynamic_sell_buffer_soc(
    windows: Dict[str, List[Dict[str, Any]]],
    now: datetime,
    config: Dict[str, Any],
) -> tuple[Optional[float], float, Optional[datetime]]:
    """Calculate required SOC buffer for discharge windows before the first charge window."""

    soc_cfg = config.get("soc", {})
    if not soc_cfg.get("sell_buffer_enabled", True):
        return None, 0.0, None

    future_charge_windows = sorted(
        [w for w in windows.get("charge", []) if w.get("end") and w["end"] > now],
        key=lambda w: w["start"],
    )
    if not future_charge_windows:
        return None, 0.0, None

    main_charge_start = future_charge_windows[0]["start"]

    lead_hours_before_sell = max(
        0.0,
        float(soc_cfg.get("sell_buffer_activation_hours_before_sell", 3)),
    )
    relevant_discharge_windows = sorted(
        [
            w for w in windows.get("discharge", [])
            if w.get("end") and w["end"] > now and w.get("start") and w["start"] < main_charge_start
        ],
        key=lambda w: w["start"],
    )
    if relevant_discharge_windows:
        first_discharge_start = relevant_discharge_windows[0]["start"]
        hours_until_first_discharge = max(
            0.0,
            (first_discharge_start - now).total_seconds() / 3600.0,
        )
        if hours_until_first_discharge > lead_hours_before_sell:
            logger.info(
                "🕒 Sell-buffer deferred: first sell window at %s (in %.2fh), activation window %.2fh",
                first_discharge_start.astimezone().strftime("%H:%M"),
                hours_until_first_discharge,
                lead_hours_before_sell,
            )
            return None, 0.0, main_charge_start

    discharge_hours = _sum_discharge_hours_before_main_charge(
        windows.get("discharge", []),
        main_charge_start,
        now,
    )

    if discharge_hours <= 0:
        return None, 0.0, main_charge_start

    required_soc = calculate_sell_buffer_soc(
        discharge_hours_before_main_charge=discharge_hours,
        safety_min_soc=float(soc_cfg.get("sell_buffer_min_soc", 20)),
        discharge_power_watts=float(config["power"].get("max_discharge_power", 8000)),
        battery_capacity_kwh=float(soc_cfg.get("battery_capacity_kwh", 25)),
        floor_soc=float(soc_cfg.get("min_soc", 5)),
        rounding_step_pct=float(soc_cfg.get("sell_buffer_rounding_step_pct", 10)),
    )

    return required_soc, discharge_hours, main_charge_start


def _build_display_windows_from_schedule(schedule: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Convert generated schedule periods into window buckets for display."""

    display: Dict[str, List[Dict[str, Any]]] = {
        "charge": [],
        "discharge": [],
        "adaptive": [],
    }

    for period in schedule.get("charge", []):
        start = period.get("start")
        duration = period.get("duration")
        if not start or duration is None:
            continue
        try:
            start_dt = isoparse(str(start))
            end_dt = start_dt + timedelta(minutes=int(duration))
            avg_price = float(period.get("price", 0.0))
        except Exception:
            continue
        display["charge"].append({
            "start": start_dt,
            "end": end_dt,
            "avg_price": avg_price,
            "power": int(period.get("power", 0)),
        })

    for period in schedule.get("discharge", []):
        start = period.get("start")
        duration = period.get("duration")
        if not start or duration is None:
            continue
        try:
            start_dt = isoparse(str(start))
            end_dt = start_dt + timedelta(minutes=int(duration))
            avg_price = float(period.get("price", 0.0))
        except Exception:
            continue

        window_type = period.get("window_type", "discharge")
        if window_type != "adaptive":
            window_type = "discharge"
        display[window_type].append({
            "start": start_dt,
            "end": end_dt,
            "avg_price": avg_price,
            "power": int(period.get("power", 0)),
        })

    for key in ("charge", "discharge", "adaptive"):
        display[key].sort(key=lambda w: w["start"])

    return display


def _build_range_state(
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    adaptive_range: Optional[PriceRange],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Build a serializable price-range state payload for MQTT attributes."""
    return {
        "load": {
            "min": load_range.min_price if load_range else None,
            "max": load_range.max_price if load_range else None,
        },
        "discharge": {
            "min": discharge_range.min_price if discharge_range else None,
            "max": discharge_range.max_price if discharge_range else None,
        },
        "adaptive": {
            "min": adaptive_range.min_price if adaptive_range else None,
            "max": adaptive_range.max_price if adaptive_range else None,
        },
    }


def _expand_charge_window_slots(window: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand a grouped charge window into individual slot entries."""
    expanded: List[Dict[str, Any]] = []
    raw_slots = window.get("slots")
    if isinstance(raw_slots, list) and raw_slots:
        for slot in raw_slots:
            start_dt = slot.get("start")
            end_dt = slot.get("end")
            price = slot.get("price")
            if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime) or price is None:
                continue
            expanded.append({
                "start": start_dt,
                "end": end_dt,
                "price": float(price),
            })
    if expanded:
        return expanded

    start_dt = window.get("start")
    end_dt = window.get("end")
    avg_price = window.get("avg_price")
    if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime) or avg_price is None:
        return []

    return [{
        "start": start_dt,
        "end": end_dt,
        "price": float(avg_price),
    }]


def _publish_price_ranges(
    mqtt_client: Any,
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    adaptive_range: Optional[PriceRange],
    adaptive_price_threshold: Optional[float],
    dry_run: bool,
) -> None:
    """Publish textual and structured price ranges to Home Assistant entities."""
    price_ranges_text = build_price_ranges_display(
        load_range,
        discharge_range,
        adaptive_range,
        adaptive_price_threshold,
    )
    update_entity(
        mqtt_client,
        ENTITY_PRICE_RANGES,
        price_ranges_text,
        _build_range_state(load_range, discharge_range, adaptive_range),
        dry_run=dry_run,
    )


def _log_sensor_snapshot(
    soc: Optional[float],
    grid_power: Optional[float],
    solar_power: Optional[float],
    house_load: Optional[float],
    batt_power: Optional[float],
    ev_power: Optional[float],
    level: int = logging.DEBUG,
) -> None:
    """Log current sensor values in a consistent, single-line format."""
    logger.log(
        level,
        "📊 Sensors | SOC: %s%% | Grid: %sW | Solar: %sW | Load: %sW | Bat: %sW | EV: %sW",
        soc if soc is not None else "?",
        grid_power if grid_power is not None else "?",
        solar_power if solar_power is not None else "?",
        house_load if house_load is not None else "?",
        batt_power if batt_power is not None else "?",
        ev_power if ev_power is not None else "?",
    )


def _get_active_period_power(
    schedule: Dict[str, Any],
    period_type: str,
    now: datetime,
) -> Optional[int]:
    """Return power for the currently active period type, if any."""
    for period in schedule.get(period_type, []):
        if _is_period_active(period, now):
            return period.get("power")
    return None




def generate_schedule(
    config: Dict[str, Any],
    ha_api: HomeAssistantApi,
    mqtt_client: Any,
    state: Optional[RuntimeState] = None,
) -> Dict[str, Any]:
    logger.info("📊 Generating schedule...")
    import_entity = config["entities"]["price_curve_entity"]
    export_entity = config["entities"]["export_price_curve_entity"]
    import_curve = _get_price_curve(ha_api, import_entity)
    export_curve = _get_export_price_curve(ha_api, export_entity)

    is_dry_run = config.get("dry_run", False)

    if not import_curve and state and state.last_price_curve:
        import_curve = state.last_price_curve
        logger.warning("⚠️ Import price curve unavailable; using last known curve")

    if not import_curve:
        logger.warning("⚠️ Import price curve unavailable; skipping schedule generation")
        if state:
            state.warned_missing_price = True
        return {"charge": [], "discharge": []}

    if not export_curve:
        logger.warning("⚠️ Export price curve unavailable; using import curve for discharge ranking")
        export_curve = import_curve

    logger.info(
        "📊 Using price curves: import=%s (%d points), export=%s (%d points)",
        import_entity,
        len(import_curve),
        export_entity,
        len(export_curve),
    )

    now = datetime.now(timezone.utc)
    interval_minutes = detect_interval_minutes(import_curve)
    interval_start, interval_end = _interval_window(now, interval_minutes)

    top_x_charge_hours = config["heuristics"]["top_x_charge_hours"]
    top_x_discharge_hours = config["heuristics"]["top_x_discharge_hours"]
    min_profit = config["heuristics"].get("min_profit_threshold", 0.1)
    overnight_threshold = config["heuristics"].get("overnight_wait_threshold", 0.02)

    if config["temperature_based_discharge"]["enabled"]:
        temperature_entity = config["entities"]["temperature_entity"]
        temperature = _get_sensor_float(ha_api, temperature_entity)
        logger.info("  Temperature sensor %s=%s", temperature_entity, temperature)
        if temperature is None and state and not state.warned_missing_temperature:
            logger.warning("⚠️ Temperature sensor unavailable, using default discharge hours")
            state.warned_missing_temperature = True
        top_x_discharge_hours = get_discharge_hours(
            temperature,
            config["temperature_based_discharge"]["thresholds"],
        )
        logger.info("  Effective discharge hours from temperature: %.2f", top_x_discharge_hours)

    top_x_charge_count = calculate_top_x_count(top_x_charge_hours, interval_minutes)
    top_x_discharge_count = calculate_discharge_top_x_count(top_x_discharge_hours, interval_minutes)

    today_import, tomorrow_import = _split_curve_by_date(import_curve, now)
    today_export, tomorrow_export_curve = _split_curve_by_date(export_curve, now)

    # Today's operating ranges must only use today's prices.
    range_import_curve = today_import if today_import else import_curve
    range_export_curve = today_export if today_export else export_curve

    load_range, discharge_range, adaptive_range = calculate_price_ranges(
        range_import_curve,
        range_export_curve,
        top_x_charge_count,
        top_x_discharge_count,
        min_profit,
    )
    today_discharge_slot_starts = find_profitable_discharge_starts(
        range_import_curve,
        range_export_curve,
        top_x_discharge_count,
        min_profit,
    )
    # If adaptive mode is disabled via config, force adaptive_range to None
    # so we don't display it or schedule adaptive windows
    adaptive_enabled = config.get("adaptive", {}).get("enabled", True)
    if not adaptive_enabled:
        adaptive_range = None

    current_import_entry = get_current_price_entry(import_curve, now, interval_minutes)
    current_export_entry = get_current_price_entry(export_curve, now, interval_minutes)
    if not current_import_entry:
        logger.warning("⚠️ Current import price unavailable; using baseline discharge")
        current_import_entry = {"price": 0.0, "start": interval_start.isoformat()}
    if not current_export_entry:
        current_export_entry = {
            "price": current_import_entry.get("price", 0.0),
            "start": interval_start.isoformat(),
        }

    import_price = float(current_import_entry.get("price", 0.0))
    export_price = float(current_export_entry.get("price", import_price))
    adaptive_price_threshold = config["heuristics"].get("adaptive_price_threshold")
    price_range = _determine_price_range(
        import_price, export_price, load_range, discharge_range, adaptive_price_threshold,
        adaptive_enabled=adaptive_enabled,
    )

    if price_range == "load" and now.hour >= 20:
        if _should_wait_for_overnight(today_import, tomorrow_import, overnight_threshold):
            logger.info("⏳ Evening prices higher than overnight; waiting to charge")
            price_range = "adaptive"

    if state:
        # Detect new prices (e.g. tomorrow's prices arriving ~14:00)
        new_length = len(import_curve)
        if state.last_curve_length > 0 and new_length > state.last_curve_length:
            logger.info(
                "📈 Price curve grew from %d to %d entries — tomorrow prices detected, recalculating ranges",
                state.last_curve_length, new_length,
            )
        state.last_curve_length = new_length
        state.last_price_curve = import_curve

    _publish_price_ranges(
        mqtt_client,
        load_range,
        discharge_range,
        adaptive_range,
        adaptive_price_threshold,
        is_dry_run,
    )

    reasoning_text = build_today_story(
        price_range, import_price, export_price,
        load_range, discharge_range, adaptive_range,
        adaptive_price_threshold, now,
    )
    update_entity(mqtt_client, ENTITY_REASONING, reasoning_text,
                  {"price_range": price_range, "import_price": import_price, "export_price": export_price},
                  dry_run=is_dry_run)

    tomorrow_load: Optional[PriceRange] = None
    tomorrow_discharge: Optional[PriceRange] = None
    tomorrow_discharge_slot_starts: Optional[set[str]] = None

    if tomorrow_import:
        tomorrow_export = tomorrow_import
        if export_curve:
            tomorrow_export = tomorrow_export_curve
        tomorrow_load, tomorrow_discharge, tomorrow_adaptive = calculate_price_ranges(
            tomorrow_import,
            tomorrow_export,
            top_x_charge_count,
            top_x_discharge_count,
            min_profit,
        )
        tomorrow_discharge_slot_starts = find_profitable_discharge_starts(
            tomorrow_import,
            tomorrow_export,
            top_x_discharge_count,
            min_profit,
        )
        forecast_text = build_tomorrow_story(
            tomorrow_load, tomorrow_discharge, tomorrow_adaptive, tomorrow_import,
            adaptive_price_threshold=adaptive_price_threshold,
        )
    else:
        forecast_text = build_tomorrow_story(None, None, None)

    update_entity(mqtt_client, ENTITY_FORECAST, forecast_text, dry_run=is_dry_run)

    discharge_rank = get_current_period_rank(range_export_curve, top_x_discharge_count, now, reverse=True)

    min_scaled_power = config["power"].get(
        "min_scaled_power", config["power"]["min_discharge_power"]
    )
    charge_power = config["power"]["max_charge_power"]

    discharge_power = config["power"]["min_discharge_power"]
    if discharge_rank:
        discharge_power = calculate_rank_scaled_power(
            discharge_rank,
            top_x_discharge_count,
            config["power"]["max_discharge_power"],
            min_scaled_power,
        )

    soc = _get_schedule_generation_soc(ha_api, config, now, state)
    max_soc = config["soc"].get("max_soc", 100)
    skip_charge = soc is not None and not can_charge(soc, max_soc)
    if skip_charge and price_range == "load":
        logger.info("🛑 SOC %.1f%% >= %s%%, skipping charge windows", soc, max_soc)

    # Build multi-period schedule from all upcoming price windows
    # This ensures all charge/discharge windows are sent to the inverter at once,
    # instead of only scheduling the current interval
    upcoming_windows = find_upcoming_windows(
        import_curve, export_curve, load_range, discharge_range,
        adaptive_price_threshold, now,
        tomorrow_load_range=tomorrow_load,
        tomorrow_discharge_range=tomorrow_discharge,
        discharge_slot_starts=today_discharge_slot_starts,
        tomorrow_discharge_slot_starts=tomorrow_discharge_slot_starts,
        adaptive_enabled=adaptive_enabled,
    )

    sell_wait_diagnostics: Dict[str, Any] = {}
    sell_wait_decision = _get_sell_wait_decision(
        upcoming_windows.get("discharge", []),
        now,
        config.get("heuristics", {}),
        diagnostics=sell_wait_diagnostics,
    )
    if sell_wait_decision:
        wait_until = sell_wait_decision["wait_until"]
        logger.info(
            "⏳ Sell-wait active until %s: best future %.3f vs pre-wait %.3f (gain %.3f)",
            wait_until.astimezone().strftime("%H:%M"),
            sell_wait_decision["best_future_price"],
            sell_wait_decision["best_price_before_wait"],
            sell_wait_decision["gain"],
        )
    elif config.get("heuristics", {}).get("sell_wait_for_better_morning_enabled", False):
        logger.info(
            "⏭️ Sell-wait skipped: %s%s",
            sell_wait_diagnostics.get("reason", "unknown"),
            f" | details={sell_wait_diagnostics}" if sell_wait_diagnostics else "",
        )

    buffer_required_soc, buffer_discharge_hours, main_charge_start = _calculate_dynamic_sell_buffer_soc(
        upcoming_windows,
        now,
        config,
    )

    ranked_charge_slots = sorted(
        [
            slot
            for window in upcoming_windows.get("charge", [])
            for slot in _expand_charge_window_slots(window)
        ],
        key=lambda slot: (float(slot.get("price", 0.0)), slot["start"].isoformat()),
    )
    charge_slot_rank_by_start: Dict[str, int] = {}
    for idx, slot in enumerate(ranked_charge_slots, start=1):
        charge_slot_rank_by_start[slot["start"].isoformat()] = idx

    if state:
        state.sell_buffer_required_soc = buffer_required_soc
        state.sell_buffer_discharge_hours = buffer_discharge_hours

    precharge_until: Optional[datetime] = None
    precharge_price_ceiling: Optional[float] = adaptive_price_threshold
    if precharge_price_ceiling is None and load_range is not None:
        precharge_price_ceiling = load_range.max_price

    if (
        soc is not None
        and buffer_required_soc is not None
        and soc < buffer_required_soc
        and not skip_charge
    ):
        sell_buffer_floor_soc = float(config["soc"].get("sell_buffer_min_soc", 20))
        is_below_sell_buffer_floor = soc < sell_buffer_floor_soc
        # Prevent emergency precharge from buying at expensive prices.
        if (
            precharge_price_ceiling is not None
            and import_price > precharge_price_ceiling
            and not is_below_sell_buffer_floor
        ):
            logger.warning(
                "🚫 Skipping pre-sell precharge: current price €%.3f above ceiling €%.3f",
                import_price,
                precharge_price_ceiling,
            )
        else:
            if (
                precharge_price_ceiling is not None
                and import_price > precharge_price_ceiling
                and is_below_sell_buffer_floor
            ):
                logger.warning(
                    "⚠️ Forcing sell-buffer floor precharge: SOC %.1f%% below floor %.1f%% despite price €%.3f > €%.3f",
                    soc,
                    sell_buffer_floor_soc,
                    import_price,
                    precharge_price_ceiling,
                )
            capacity_kwh = float(config["soc"].get("battery_capacity_kwh", 25))
            charge_power_watts = float(config["power"].get("max_charge_power", 8000))
            soc_per_hour_charge = max(0.0, (charge_power_watts / 1000.0) / max(capacity_kwh, 0.1) * 100.0)
            if soc_per_hour_charge > 0:
                deficit_soc = buffer_required_soc - soc
                required_minutes = int(math.ceil((deficit_soc / soc_per_hour_charge) * 60.0))
                if required_minutes > 0:
                    precharge_until = interval_start + timedelta(minutes=required_minutes)
                    logger.info(
                        "🔋 Pre-sell buffer active: SOC %.1f%% < %.1f%%, adding pre-charge window %d min until %s",
                        soc,
                        buffer_required_soc,
                        required_minutes,
                        precharge_until.astimezone().strftime("%H:%M"),
                    )

    if buffer_required_soc is not None and main_charge_start is not None:
        logger.info(
            "🧮 Sell buffer target %.1f%% for %.2fh discharge before main charge at %s",
            buffer_required_soc,
            buffer_discharge_hours,
            main_charge_start.astimezone().strftime("%H:%M"),
        )

    charge_schedule: List[Dict[str, Any]] = []
    discharge_schedule: List[Dict[str, Any]] = []
    scheduled_discharge_windows = 0
    scheduled_adaptive_windows = 0
    solar_aware_allocation: Optional[SolarAwareChargeAllocation] = None
    solar_aware_remaining_kwh: Optional[float] = None
    solar_charge_deficit_kwh = 0.0

    if precharge_until is not None:
        precharge_minutes = int((precharge_until - interval_start).total_seconds() / 60)
        if precharge_minutes > 0:
            charge_schedule.append({
                "start": interval_start.isoformat(),
                "power": config["power"]["max_charge_power"],
                "duration": precharge_minutes,
                "window_type": "precharge",
            })

    charge_slot_records: List[Dict[str, Any]] = []
    if not skip_charge:
        max_charge_rank = max(top_x_charge_count, 1)
        for window in upcoming_windows["charge"]:
            if len(charge_slot_records) >= MAX_CHARGE_PERIODS:
                break
            for slot in _expand_charge_window_slots(window):
                if len(charge_slot_records) >= MAX_CHARGE_PERIODS:
                    break
                start_dt = slot["start"]
                end_dt = slot["end"]
                if end_dt <= now:
                    continue
                effective_start = max(start_dt, interval_start)
                duration = int((end_dt - effective_start).total_seconds() / 60)
                if duration <= 0:
                    continue
                slot_rank = charge_slot_rank_by_start.get(start_dt.isoformat(), max_charge_rank)
                slot_rank = max(1, min(slot_rank, max_charge_rank))
                slot_power = calculate_rank_scaled_power(
                    slot_rank,
                    max_charge_rank,
                    config["power"]["max_charge_power"],
                    min_scaled_power,
                )
                charge_slot_records.append({
                    "start": effective_start,
                    "end": end_dt,
                    "base_power": slot_power,
                    "duration": duration,
                    "window_type": "charge",
                    "price": round(float(slot.get("price", 0.0)), 4),
                })

    solar_aware_cfg = config.get("solar_aware_charging", {})
    solar_aware_enabled = bool(solar_aware_cfg.get("enabled", True))
    if solar_aware_enabled and charge_slot_records and soc is not None:
        solar_aware_remaining_kwh = _get_remaining_solar_energy_kwh(
            ha_api,
            config.get("entities", {}).get("remaining_solar_energy_entity"),
        )
        solar_charge_deficit_kwh = calculate_charge_deficit_kwh(
            soc,
            float(max_soc),
            float(config["soc"].get("battery_capacity_kwh", 25)),
        )
        today_charge_slot_records = [
            record
            for record in charge_slot_records
            if record["start"].astimezone().date() == now.astimezone().date()
        ]
        if solar_aware_remaining_kwh is not None and solar_charge_deficit_kwh > 0 and today_charge_slot_records:
            solar_aware_allocation = allocate_solar_aware_charge_powers(
                today_charge_slot_records,
                solar_charge_deficit_kwh,
                solar_aware_remaining_kwh,
                int(solar_aware_cfg.get("min_charge_power", 500)),
                float(solar_aware_cfg.get("forecast_safety_factor", 0.8)),
            )
            if solar_aware_allocation.applied:
                logger.info(
                    "☀️ Solar-aware charge planning: deficit %.2fkWh, remaining solar %.2fkWh, usable %.2fkWh, grid target %.2fkWh",
                    solar_charge_deficit_kwh,
                    solar_aware_remaining_kwh,
                    solar_aware_allocation.usable_solar_kwh,
                    solar_aware_allocation.grid_energy_target_kwh,
                )

    for record in charge_slot_records:
        slot_start = record["start"]
        slot_key = slot_start.isoformat()
        slot_power = int(record["base_power"])
        solar_aware = False
        forecast_solar_kwh = None

        if (
            solar_aware_allocation is not None
            and solar_aware_allocation.applied
            and slot_start.astimezone().date() == now.astimezone().date()
        ):
            forecast_solar_kwh = solar_aware_allocation.slot_solar_kwh.get(slot_key)
            if slot_key not in solar_aware_allocation.slot_powers:
                logger.info(
                    "☀️ Skipping grid charge slot %s; remaining solar forecast covers the residual charge target",
                    slot_start.astimezone().strftime("%H:%M"),
                )
                continue
            slot_power = solar_aware_allocation.slot_powers[slot_key]
            solar_aware = True

        charge_schedule.append({
            "start": slot_start.isoformat(),
            "power": slot_power,
            "duration": int(record["duration"]),
            "window_type": record["window_type"],
            "price": record["price"],
            "base_power": int(record["base_power"]),
            "solar_aware": solar_aware,
            "forecast_solar_kwh": forecast_solar_kwh,
        })

    discharge_not_before = interval_start
    if precharge_until is not None:
        discharge_not_before = max(discharge_not_before, precharge_until)
    if sell_wait_decision:
        discharge_not_before = max(discharge_not_before, sell_wait_decision["wait_until"])

    # Combine discharge + adaptive windows into discharge periods.
    # Important: profitable discharge windows are prioritized first so adaptive
    # fillers never crowd out core sell windows when the API period cap applies.
    min_discharge_power = config["power"]["min_discharge_power"]
    discharge_windows_sorted = sorted(
        upcoming_windows.get("discharge", []),
        key=lambda w: (
            -float(w.get("avg_price", 0.0)),
            w.get("start"),
        ),
    )
    discharge_windows_sorted = _filter_supported_discharge_windows(
        discharge_windows_sorted,
        charge_schedule,
        soc,
        config,
        discharge_not_before,
        top_x_discharge_count,
        min_scaled_power,
    )
    discharge_window_rank_by_start: Dict[str, int] = {}
    for idx, window in enumerate(discharge_windows_sorted, start=1):
        start_dt = window.get("start")
        if isinstance(start_dt, datetime):
            discharge_window_rank_by_start[start_dt.isoformat()] = idx

    adaptive_windows_sorted = sorted(
        upcoming_windows.get("adaptive", []),
        key=lambda w: w.get("start"),
    )

    selected_discharge_windows: List[tuple[str, Dict[str, Any]]] = []
    for window in discharge_windows_sorted[:MAX_DISCHARGE_PERIODS]:
        selected_discharge_windows.append(("discharge", window))

    remaining_slots = max(0, MAX_DISCHARGE_PERIODS - len(selected_discharge_windows))
    for window in adaptive_windows_sorted[:remaining_slots]:
        selected_discharge_windows.append(("adaptive", window))

    # Publish in chronological order regardless of selection priority.
    selected_discharge_windows.sort(key=lambda x: x[1]["start"])

    for window_type, window in selected_discharge_windows:
        start_dt = window["start"]
        end_dt = window["end"]
        if end_dt <= now:
            continue
        effective_start = max(start_dt, discharge_not_before)
        duration = int((end_dt - effective_start).total_seconds() / 60)
        if duration <= 0:
            continue
        # Adaptive windows start at minimum power; explicit discharge windows
        # use their own rank-based power and remain stable across monitor ticks.
        if window_type == "discharge":
            window_rank = discharge_window_rank_by_start.get(
                start_dt.isoformat(),
                top_x_discharge_count,
            )
            window_rank = max(1, min(window_rank, max(top_x_discharge_count, 1)))
            power = calculate_rank_scaled_power(
                window_rank,
                max(top_x_discharge_count, 1),
                config["power"]["max_discharge_power"],
                min_scaled_power,
            )
        else:
            power = min_discharge_power
        discharge_schedule.append({
            "start": effective_start.isoformat(),
            "power": power,
            "duration": duration,
            "window_type": window_type,
            "price": round(float(window.get("avg_price", 0.0)), 4),
        })
        if window_type == "discharge":
            scheduled_discharge_windows += 1
        else:
            scheduled_adaptive_windows += 1

    has_active_charge_period = any(_is_period_active(period, now) for period in charge_schedule)
    has_active_discharge_period = any(_is_period_active(period, now) for period in discharge_schedule)
    if (
        adaptive_enabled
        and price_range == "adaptive"
        and not has_active_charge_period
        and not has_active_discharge_period
        and len(discharge_schedule) < MAX_DISCHARGE_PERIODS
    ):
        fallback_duration = int((interval_end - interval_start).total_seconds() / 60)
        if fallback_duration > 0:
            discharge_schedule.insert(
                0,
                {
                    "start": interval_start.isoformat(),
                    "power": min_discharge_power,
                    "duration": fallback_duration,
                    "window_type": "adaptive",
                    "price": round(import_price, 4),
                },
            )
            scheduled_adaptive_windows += 1
            logger.info(
                "⚖️ Added current adaptive window for active price band: %s %dW %dm @€%.3f",
                interval_start.isoformat(),
                min_discharge_power,
                fallback_duration,
                import_price,
            )

    if not charge_schedule and not discharge_schedule:
        if price_range == "passive":
            logger.info("💤 Passive range — price below threshold, battery idle")
        else:
            logger.info("💤 No upcoming charge or discharge windows")

    schedule = {"charge": charge_schedule, "discharge": discharge_schedule}
    active_charge_power = _get_active_period_power(schedule, "charge", now)
    if active_charge_power is None and charge_schedule:
        active_charge_power = int(charge_schedule[0].get("power", config["power"]["max_charge_power"]))
    if active_charge_power is not None:
        charge_power = active_charge_power

    published = _publish_schedule(mqtt_client, schedule, is_dry_run, state=state, force=True)
    if not published and not is_dry_run:
        logger.warning("⚠️ Schedule was NOT delivered to battery-api — will retry next cycle")
    api_payload = _format_schedule_for_api(schedule)
    api_charge_count = len(api_payload.get("charge", []))
    api_discharge_count = len(api_payload.get("discharge", []))
    logger.info(
        "✅ Multi-period schedule: %s range | internal charge=%d discharge=%d adaptive=%d | api(local-day) charge=%d discharge=%d",
        price_range,
        len(schedule["charge"]),
        scheduled_discharge_windows,
        scheduled_adaptive_windows,
        api_charge_count,
        api_discharge_count,
    )
    for i, p in enumerate(schedule["charge"]):
        window_type = p.get("window_type", "charge")
        price = p.get("price")
        solar_aware_text = ""
        if p.get("solar_aware"):
            forecast_kwh = p.get("forecast_solar_kwh")
            base_power = p.get("base_power")
            solar_aware_text = (
                f" | solar-aware base={int(base_power)}W forecast={float(forecast_kwh):.2f}kWh"
                if forecast_kwh is not None and base_power is not None
                else " | solar-aware"
            )
        if price is None:
            logger.info(
                "   charge[%d] (%s): %s %dW %dm%s",
                i,
                window_type,
                p["start"],
                p["power"],
                p["duration"],
                solar_aware_text,
            )
        else:
            logger.info(
                "   charge[%d] (%s): %s %dW %dm @€%.3f%s",
                i,
                window_type,
                p["start"],
                p["power"],
                p["duration"],
                float(price),
                solar_aware_text,
            )
    for i, p in enumerate(schedule["discharge"]):
        window_type = p.get("window_type", "discharge")
        price = p.get("price")
        logger.info(
            "   %s[%d]: %s %dW %dm%s",
            window_type,
            i,
            p["start"],
            p["power"],
            p["duration"],
            f" @€{float(price):.3f}" if price is not None else "",
        )

    action_labels = {
        "load": f"Charging {charge_power}W",
        "discharge": f"Discharging {discharge_power}W",
        "adaptive": f"Adaptive (discharge to 0W export)",
        "passive": "Passive (battery idle)",
    }
    action_state = action_labels.get(price_range, price_range)
    if (
        price_range == "load"
        and not charge_schedule
        and solar_aware_allocation is not None
        and solar_aware_allocation.applied
    ):
        action_state = "Solar-aware (no grid charge needed)"

    action_attributes = {
        "price_range": price_range,
        "import_price": import_price,
        "export_price": export_price,
        "charge_power": charge_power if price_range == "load" else None,
        "discharge_power": discharge_power if price_range != "load" else None,
        "interval_minutes": interval_minutes,
    }
    if solar_aware_allocation is not None and solar_aware_allocation.applied:
        action_attributes.update({
            "solar_aware_charging": True,
            "remaining_solar_energy_kwh": solar_aware_remaining_kwh,
            "charge_deficit_kwh": round(solar_charge_deficit_kwh, 3),
            "usable_remaining_solar_kwh": solar_aware_allocation.usable_solar_kwh,
            "grid_charge_target_kwh": solar_aware_allocation.grid_energy_target_kwh,
        })

    update_entity(
        mqtt_client,
        ENTITY_CURRENT_ACTION,
        action_state,
        action_attributes,
        dry_run=is_dry_run,
    )

    # Build full-day schedule from price curve windows
    upcoming_windows = find_upcoming_windows(
        import_curve, export_curve, load_range, discharge_range,
        adaptive_price_threshold, now,
        tomorrow_load_range=tomorrow_load,
        tomorrow_discharge_range=tomorrow_discharge,
        discharge_slot_starts=today_discharge_slot_starts,
        tomorrow_discharge_slot_starts=tomorrow_discharge_slot_starts,
        adaptive_enabled=adaptive_enabled,
    )

    # Determine informative messages when ranges don't exist
    discharge_no_range_msg = None
    if discharge_range is None and load_range is not None:
        spread = max(p.get("price", 0) for p in export_curve) - min(p.get("price", 999) for p in import_curve)
        discharge_no_range_msg = f"📉 No profitable discharge today (spread €{spread:.3f} < €{min_profit:.2f} minimum)"

    # Update ENTITY_CHARGE_SCHEDULE with HA state length protection
    display_windows = _build_display_windows_from_schedule(schedule)

    charge_text = build_windows_display(display_windows["charge"], "charge", charge_power, now)
    charge_state = charge_text
    if len(charge_state) > 255:
        count = len(display_windows["charge"])
        charge_state = f"{count} charge windows planned"

    update_entity(
        mqtt_client,
        ENTITY_CHARGE_SCHEDULE,
        charge_state,
        {
            "windows": _serialize_windows(display_windows["charge"]),
            "markdown": charge_text,
        },
        dry_run=is_dry_run,
    )

    # Update ENTITY_DISCHARGE_SCHEDULE with HA state length protection
    discharge_text = build_windows_display(upcoming_windows["discharge"], "discharge", discharge_power, now, discharge_no_range_msg)
    discharge_state = discharge_text
    if len(discharge_state) > 255:
        count = len(upcoming_windows["discharge"])
        discharge_state = f"{count} discharge windows planned"

    update_entity(
        mqtt_client,
        ENTITY_DISCHARGE_SCHEDULE,
        discharge_state,
        {
            "windows": _serialize_windows(upcoming_windows["discharge"]),
            "markdown": discharge_text,
        },
        dry_run=is_dry_run,
    )

    # Update ENTITY_SCHEDULE with HA state length protection (split to _2)
    # Use the generated schedule payload (not full-day candidate windows)
    # so the table always matches what was actually published.
    combined_text = build_combined_schedule_display(
        display_windows,
        charge_power,
        config["power"]["max_discharge_power"],
        now,
        discharge_no_range_msg,
        adaptive_power=config["power"].get("min_discharge_power", 0),
    )

    schedule_1, schedule_2 = _split_state_for_ha(combined_text)

    update_entity(
        mqtt_client,
        ENTITY_SCHEDULE,
        schedule_1,
        {"markdown": combined_text},
        dry_run=is_dry_run,
    )
    
    update_entity(
        mqtt_client,
        ENTITY_SCHEDULE_2,
        schedule_2,
        dry_run=is_dry_run,
    )

    return schedule


def monitor_and_adjust_active_period(
    config: Dict[str, Any],
    ha_api: HomeAssistantApi,
    mqtt_client: Any,
    state: RuntimeState,
    solar_monitor: SolarMonitor,
    gap_scheduler: GapScheduler,
) -> None:
    logger.debug("🔍 Monitoring active period...")
    now = datetime.now(timezone.utc)
    soc_entity = config["entities"]["soc_entity"]
    grid_entity = config["entities"]["grid_power_entity"]
    solar_entity = config["entities"]["solar_power_entity"]
    load_entity = config["entities"]["house_load_entity"]
    batt_entity = config["entities"].get("battery_power_entity")

    # Dry run check
    is_dry_run = config.get("dry_run", False)

    soc, soc_age_seconds = _get_sensor_float_and_age_seconds(ha_api, soc_entity, now)
    grid_power = _get_sensor_float(ha_api, grid_entity)
    solar_power = _get_sensor_float(ha_api, solar_entity)
    house_load = _get_sensor_float(ha_api, load_entity)
    batt_power = _get_sensor_float(ha_api, batt_entity) if batt_entity else None

    ev_power = None
    ev_age_seconds = None
    if config["ev_charger"]["enabled"]:
        ev_power, ev_age_seconds = _get_sensor_float_and_age_seconds(
            ha_api,
            config["ev_charger"]["entity_id"],
            now,
        )
        max_ev_sensor_age = max(
            0,
            int(config.get("timing", {}).get("max_ev_sensor_age_seconds", 180)),
        )
        if ev_age_seconds is not None and max_ev_sensor_age > 0 and ev_age_seconds > max_ev_sensor_age:
            if not state.warned_stale_ev:
                logger.warning(
                    "⚠️ EV charger sensor stale (age %.0fs > %ss), ignoring EV charging hold",
                    ev_age_seconds,
                    max_ev_sensor_age,
                )
                state.warned_stale_ev = True
            ev_power = None
        elif ev_power is not None:
            state.warned_stale_ev = False

        if ev_power is None:
            if ev_age_seconds is None and not state.warned_missing_ev:
                logger.warning("⚠️ EV charger sensor unavailable, skipping EV integration")
                state.warned_missing_ev = True
        else:
            state.warned_missing_ev = False

    max_soc_sensor_age = max(0, int(config.get("timing", {}).get("max_soc_sensor_age_seconds", 900)))
    if soc_age_seconds is not None and max_soc_sensor_age > 0 and soc_age_seconds > max_soc_sensor_age:
        if not state.warned_stale_soc:
            logger.warning(
                "⚠️ SOC sensor stale (age %.0fs > %ss), forcing protective pause behavior",
                soc_age_seconds,
                max_soc_sensor_age,
            )
            state.warned_stale_soc = True
        soc = None
    elif soc is not None:
        state.warned_stale_soc = False

    if soc is None and not state.warned_missing_soc:
        logger.warning("⚠️ SOC sensor unavailable or invalid, forcing protective pause behavior")
        state.warned_missing_soc = True
    elif soc is not None:
        state.warned_missing_soc = False

    _log_sensor_snapshot(soc, grid_power, solar_power, house_load, batt_power, ev_power)

    if grid_power is None and not state.warned_missing_grid:
        logger.warning("⚠️ Grid power sensor unavailable, skipping export prevention")
        state.warned_missing_grid = True

    if (solar_power is None or house_load is None) and not state.warned_missing_solar:
        logger.warning("⚠️ Solar sensors unavailable, skipping opportunistic charging")
        state.warned_missing_solar = True

    passive_active = solar_monitor.check_passive_state(ha_api)

    effective_schedule = state.published_schedule or state.schedule
    active_discharge_period = next(
        (period for period in effective_schedule.get("discharge", []) if _is_period_active(period, now)),
        None,
    )
    active_charge_period = next(
        (period for period in effective_schedule.get("charge", []) if _is_period_active(period, now)),
        None,
    )
    active_discharge = active_discharge_period is not None
    active_charge = active_charge_period is not None

    import_curve = (
        _get_price_curve(ha_api, config["entities"]["price_curve_entity"]) or state.last_price_curve
    )
    export_curve = (
        _get_export_price_curve(ha_api, config["entities"]["export_price_curve_entity"])
        or import_curve
    )

    interval_minutes = detect_interval_minutes(import_curve or [])
    top_x_charge_count = calculate_top_x_count(
        config["heuristics"]["top_x_charge_hours"], interval_minutes
    )

    # Always fetch temperature for status logging and potential heuristics
    temperature = _get_sensor_float(ha_api, config["entities"]["temperature_entity"])

    top_x_discharge_hours = config["heuristics"]["top_x_discharge_hours"]
    if config["temperature_based_discharge"]["enabled"]:
        top_x_discharge_hours = get_discharge_hours(
            temperature,
            config["temperature_based_discharge"]["thresholds"],
        )
    top_x_discharge_count = calculate_discharge_top_x_count(top_x_discharge_hours, interval_minutes)

    min_profit = config["heuristics"].get("min_profit_threshold", 0.1)
    today_import, _ = _split_curve_by_date(import_curve or [], now)
    today_export, _ = _split_curve_by_date(export_curve or [], now)
    range_import_curve = today_import if today_import else (import_curve or [])
    range_export_curve = today_export if today_export else (export_curve or import_curve or [])

    load_range, discharge_range, adaptive_range = calculate_price_ranges(
        range_import_curve,
        range_export_curve,
        top_x_charge_count,
        top_x_discharge_count,
        min_profit,
    )
    if not config.get("adaptive", {}).get("enabled", True):
        adaptive_range = None

    current_import_entry = (
        get_current_price_entry(import_curve or [], now, interval_minutes) if import_curve else None
    )
    current_export_entry = (
        get_current_price_entry(export_curve or [], now, interval_minutes) if export_curve else None
    )

    if current_import_entry:
        import_price = float(current_import_entry.get("price", 0.0))
    else:
        import_price = 0.0

    export_price = (
        float(current_export_entry.get("price", import_price))
        if current_export_entry
        else import_price
    )
    adaptive_price_threshold = config["heuristics"].get("adaptive_price_threshold")
    adaptive_enabled = config.get("adaptive", {}).get("enabled", True)
    price_range = _determine_price_range(
        import_price, export_price, load_range, discharge_range,
        adaptive_price_threshold,
        adaptive_enabled=adaptive_enabled,
    )
    runtime_price_range = price_range
    conservative_soc = config["soc"]["conservative_soc"]
    max_soc = float(config["soc"].get("max_soc", 100))
    if soc is not None and soc <= conservative_soc and runtime_price_range == "discharge":
        runtime_price_range = "adaptive"
    if active_discharge_period and active_discharge_period.get("window_type") == "adaptive":
        runtime_price_range = "adaptive"

    if state.last_price_range != runtime_price_range:
        _publish_price_ranges(
            mqtt_client,
            load_range,
            discharge_range,
            adaptive_range,
            adaptive_price_threshold,
            is_dry_run,
        )
        state.last_price_range = runtime_price_range

    # Update "Today's Energy Market" every cycle so the "📍 Now" line stays current
    reasoning_text = build_today_story(
        runtime_price_range, import_price, export_price,
        load_range, discharge_range, adaptive_range,
        config["heuristics"].get("adaptive_price_threshold"), now,
    )
    update_entity(mqtt_client, ENTITY_REASONING, reasoning_text,
                  {"price_range": runtime_price_range, "import_price": import_price, "export_price": export_price},
                  dry_run=is_dry_run)

    regen_cooldown = config["timing"].get("schedule_regen_cooldown_seconds", 60)
    regen_price_range = _should_regenerate_live_schedule(
        runtime_price_range,
        active_charge,
        active_discharge,
        import_curve,
        soc,
        config,
    )
    if regen_price_range is not None:
        if (
            not state.last_schedule_publish
            or (now - state.last_schedule_publish).total_seconds() >= regen_cooldown
        ):
            logger.info(
                "🔄 Live %s price band has no active window - regenerating rolling schedule",
                regen_price_range,
            )
            state.schedule = generate_schedule(config, ha_api, mqtt_client, state)
            state.schedule_generated_at = now
            state.last_schedule_publish = now
            return

    should_pause = False
    reduce_discharge = False
    pause_reasons: List[str] = []
    reduce_reasons: List[str] = []

    if config["ev_charger"]["enabled"]:
        ev_threshold = config["ev_charger"]["charging_threshold"]
        if should_pause_discharge(ev_power, ev_threshold):
            should_pause = True
            pause_reasons.append(f"EV Charging >{ev_threshold}W")

    if soc is None:
        if active_discharge:
            should_pause = True
            pause_reasons.append("SOC unavailable/stale")
    else:
        min_soc = config["soc"]["min_soc"]
        dynamic_buffer_soc = state.sell_buffer_required_soc
        low_soc_discharge_mode = active_discharge and soc <= conservative_soc
        # Sell-buffer floor protects planned precharge strategy in non-sell modes only.
        use_sell_buffer_protection = runtime_price_range != "discharge" and not low_soc_discharge_mode
        effective_min_soc = (
            max(min_soc, dynamic_buffer_soc)
            if dynamic_buffer_soc is not None and use_sell_buffer_protection
            else min_soc
        )
        # During active low-SOC discharge we switch to adaptive runtime behavior
        # instead of hard-pausing based on conservative threshold.
        is_conservative = runtime_price_range != "discharge" and not low_soc_discharge_mode
        if not can_discharge(soc, effective_min_soc, conservative_soc, is_conservative):
            should_pause = True
            if use_sell_buffer_protection and dynamic_buffer_soc is not None and effective_min_soc > min_soc:
                pause_reasons.append(
                    f"SOC sell-buffer protection ({soc:.1f}% < {effective_min_soc:.1f}%)"
                )
            else:
                pause_reasons.append(f"SOC protection ({soc:.1f}%)")

        if low_soc_discharge_mode and not should_pause:
            reduce_discharge = True
            reduce_reasons.append(
                f"SOC <= conservative ({soc:.1f}% <= {conservative_soc:.1f}%), switching to adaptive discharge"
            )

    stabilizer_active = (
        state.max_soc_stabilizer_until is not None
        and now < state.max_soc_stabilizer_until
    )
    stabilizer_floor = max_soc - MAX_SOC_STABILIZER_HYSTERESIS_PCT

    if stabilizer_active:
        if should_pause or reduce_discharge or (soc is not None and soc < stabilizer_floor):
            logger.info("🟢 Max-SOC stabilizer cleared - restoring generated schedule")
            _publish_schedule(mqtt_client, state.schedule, is_dry_run, state=state, force=True)
            state.max_soc_stabilizer_until = None
            state.last_effective_discharge_power = None
            _update_effective_discharge_power(
                mqtt_client,
                None,
                is_dry_run,
                price_range=runtime_price_range,
                effective_price_range="idle",
                soc=soc,
                grid_power=grid_power,
            )
            stabilizer_active = False
        else:
            if state.passive_gap_active:
                state.passive_gap_active = False
            stabilizer_power = _get_max_soc_stabilizer_power(config)
            remaining_minutes = max(
                1,
                int(math.ceil((state.max_soc_stabilizer_until - now).total_seconds() / 60.0)),
            )
            _update_mode_entity(
                mqtt_client,
                state,
                "max_soc_stabilizer",
                is_dry_run,
                price_range=runtime_price_range,
            )
            status_msg = build_status_message(
                runtime_price_range, False, True, None, stabilizer_power, temperature,
            )
            update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
            update_entity(
                mqtt_client,
                ENTITY_CURRENT_ACTION,
                f"Max SOC stabilizing {stabilizer_power}W",
                {
                    "price_range": runtime_price_range,
                    "effective_price_range": "max_soc_stabilizer",
                    "discharge_power": stabilizer_power,
                    "remaining_minutes": remaining_minutes,
                    "soc": soc,
                },
                dry_run=is_dry_run,
            )
            _update_effective_discharge_power(
                mqtt_client,
                stabilizer_power,
                is_dry_run,
                active_window_type="max_soc_stabilizer",
                price_range=runtime_price_range,
                effective_price_range="max_soc_stabilizer",
                soc=soc,
                grid_power=grid_power,
            )
            return

    should_start_max_soc_stabilizer = (
        soc is not None
        and soc >= max_soc
        and not active_discharge
        and not should_pause
        and not reduce_discharge
    )
    if should_start_max_soc_stabilizer:
        if state.passive_gap_active:
            logger.info("🛡️ Max-SOC stabilizer overriding Passive Solar gap schedule")
            state.passive_gap_active = False
        stabilizer_power = _get_max_soc_stabilizer_power(config)
        override = _build_max_soc_stabilizer_schedule(
            now,
            stabilizer_power,
            MAX_SOC_STABILIZER_MINUTES,
        )
        _publish_schedule(mqtt_client, override, is_dry_run, state=state, force=True)
        state.max_soc_stabilizer_until = now + timedelta(minutes=MAX_SOC_STABILIZER_MINUTES)
        state.last_effective_discharge_power = stabilizer_power
        _update_mode_entity(
            mqtt_client,
            state,
            "max_soc_stabilizer",
            is_dry_run,
            price_range=runtime_price_range,
        )
        status_msg = build_status_message(
            runtime_price_range, False, True, None, stabilizer_power, temperature,
        )
        update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
        update_entity(
            mqtt_client,
            ENTITY_CURRENT_ACTION,
            f"Max SOC stabilizing {stabilizer_power}W",
            {
                "price_range": runtime_price_range,
                "effective_price_range": "max_soc_stabilizer",
                "discharge_power": stabilizer_power,
                "duration_minutes": MAX_SOC_STABILIZER_MINUTES,
                "soc": soc,
            },
            dry_run=is_dry_run,
        )
        _update_effective_discharge_power(
            mqtt_client,
            stabilizer_power,
            is_dry_run,
            active_window_type="max_soc_stabilizer",
            price_range=runtime_price_range,
            effective_price_range="max_soc_stabilizer",
            soc=soc,
            grid_power=grid_power,
        )
        return

    if passive_active:
        if not state.passive_gap_active:
            logger.info("☀️ Passive Solar Mode is ACTIVE (0W Charge Gap)")
            gap_schedule = gap_scheduler.generate_passive_gap_schedule()
            _publish_schedule(mqtt_client, gap_schedule, is_dry_run, state=state, force=True)
            state.passive_gap_active = True
        state.last_effective_discharge_power = 0
        _update_mode_entity(
            mqtt_client,
            state,
            "passive_solar",
            is_dry_run,
            price_range="passive",
        )
        update_entity(
            mqtt_client,
            ENTITY_CURRENT_ACTION,
            "Passive Solar (0W charge gap)",
            {"status": "active", "gap_schedule": True},
            dry_run=is_dry_run,
        )
        _update_effective_discharge_power(
            mqtt_client,
            0,
            is_dry_run,
            active_window_type="passive_gap",
            price_range="passive",
            effective_price_range="passive_gap",
            soc=soc,
            grid_power=grid_power,
        )
        return

    if state.passive_gap_active:
        logger.info("☁️ Passive Solar Mode cleared - restoring generated schedule")
        _publish_schedule(mqtt_client, state.schedule, is_dry_run, state=state, force=True)
        state.passive_gap_active = False
        state.last_monitor_status = None

    status_parts = []
    if active_charge:
        status_parts.append("✅ Charging")
    elif active_discharge:
        status_parts.append("✅ Discharging")
    else:
        status_parts.append("💤 Idle")

    if temperature is not None:
        icon = get_temperature_icon(temperature)
        status_parts.append(f"{icon} {temperature}°C")

    # Build a status key to detect state changes and suppress repeat log lines
    if active_discharge and should_pause:
        monitor_status = f"paused:{','.join(pause_reasons)}"
    elif active_discharge and reduce_discharge:
        monitor_status = f"reduced:{','.join(reduce_reasons)}"
    elif active_charge:
        monitor_status = f"charging:{runtime_price_range}"
    elif active_discharge:
        monitor_status = f"discharging:{runtime_price_range}"
    else:
        monitor_status = f"idle:{runtime_price_range}"

    status_changed = monitor_status != state.last_monitor_status
    if status_changed:
        state.last_monitor_status = monitor_status
        # Log sensor values on state transitions at INFO for context
        _log_sensor_snapshot(
            soc,
            grid_power,
            solar_power,
            house_load,
            batt_power,
            ev_power,
            level=logging.INFO,
        )

    if active_discharge and should_pause:
        if status_changed:
            logger.info("%s | 🛑 Paused | Reasons: %s", " | ".join(status_parts), ", ".join(pause_reasons))
    elif active_discharge and reduce_discharge:
        if status_changed:
            logger.info("%s | 🟡 Reduced | Reasons: %s", " | ".join(status_parts), ", ".join(reduce_reasons))
    elif active_charge or active_discharge:
        if status_changed:
            logger.info("%s | Active | Mode: %s", " | ".join(status_parts), runtime_price_range)
    else:
        if status_changed:
            logger.info("%s", " | ".join(status_parts))

    active_window_type = active_discharge_period.get("window_type", "discharge") if active_discharge_period else None
    if active_charge:
        effective_mode = "load"
    elif active_discharge and should_pause:
        effective_mode = "paused"
    elif active_discharge and (reduce_discharge or active_window_type == "adaptive"):
        effective_mode = "adaptive"
    elif active_discharge:
        effective_mode = "discharge"
    elif runtime_price_range == "passive":
        effective_mode = "passive"
    else:
        effective_mode = "idle"

    _update_mode_entity(
        mqtt_client,
        state,
        effective_mode,
        is_dry_run,
        price_range=runtime_price_range,
    )

    if state.reduced_override_active and not reduce_discharge and not should_pause:
        logger.info("🟢 Reduced mode cleared - restoring scheduled discharge power")
        _publish_schedule(mqtt_client, state.schedule, is_dry_run, state=state, force=True)
        state.reduced_override_active = False

    if active_discharge and (should_pause or reduce_discharge):
        if reduce_discharge and not should_pause:
            adaptive_grace = config["timing"].get("adaptive_power_grace_seconds", 60)
            max_power = config["power"]["max_discharge_power"]
            min_power = config["power"]["min_discharge_power"]

            # Keep using the last command briefly to avoid reacting to lagging
            # battery power telemetry while reduced/adaptive mode is active.
            if (
                state.last_effective_discharge_power is not None
                and state.last_power_adjustment is not None
                and (now - state.last_power_adjustment).total_seconds() < adaptive_grace * 2
            ):
                current_power = state.last_effective_discharge_power
            else:
                current_power = int(batt_power) if batt_power is not None else min_power

            current_power = max(0, min(int(current_power), max_power))

            target_power = _calculate_adaptive_power(
                grid_power,
                current_power,
                min_power,
                max_power,
            )
            if target_power is not None and soc is not None and soc <= 50:
                target_power = min(target_power, int(max_power / 2))

            adaptive_power = current_power
            if target_power is not None:
                if (
                    state.last_power_adjustment
                    and (now - state.last_power_adjustment).total_seconds() < adaptive_grace
                ):
                    adaptive_power = current_power
                else:
                    adaptive_power = target_power
                    if adaptive_power != current_power:
                        state.last_power_adjustment = now

            adaptive_power = max(min_power, min(int(adaptive_power), max_power))

            reduced = []
            for period in state.schedule.get("discharge", []):
                if _is_period_active(period, now):
                    reduced.append(
                        {
                            **period,
                            "power": adaptive_power,
                            "window_type": "adaptive",
                        }
                    )
                else:
                    reduced.append(period)

            override = {"charge": state.schedule.get("charge", []), "discharge": reduced}
            _publish_schedule(mqtt_client, override, is_dry_run, state=state)
            state.reduced_override_active = True
            state.last_effective_discharge_power = adaptive_power
            update_entity(
                mqtt_client,
                ENTITY_CURRENT_ACTION,
                f"Adaptive Discharging {adaptive_power}W",
                {
                    "price_range": runtime_price_range,
                    "effective_price_range": "adaptive",
                    "target_power": adaptive_power,
                    "current_power": current_power,
                    "grid_power": grid_power,
                    "soc": soc,
                },
                dry_run=is_dry_run,
            )
            _update_effective_discharge_power(
                mqtt_client,
                adaptive_power,
                is_dry_run,
                active_window_type="adaptive",
                price_range=runtime_price_range,
                effective_price_range="adaptive",
                soc=soc,
                grid_power=grid_power,
            )
            status_msg = build_status_message(
                runtime_price_range, False, True, None, None, temperature,
                reduced=True, pause_reason=", ".join(reduce_reasons),
            )
            update_entity(
                mqtt_client, ENTITY_STATUS, status_msg, {"reason": "conservative_soc_adaptive"}, dry_run=is_dry_run,
            )
            return

        override = {"charge": state.schedule.get("charge", []), "discharge": []}
        _publish_schedule(mqtt_client, override, is_dry_run, state=state)
        state.reduced_override_active = False
        status_msg = build_status_message(
            runtime_price_range, False, False, None, None, temperature,
            paused=True, pause_reason=", ".join(pause_reasons),
        )
        update_entity(
            mqtt_client, ENTITY_STATUS, status_msg, {"reason": "override"}, dry_run=is_dry_run,
        )
        state.last_effective_discharge_power = 0
        _update_effective_discharge_power(
            mqtt_client,
            0,
            is_dry_run,
            active_window_type="paused",
            price_range=runtime_price_range,
            effective_price_range="paused",
            soc=soc,
            grid_power=grid_power,
        )
    else:
        if active_charge:
            charge_power_val = int(active_charge_period.get("power", 0)) if active_charge_period else _get_active_period_power(effective_schedule, "charge", now)
            status_msg = build_status_message(
                runtime_price_range, True, False, charge_power_val, None, temperature,
            )
            update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
            update_entity(
                mqtt_client,
                ENTITY_CURRENT_ACTION,
                f"Charging {charge_power_val}W" if charge_power_val else "Charging",
                {
                    "price_range": runtime_price_range,
                    "effective_price_range": runtime_price_range,
                    "charge_power": charge_power_val,
                    "soc": soc,
                },
                dry_run=is_dry_run,
            )
            state.last_effective_discharge_power = 0
            _update_effective_discharge_power(
                mqtt_client,
                0,
                is_dry_run,
                active_window_type="charge",
                price_range=runtime_price_range,
                effective_price_range=runtime_price_range,
                soc=soc,
                grid_power=grid_power,
            )
        elif active_discharge:
            discharge_power_val = int(active_discharge_period.get("power", 0)) if active_discharge_period else _get_active_period_power(effective_schedule, "discharge", now)
            status_msg = build_status_message(
                runtime_price_range, False, True, None, discharge_power_val, temperature,
            )
            update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
            action_label = f"Discharging {discharge_power_val}W" if discharge_power_val else "Discharging"
            if runtime_price_range == "adaptive":
                action_label = f"Adaptive {discharge_power_val}W" if discharge_power_val else "Adaptive (matching grid)"
            update_entity(
                mqtt_client,
                ENTITY_CURRENT_ACTION,
                action_label,
                {
                    "price_range": runtime_price_range,
                    "active_window_type": active_discharge_period.get("window_type", runtime_price_range) if active_discharge_period else runtime_price_range,
                    "discharge_power": discharge_power_val,
                    "soc": soc,
                },
                dry_run=is_dry_run,
            )
            state.last_effective_discharge_power = discharge_power_val
            _update_effective_discharge_power(
                mqtt_client,
                discharge_power_val,
                is_dry_run,
                active_window_type=active_discharge_period.get("window_type", runtime_price_range) if active_discharge_period else runtime_price_range,
                price_range=runtime_price_range,
                effective_price_range=runtime_price_range,
                soc=soc,
                grid_power=grid_power,
            )
        else:
            status_msg = build_status_message(
                runtime_price_range, False, False, None, None, temperature,
            )
            update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
            next_event_summary = build_next_event_summary(effective_schedule, now, temperature)
            idle_labels = {
                "passive": "Passive (battery idle)",
                "adaptive": "Idle (adaptive price, no active window)",
                "load": "Waiting (charge window pending)",
            }
            idle_action = (
                f"Idle | {next_event_summary}"
                if next_event_summary != "No upcoming events" and not next_event_summary.startswith("No upcoming")
                else idle_labels.get(runtime_price_range, f"Idle ({runtime_price_range})")
            )
            update_entity(
                mqtt_client,
                ENTITY_CURRENT_ACTION,
                idle_action,
                {
                    "price_range": runtime_price_range,
                    "soc": soc,
                    "next_event": next_event_summary,
                },
                dry_run=is_dry_run,
            )
            state.last_effective_discharge_power = 0
            _update_effective_discharge_power(
                mqtt_client,
                0,
                is_dry_run,
                active_window_type="none",
                price_range=runtime_price_range,
                effective_price_range=runtime_price_range,
                soc=soc,
                grid_power=grid_power,
            )

    if active_discharge and not should_pause:
        discharge_periods = effective_schedule.get("discharge", [])
        active_period = active_discharge_period

        scheduled_power = int(active_period.get("power", 0)) if active_period else 0
        active_window_type = active_period.get("window_type", "discharge") if active_period else "discharge"
        adaptive_grace = config["timing"].get("adaptive_power_grace_seconds", 60)

        # Use the last commanded power if a recent adjustment was made,
        # because the battery sensor lags behind the commanded value
        # and causes overshoot oscillation.
        if (
            state.last_effective_discharge_power is not None
            and state.last_power_adjustment is not None
            and (now - state.last_power_adjustment).total_seconds() < adaptive_grace * 2
        ):
            current_power = state.last_effective_discharge_power
        else:
            current_power = int(batt_power) if batt_power is not None else scheduled_power

        # Keep runtime adjustments aligned with the active window type, not just
        # the broad price range. Explicit discharge windows must keep scheduled
        # power, while adaptive windows can be adjusted.
        effective_range = "adaptive" if active_window_type == "adaptive" else "discharge"

        max_power = config["power"]["max_discharge_power"]

        target_power: Optional[int] = None
        if effective_range == "adaptive":
            target_power = _calculate_adaptive_power(
                grid_power,
                current_power,
                config["power"]["min_discharge_power"],
                max_power,
            )
            if target_power is not None and soc is not None and soc <= 50:
                cap = int(max_power / 2)
                if target_power > cap:
                    target_power = cap

        if target_power is not None and active_period:
            if (
                state.last_power_adjustment
                and (now - state.last_power_adjustment).total_seconds() < adaptive_grace
            ):
                logger.info("⏱️ Adaptive adjustment skipped (grace period active)")
            elif target_power != current_power:
                delta = target_power - current_power
                delta_str = f"+{delta}" if delta > 0 else f"{delta}"

                logger.info(
                    "Power adjustment applied: %sW (%sW)",
                    target_power,
                    delta_str,
                )
                # Keep original schedule times — only change power to avoid
                # timing mismatches that cause the inverter to toggle on/off
                updated = []
                for period in discharge_periods:
                    if period is active_period:
                        updated.append({**period, "power": target_power})
                    else:
                        updated.append(period)
                override = {"charge": state.schedule.get("charge", []), "discharge": updated}
                _publish_schedule(mqtt_client, override, is_dry_run, state=state)
                state.last_power_adjustment = now
                state.last_effective_discharge_power = target_power
                update_entity(
                    mqtt_client,
                    ENTITY_CURRENT_ACTION,
                    f"Adaptive {target_power}W",
                    {
                        "target_power": target_power,
                        "current_power": current_power,
                        "grid_power": grid_power,
                        "range": effective_range,
                    },
                    dry_run=is_dry_run,
                )
                _update_effective_discharge_power(
                    mqtt_client,
                    target_power,
                    is_dry_run,
                    active_window_type=active_window_type,
                    price_range=runtime_price_range,
                    effective_price_range=effective_range,
                    soc=soc,
                    grid_power=grid_power,
                )

        if (
            effective_range == "adaptive"
            and current_power == 0
            and grid_power is not None
            and grid_power < -1000
            and soc is not None
            and soc < 99
        ):
            update_entity(
                mqtt_client,
                ENTITY_CURRENT_ACTION,
                f"Opportunistic Solar ({abs(grid_power):.0f}W excess)",
                {"excess_solar": abs(grid_power), "soc": soc},
                dry_run=is_dry_run,
            )

def main() -> int:
    logger.info("Battery Manager add-on starting...")

    shutdown_event = setup_signal_handlers(logger)
    config = _load_config()

    if not config.get("enabled", True):
        logger.info("Battery Manager disabled via configuration, exiting")
        return 0

    if config.get("dry_run", False):
        logger.info("📝 Dry-run mode enabled - actions will be logged only")
        logger.info("   Entities configured:")
        for key, entity_id in config.get("entities", {}).items():
            logger.info("   - %s: %s", key, entity_id)

    ha_api = HomeAssistantApi()

    mqtt_client = setup_mqtt_client(
        addon_name="Battery Manager",
        addon_id="battery_manager",
        config=config,
        manufacturer="HA Addons",
        model="Battery Manager",
    )

    if mqtt_client:
        publish_all_entities(mqtt_client)

    # Initialize helpers
    solar_monitor = SolarMonitor(config, logger)
    gap_scheduler = GapScheduler(logger)

    # Initialize runtime state
    state = RuntimeState(
        schedule={"charge": [], "discharge": []}, schedule_generated_at=None
    )

    run_once = get_run_once_mode()

    def schedule_task():
        state.schedule = generate_schedule(config, ha_api, mqtt_client, state)
        state.schedule_generated_at = datetime.now(timezone.utc)
        state.last_schedule_publish = state.schedule_generated_at

    # Initial schedule generation
    schedule_task()

    while not shutdown_event.is_set():
        try:
            monitor_and_adjust_active_period(
                config, ha_api, mqtt_client, state, solar_monitor, gap_scheduler
            )
        except Exception as exc:
            logger.error("Monitoring loop error: %s", exc, exc_info=True)

        if run_once:
            logger.info("RUN_ONCE mode complete, exiting")
            break

        if state.schedule_generated_at:
            elapsed = (datetime.now(timezone.utc) - state.schedule_generated_at).total_seconds()
            if elapsed >= config["timing"]["update_interval"]:
                schedule_task()

        # Detect tomorrow's prices arriving (curve grows by 12+ entries)
        import_entity = config["entities"]["price_curve_entity"]
        cur_curve = _get_price_curve(ha_api, import_entity)
        if cur_curve and state.last_curve_length > 0:
            if len(cur_curve) >= state.last_curve_length + 12:
                logger.info("📈 Tomorrow prices detected (%d → %d entries) — regenerating schedule",
                            state.last_curve_length, len(cur_curve))
                schedule_task()

        if not sleep_with_shutdown_check(shutdown_event, config["timing"]["monitor_interval"]):
            break

    if mqtt_client:
        mqtt_client.disconnect()

    logger.info("Battery Manager add-on stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
