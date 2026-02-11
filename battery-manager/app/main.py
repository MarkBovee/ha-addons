"""Battery Manager add-on main entry point."""

from __future__ import annotations

import json
import logging
import os
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
from .grid_monitor import should_reduce_discharge
from .power_calculator import calculate_rank_scaled_power
from .price_analyzer import (
    PriceRange,
    calculate_price_ranges,
    calculate_top_x_count,
    detect_interval_minutes,
    get_current_period_rank,
    get_current_price_entry,
)
from .schedule_builder import build_charge_schedule, build_discharge_schedule, merge_schedules
from .schedule_publisher import publish_to_mqtt
from .solar_monitor import SolarMonitor
from .gap_scheduler import GapScheduler
from .soc_guardian import can_charge, can_discharge
from .temperature_advisor import get_discharge_hours
from .status_reporter import (
    ENTITY_CHARGE_SCHEDULE,
    ENTITY_CURRENT_ACTION,
    ENTITY_DISCHARGE_SCHEDULE,
    ENTITY_FORECAST,
    ENTITY_MODE,
    ENTITY_PRICE_RANGES,
    ENTITY_REASONING,
    ENTITY_SCHEDULE,
    ENTITY_STATUS,
    build_charge_forecast,
    build_next_event_summary,
    build_price_ranges_display,
    build_schedule_display,
    build_schedule_markdown,
    build_status_message,
    build_today_story,
    build_tomorrow_story,
    get_temperature_icon,
    publish_all_entities,
    update_entity,
)

logger = setup_logging(name=__name__)


DEFAULT_CONFIG = {
    "enabled": True,
    "dry_run": False,
    "entities": {
        "price_curve_entity": "sensor.energy_prices_electricity_import_price",
        "export_price_curve_entity": "sensor.energy_prices_electricity_export_price",
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
    },
    "power": {
        "charging_power_limit": 1000,
        "max_charge_power": 8000,
        "max_discharge_power": 8000,
        "min_discharge_power": 0,
        "min_scaled_power": 2500,
    },
    "passive_solar": {
        "enabled": True,
        "entry_threshold": 1000,
        "exit_threshold": 200,
    },
    "soc": {"min_soc": 5, "conservative_soc": 40, "target_eod_soc": 20, "max_soc": 100},
    "heuristics": {
        "charging_price_threshold": 0.26,
        "top_x_charge_hours": 3,
        "top_x_discharge_hours": 2,
        "min_profit_threshold": 0.1,
        "overnight_wait_threshold": 0.02,
    },
    "temperature_based_discharge": {
        "enabled": True,
        "thresholds": [
            {"temp_max": 0, "discharge_hours": 1},
            {"temp_max": 8, "discharge_hours": 1},
            {"temp_max": 16, "discharge_hours": 2},
            {"temp_max": 20, "discharge_hours": 2},
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
    last_price_curve: Optional[List[Dict[str, Any]]] = None
    warned_missing_price: bool = False
    warned_missing_temperature: bool = False
    warned_missing_ev: bool = False
    warned_missing_grid: bool = False
    warned_missing_solar: bool = False
    last_schedule_publish: Optional[datetime] = None
    last_power_adjustment: Optional[datetime] = None
    last_price_range: Optional[str] = None


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
    """Convert internal ISO schedule to API format (HH:MM)."""
    output = {}
    for key in ["charge", "discharge"]:
        if key in schedule:
            periods = []
            for p in schedule[key]:
                entry = dict(p)
                start_val = entry.get("start")
                if start_val:
                    try:
                        # Parse and format to HH:MM
                        dt = isoparse(start_val)
                        entry["start"] = dt.strftime("%H:%M")
                    except Exception:
                        pass  # Keep original if parse fails
                periods.append(entry)
            output[key] = periods
    return output


def _publish_schedule(mqtt_client: Optional[MqttDiscovery], schedule: Dict[str, Any], dry_run: bool) -> None:
    api_schedule = _format_schedule_for_api(schedule)
    
    if dry_run:
        logger.info("📝 [Dry-Run] Schedule generated (not published)")
        logger.info("   Content: %s", json.dumps(api_schedule, ensure_ascii=False))
        return

    if mqtt_client is None:
        logger.warning("⚠️ MQTT unavailable, schedule not published")
        return

    mqtt_client.publish_raw("battery_api/text/schedule/set", api_schedule, retain=False)


def _split_curve_by_date(curve: List[Dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    today = datetime.now(timezone.utc).date()
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
        if start_dt.date() == today:
            today_curve.append(entry)
        elif start_dt.date() == tomorrow:
            tomorrow_curve.append(entry)

    return today_curve, tomorrow_curve


def _determine_price_range(
    import_price: float,
    export_price: float,
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    charging_price_threshold: Optional[float] = None,
) -> str:
    """Classify the current price into load/discharge/adaptive/passive.

    When a charging_price_threshold is set, prices in the adaptive range
    that fall below the threshold are returned as "passive" — meaning the
    battery should neither charge nor actively discharge (house runs on grid).
    Prices at or above the threshold stay "adaptive" and the battery will
    discharge to bring grid export to 0W.
    """
    if load_range and load_range.min_price <= import_price <= load_range.max_price:
        return "load"
    if discharge_range and discharge_range.min_price <= export_price <= discharge_range.max_price:
        return "discharge"
    if charging_price_threshold is not None and import_price < charging_price_threshold:
        return "passive"
    return "adaptive"


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
    start_str = period.get("start")
    duration = period.get("duration", 0)
    if not start_str or not duration:
        return False
    try:
        start_dt = isoparse(start_str)
        end_dt = start_dt + timedelta(minutes=int(duration))
        return start_dt <= now < end_dt
    except Exception:
        return False


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
        logger.info("  Effective discharge hours from temperature: %d", top_x_discharge_hours)

    top_x_charge_count = calculate_top_x_count(top_x_charge_hours, interval_minutes)
    top_x_discharge_count = calculate_top_x_count(top_x_discharge_hours, interval_minutes)

    load_range, discharge_range, adaptive_range = calculate_price_ranges(
        import_curve,
        export_curve,
        top_x_charge_count,
        top_x_discharge_count,
        min_profit,
    )

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
    charging_price_threshold = config["heuristics"].get("charging_price_threshold")
    price_range = _determine_price_range(
        import_price, export_price, load_range, discharge_range, charging_price_threshold,
    )

    today_import, tomorrow_import = _split_curve_by_date(import_curve)
    if price_range == "load" and now.hour >= 20:
        if _should_wait_for_overnight(today_import, tomorrow_import, overnight_threshold):
            logger.info("⏳ Evening prices higher than overnight; waiting to charge")
            price_range = "adaptive"

    if state:
        state.last_price_curve = import_curve

    range_state = {
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
    price_ranges_text = build_price_ranges_display(
        load_range, discharge_range, adaptive_range, charging_price_threshold,
    )
    update_entity(mqtt_client, ENTITY_PRICE_RANGES, price_ranges_text, range_state, dry_run=is_dry_run)

    reasoning_text = build_today_story(
        price_range, import_price, export_price,
        load_range, discharge_range, adaptive_range,
        charging_price_threshold, now,
    )
    update_entity(mqtt_client, ENTITY_REASONING, reasoning_text,
                  {"price_range": price_range, "import_price": import_price, "export_price": export_price},
                  dry_run=is_dry_run)

    if tomorrow_import:
        tomorrow_export = tomorrow_import
        if export_curve:
            _, tomorrow_export = _split_curve_by_date(export_curve)
        tomorrow_load, tomorrow_discharge, tomorrow_adaptive = calculate_price_ranges(
            tomorrow_import,
            tomorrow_export,
            top_x_charge_count,
            top_x_discharge_count,
            min_profit,
        )
        forecast_text = build_tomorrow_story(
            tomorrow_load, tomorrow_discharge, tomorrow_adaptive, tomorrow_import,
        )
    else:
        forecast_text = build_tomorrow_story(None, None, None)

    update_entity(mqtt_client, ENTITY_FORECAST, forecast_text, dry_run=is_dry_run)

    charge_rank = get_current_period_rank(import_curve, top_x_charge_count, now, reverse=False)
    discharge_rank = get_current_period_rank(export_curve, top_x_discharge_count, now, reverse=True)

    min_scaled_power = config["power"].get(
        "min_scaled_power", config["power"]["min_discharge_power"]
    )
    charge_power = config["power"]["max_charge_power"]
    if charge_rank:
        charge_power = calculate_rank_scaled_power(
            charge_rank,
            top_x_charge_count,
            config["power"]["max_charge_power"],
            min_scaled_power,
        )

    discharge_power = config["power"]["min_discharge_power"]
    if discharge_rank:
        discharge_power = calculate_rank_scaled_power(
            discharge_rank,
            top_x_discharge_count,
            config["power"]["max_discharge_power"],
            min_scaled_power,
        )

    soc = _get_sensor_float(ha_api, config["entities"]["soc_entity"])
    max_soc = config["soc"].get("max_soc", 100)
    if soc is not None and not can_charge(soc, max_soc) and price_range == "load":
        logger.info("🛑 SOC %.1f%% >= %s%%, skipping charge window", soc, max_soc)
        price_range = "adaptive"

    discharge_start = interval_end if price_range == "load" else interval_start
    discharge_duration = _minutes_until_end_of_day(discharge_start)

    charge_periods: List[Dict[str, Any]] = []
    discharge_periods: List[Dict[str, Any]] = []

    if price_range == "load":
        charge_periods.append({
            "start": interval_start.isoformat(),
            "duration": interval_minutes,
        })
        if discharge_duration > 0:
            discharge_periods.append({
                "start": discharge_start.isoformat(),
                "duration": discharge_duration,
            })
    elif price_range == "passive":
        # Below threshold — neither charge nor discharge, let house run on grid
        logger.info("💤 Passive range — price below threshold, battery idle")
    else:
        if discharge_duration > 0:
            discharge_periods.append({
                "start": discharge_start.isoformat(),
                "duration": discharge_duration,
            })

    charge_schedule = build_charge_schedule(
        charge_periods,
        power=charge_power,
        duration_minutes=interval_minutes,
    )

    discharge_schedule = []
    if discharge_periods:
        discharge_schedule = build_discharge_schedule(
            discharge_periods,
            power_ranks=[discharge_power for _ in discharge_periods],
            duration_minutes=interval_minutes,
        )

    schedule = merge_schedules(charge_schedule, discharge_schedule)
    _publish_schedule(mqtt_client, schedule, is_dry_run)
    logger.info(
        "✅ Range-based schedule: %s range, charge=%d discharge=%d",
        price_range,
        len(schedule["charge"]),
        len(schedule["discharge"]),
    )

    action_labels = {
        "load": f"Charging {charge_power}W",
        "discharge": f"Discharging {discharge_power}W",
        "adaptive": f"Adaptive (discharge to 0W export)",
        "passive": "Passive (battery idle)",
    }
    action_state = action_labels.get(price_range, price_range)

    update_entity(
        mqtt_client,
        ENTITY_CURRENT_ACTION,
        action_state,
        {
            "price_range": price_range,
            "import_price": import_price,
            "export_price": export_price,
            "charge_power": charge_power if price_range == "load" else None,
            "discharge_power": discharge_power if price_range != "load" else None,
            "interval_minutes": interval_minutes,
        },
        dry_run=is_dry_run,
    )

    # Update schedule entities
    update_entity(
        mqtt_client,
        ENTITY_CHARGE_SCHEDULE,
        build_charge_forecast(schedule, import_curve, load_range, now, charge_power),
        dry_run=is_dry_run,
    )
    update_entity(
        mqtt_client,
        ENTITY_DISCHARGE_SCHEDULE,
        build_schedule_display(schedule, "discharge", now),
        dry_run=is_dry_run,
    )
    update_entity(
        mqtt_client,
        ENTITY_SCHEDULE,
        build_schedule_markdown(schedule, now),
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
    logger.info("🔍 Monitoring active period...")
    soc_entity = config["entities"]["soc_entity"]
    grid_entity = config["entities"]["grid_power_entity"]
    solar_entity = config["entities"]["solar_power_entity"]
    load_entity = config["entities"]["house_load_entity"]
    batt_entity = config["entities"].get("battery_power_entity")

    # Dry run check
    is_dry_run = config.get("dry_run", False)

    soc = _get_sensor_float(ha_api, soc_entity)
    grid_power = _get_sensor_float(ha_api, grid_entity)
    solar_power = _get_sensor_float(ha_api, solar_entity)
    house_load = _get_sensor_float(ha_api, load_entity)
    batt_power = _get_sensor_float(ha_api, batt_entity) if batt_entity else None

    logger.info(
        "📊 Sensors | SOC: %s%% | Grid: %sW | Solar: %sW | Load: %sW | Bat: %sW",
        soc if soc is not None else "?",
        grid_power if grid_power is not None else "?",
        solar_power if solar_power is not None else "?",
        house_load if house_load is not None else "?",
        batt_power if batt_power is not None else "?",
    )

    if grid_power is None and not state.warned_missing_grid:
        logger.warning("⚠️ Grid power sensor unavailable, skipping export prevention")
        state.warned_missing_grid = True

    if (solar_power is None or house_load is None) and not state.warned_missing_solar:
        logger.warning("⚠️ Solar sensors unavailable, skipping opportunistic charging")
        state.warned_missing_solar = True

    ev_power = None
    if config["ev_charger"]["enabled"]:
        ev_power = _get_sensor_float(ha_api, config["ev_charger"]["entity_id"])
        logger.info("  EV sensor %s=%s", config["ev_charger"]["entity_id"], ev_power)
        if ev_power is None and not state.warned_missing_ev:
            logger.warning("⚠️ EV charger sensor unavailable, skipping EV integration")
            state.warned_missing_ev = True

    now = datetime.now(timezone.utc)

    active_discharge = any(
        _is_period_active(period, now) for period in state.schedule.get("discharge", [])
    )
    active_charge = any(
        _is_period_active(period, now) for period in state.schedule.get("charge", [])
    )

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
    top_x_discharge_count = calculate_top_x_count(top_x_discharge_hours, interval_minutes)

    min_profit = config["heuristics"].get("min_profit_threshold", 0.1)
    load_range, discharge_range, adaptive_range = calculate_price_ranges(
        import_curve or [],
        export_curve or [],
        top_x_charge_count,
        top_x_discharge_count,
        min_profit,
    )

    current_import_entry = (
        get_current_price_entry(import_curve or [], now, interval_minutes) if import_curve else None
    )
    current_export_entry = (
        get_current_price_entry(export_curve or [], now, interval_minutes) if export_curve else None
    )

    import_price = float(current_import_entry.get("price", 0.0)) if current_import_entry else 0.0
    export_price = (
        float(current_export_entry.get("price", import_price))
        if current_export_entry
        else import_price
    )
    price_range = _determine_price_range(
        import_price, export_price, load_range, discharge_range,
        config["heuristics"].get("charging_price_threshold"),
    )

    if state.last_price_range != price_range:
        price_ranges_text = build_price_ranges_display(
            load_range, discharge_range, adaptive_range,
            config["heuristics"].get("charging_price_threshold"),
        )
        update_entity(
            mqtt_client,
            ENTITY_PRICE_RANGES,
            price_ranges_text,
            {
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
            },
            dry_run=is_dry_run,
        )
        state.last_price_range = price_range

    regen_cooldown = config["timing"].get("schedule_regen_cooldown_seconds", 60)
    if price_range == "load" and not active_charge and import_curve:
        if (
            not state.last_schedule_publish
            or (now - state.last_schedule_publish).total_seconds() >= regen_cooldown
        ):
            logger.info("🔄 Price moved into load range - regenerating rolling schedule")
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

    if should_reduce_discharge(grid_power, threshold=500):
        reduce_discharge = True
        reduce_reasons.append("High Grid Export")

    if soc is not None:
        min_soc = config["soc"]["min_soc"]
        conservative_soc = config["soc"]["conservative_soc"]
        is_conservative = price_range != "discharge"
        if not can_discharge(soc, min_soc, conservative_soc, is_conservative):
            should_pause = True
            pause_reasons.append(f"SOC protection ({soc}%)")

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

    if active_discharge and should_pause:
        logger.info("%s | 🛑 Paused | Reasons: %s", " | ".join(status_parts), ", ".join(pause_reasons))
    elif active_discharge and reduce_discharge:
        logger.info("%s | 🟡 Reduced | Reasons: %s", " | ".join(status_parts), ", ".join(reduce_reasons))
    elif active_charge or active_discharge:
        logger.info("%s | Active | Mode: %s", " | ".join(status_parts), price_range)
    else:
        logger.info("%s", " | ".join(status_parts))

    if active_discharge and (should_pause or reduce_discharge):
        if should_pause:
            logger.info("🛑 Pausing discharge due to EV charging or SOC protection")

        if reduce_discharge and not should_pause:
            logger.info("🟡 Reducing discharge due to grid export or conservative SOC")
            reduced = []
            for period in state.schedule.get("discharge", []):
                reduced_power = max(
                    int(period.get("power", 0) * 0.5),
                    config["power"]["min_discharge_power"],
                )
                reduced.append({**period, "power": reduced_power})

            override = {"charge": state.schedule.get("charge", []), "discharge": reduced}
            _publish_schedule(mqtt_client, override, is_dry_run)
            status_msg = build_status_message(
                price_range, False, True, None, None, temperature,
                reduced=True, pause_reason=", ".join(reduce_reasons),
            )
            update_entity(
                mqtt_client, ENTITY_STATUS, status_msg, {"reason": "conservative"}, dry_run=is_dry_run,
            )
            return

        override = {"charge": state.schedule.get("charge", []), "discharge": []}
        _publish_schedule(mqtt_client, override, is_dry_run)
        status_msg = build_status_message(
            price_range, False, False, None, None, temperature,
            paused=True, pause_reason=", ".join(pause_reasons),
        )
        update_entity(
            mqtt_client, ENTITY_STATUS, status_msg, {"reason": "override"}, dry_run=is_dry_run,
        )
    elif active_charge:
        charge_power_val = None
        for p in state.schedule.get("charge", []):
            if _is_period_active(p, now):
                charge_power_val = p.get("power")
                break
        status_msg = build_status_message(
            price_range, True, False, charge_power_val, None, temperature,
        )
        update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
    elif active_discharge:
        discharge_power_val = None
        for p in state.schedule.get("discharge", []):
            if _is_period_active(p, now):
                discharge_power_val = p.get("power")
                break
        status_msg = build_status_message(
            price_range, False, True, None, discharge_power_val, temperature,
        )
        update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)
    else:
        status_msg = build_status_message(
            price_range, False, False, None, None, temperature,
        )
        update_entity(mqtt_client, ENTITY_STATUS, status_msg, dry_run=is_dry_run)

    if active_discharge and not should_pause:
        discharge_periods = state.schedule.get("discharge", [])
        active_period = next((p for p in discharge_periods if _is_period_active(p, now)), None)
        
        scheduled_power = int(active_period.get("power", 0)) if active_period else 0
        current_power = int(batt_power) if batt_power is not None else scheduled_power

        effective_range = price_range
        if (
            soc is not None
            and soc <= config["soc"]["conservative_soc"]
            and price_range == "discharge"
        ):
            effective_range = "adaptive"

        max_power = config["power"]["max_discharge_power"]
        min_scaled_power = config["power"].get(
            "min_scaled_power", config["power"]["min_discharge_power"]
        )
        adaptive_grace = config["timing"].get("adaptive_power_grace_seconds", 60)

        target_power: Optional[int] = None
        if effective_range == "discharge" and export_curve:
            rank = get_current_period_rank(export_curve, top_x_discharge_count, now, reverse=True)
            if rank:
                target_power = calculate_rank_scaled_power(
                    rank, top_x_discharge_count, max_power, min_scaled_power
                )
        elif effective_range == "adaptive":
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
                updated = []
                for period in discharge_periods:
                    if period is active_period:
                        updated.append({**period, "power": target_power})
                    else:
                        updated.append(period)
                override = {"charge": state.schedule.get("charge", []), "discharge": updated}
                _publish_schedule(mqtt_client, override, is_dry_run)
                state.last_power_adjustment = now
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

    # ---------------------------
    # Passive Solar / Gap Logic
    # ---------------------------
    # Using SolarMonitor to check if we should be in 0W charge mode
    if solar_monitor.check_passive_state(ha_api):
        logger.info("☀️ Passive Solar Mode is ACTIVE (0W Charge Gap)")
        gap_schedule = gap_scheduler.generate_passive_gap_schedule()
        
        # We publish a focused schedule: 0W charge now, then discharge fallback
        _publish_schedule(mqtt_client, gap_schedule, is_dry_run)
        
        update_entity(
            mqtt_client,
            ENTITY_CURRENT_ACTION,
            "Passive Solar (0W charge gap)",
            {"status": "active", "gap_schedule": True},
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

        if not sleep_with_shutdown_check(shutdown_event, config["timing"]["monitor_interval"]):
            break

    if mqtt_client:
        mqtt_client.disconnect()

    logger.info("Battery Manager add-on stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
