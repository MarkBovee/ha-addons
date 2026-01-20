"""Battery Manager add-on main entry point."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dateutil.parser import isoparse

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
from .solar_monitor import detect_excess_solar, should_charge_from_solar
from .temperature_advisor import get_discharge_hours
from .status_reporter import build_entity_configs, publish_discovery, update_entity_state

from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.ha_api import HomeAssistantApi
from shared.config_loader import get_run_once_mode
from shared.mqtt_setup import setup_mqtt_client


logger = setup_logging(name=__name__)


DEFAULT_CONFIG = {
    "enabled": True,
    "dry_run": False,
    "entities": {
        "price_curve_entity": "sensor.energy_prices_electricity_import_price",
        "export_price_curve_entity": "sensor.energy_prices_electricity_export_price",
        "soc_entity": "sensor.battery_api_battery_soc",
        "grid_power_entity": "sensor.battery_api_grid_power",
        "solar_power_entity": "sensor.battery_api_pv_power",
        "house_load_entity": "sensor.battery_api_load_power",
        "temperature_entity": "sensor.weather_forecast_temperature",
    },
    "timing": {
        "update_interval": 3600,
        "monitor_interval": 60,
        "adaptive_power_grace_seconds": 60,
        "schedule_regen_cooldown_seconds": 60,
    },
    "power": {
        "max_charge_power": 8000,
        "max_discharge_power": 8000,
        "min_discharge_power": 0,
        "min_scaled_power": 2500,
    },
    "soc": {"min_soc": 5, "conservative_soc": 40, "target_eod_soc": 20, "max_soc": 100},
    "heuristics": {
        "top_x_charge_hours": 3,
        "top_x_discharge_hours": 2,
        "excess_solar_threshold": 1000,
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
    "ev_charger": {"enabled": True, "charging_threshold": 500, "entity_id": "sensor.charge_amps_monitor_charger_current_power"},
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
    config_path = "/data/options.json"
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
    candidates = [entity_id, "sensor.ep_price_import", "sensor.energy_prices_electricity_import_price"]
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


def _prepare_periods(periods: List[Dict[str, Any]], fallback_duration: int) -> List[Dict[str, Any]]:
    prepared = []
    for period in periods:
        prepared.append(
            {
                "start": period.get("start"),
                "duration": _duration_minutes(period, fallback_duration),
                "price": period.get("price"),
            }
        )
    return prepared


def _publish_schedule(mqtt_client: Any, schedule: Dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        logger.info("Dry run enabled; schedule not published")
        logger.info("Dry run schedule payload: %s", json.dumps(schedule, ensure_ascii=False))
        return
    if mqtt_client is None:
        logger.warning("MQTT unavailable, schedule not published")
        return
    if hasattr(mqtt_client, "publish_raw"):
        mqtt_client.publish_raw("battery_api/text/schedule/set", schedule, retain=False)
    else:
        publish_to_mqtt(mqtt_client, schedule, "battery_api/text/schedule/set")


def _split_curve_by_date(curve: List[Dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    today = datetime.now().date()
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
) -> str:
    if load_range and load_range.min_price <= import_price <= load_range.max_price:
        return "load"
    if discharge_range and discharge_range.min_price <= export_price <= discharge_range.max_price:
        return "discharge"
    return "adaptive"


def _interval_window(now: datetime, interval_minutes: int) -> tuple[datetime, datetime]:
    interval_minutes = max(interval_minutes, 1)
    rounded = now.replace(minute=(now.minute // interval_minutes) * interval_minutes, second=0, microsecond=0)
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


def generate_schedule(
    config: Dict[str, Any],
    ha_api: HomeAssistantApi,
    mqtt_client: Any,
    state: Optional[RuntimeState] = None,
) -> Dict[str, Any]:
    import_entity = config["entities"]["price_curve_entity"]
    export_entity = config["entities"]["export_price_curve_entity"]
    import_curve = _get_price_curve(ha_api, import_entity)
    export_curve = _get_export_price_curve(ha_api, export_entity)

    if not import_curve and state and state.last_price_curve:
        import_curve = state.last_price_curve
        logger.warning("Import price curve unavailable; using last known curve")

    if not import_curve:
        logger.warning("Import price curve unavailable; skipping schedule generation")
        if state:
            state.warned_missing_price = True
        return {"charge": [], "discharge": []}

    if not export_curve:
        logger.warning("Export price curve unavailable; using import curve for discharge ranking")
        export_curve = import_curve

    logger.info(
        "Using price curves: import=%s (%d points), export=%s (%d points)",
        import_entity,
        len(import_curve),
        export_entity,
        len(export_curve),
    )

    now = datetime.utcnow()
    interval_minutes = detect_interval_minutes(import_curve)
    interval_start, interval_end = _interval_window(now, interval_minutes)

    top_x_charge_hours = config["heuristics"]["top_x_charge_hours"]
    top_x_discharge_hours = config["heuristics"]["top_x_discharge_hours"]
    min_profit = config["heuristics"].get("min_profit_threshold", 0.1)
    overnight_threshold = config["heuristics"].get("overnight_wait_threshold", 0.02)

    if config["temperature_based_discharge"]["enabled"]:
        temperature_entity = config["entities"]["temperature_entity"]
        temperature = _get_sensor_float(ha_api, temperature_entity)
        logger.info("Temperature sensor %s=%s", temperature_entity, temperature)
        if temperature is None and state and not state.warned_missing_temperature:
            logger.warning("Temperature sensor unavailable, using default discharge hours")
            state.warned_missing_temperature = True
        top_x_discharge_hours = get_discharge_hours(
            temperature,
            config["temperature_based_discharge"]["thresholds"],
        )
        logger.info("Effective discharge hours from temperature: %d", top_x_discharge_hours)

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
        logger.warning("Current import price unavailable; using baseline discharge")
        current_import_entry = {"price": 0.0, "start": interval_start.isoformat()}
    if not current_export_entry:
        current_export_entry = {"price": current_import_entry.get("price", 0.0), "start": interval_start.isoformat()}

    import_price = float(current_import_entry.get("price", 0.0))
    export_price = float(current_export_entry.get("price", import_price))
    price_range = _determine_price_range(import_price, export_price, load_range, discharge_range)

    today_import, tomorrow_import = _split_curve_by_date(import_curve)
    if price_range == "load" and now.hour >= 20:
        if _should_wait_for_overnight(today_import, tomorrow_import, overnight_threshold):
            logger.info("Evening prices higher than overnight; waiting to charge")
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
    _safe_update_entity_state(
        mqtt_client,
        build_entity_configs()[3],
        price_range,
        range_state,
    )

    reasoning = (
        f"Now: {price_range} | import €{import_price:.3f}/kWh, export €{export_price:.3f}/kWh. "
    )
    if load_range:
        reasoning += f"Load €{load_range.min_price:.3f}-{load_range.max_price:.3f}"
    else:
        reasoning += "Load n/a"
    if discharge_range:
        reasoning += (
            f" | Discharge €{discharge_range.min_price:.3f}-{discharge_range.max_price:.3f}"
        )
    if adaptive_range:
        reasoning += (
            f" | Adaptive €{adaptive_range.min_price:.3f}-{adaptive_range.max_price:.3f}"
        )

    _safe_update_entity_state(
        mqtt_client,
        build_entity_configs()[1],
        price_range,
        {"text": reasoning},
    )

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
        forecast = "Tomorrow: "
        if tomorrow_load:
            forecast += f"Load €{tomorrow_load.min_price:.3f}-{tomorrow_load.max_price:.3f}"
        if tomorrow_adaptive:
            forecast += f" | Adaptive €{tomorrow_adaptive.min_price:.3f}-{tomorrow_adaptive.max_price:.3f}"
        if tomorrow_discharge:
            forecast += f" | Discharge €{tomorrow_discharge.min_price:.3f}-{tomorrow_discharge.max_price:.3f}"
    else:
        forecast = "Tomorrow: price curve not available yet"

    _safe_update_entity_state(
        mqtt_client,
        build_entity_configs()[2],
        price_range,
        {"text": forecast},
    )

    charge_rank = get_current_period_rank(import_curve, top_x_charge_count, now, reverse=False)
    discharge_rank = get_current_period_rank(export_curve, top_x_discharge_count, now, reverse=True)

    min_scaled_power = config["power"].get("min_scaled_power", config["power"]["min_discharge_power"])
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
    if soc is not None and soc >= max_soc and price_range == "load":
        logger.info("SOC %.1f%% >= %s%%, skipping charge window", soc, max_soc)
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
    _publish_schedule(mqtt_client, schedule, config.get("dry_run", False))
    logger.info(
        "Range-based schedule: %s range, charge=%d discharge=%d",
        price_range,
        len(schedule["charge"]),
        len(schedule["discharge"]),
    )

    _safe_update_entity_state(
        mqtt_client,
        build_entity_configs()[4],
        price_range,
        {
            "import_price": import_price,
            "export_price": export_price,
            "charge_power": charge_power if price_range == "load" else None,
            "discharge_power": discharge_power if price_range != "load" else None,
            "interval_minutes": interval_minutes,
        },
    )

    return schedule


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


def monitor_active_period(config: Dict[str, Any], ha_api: HomeAssistantApi, mqtt_client: Any, state: RuntimeState) -> None:
    soc_entity = config["entities"]["soc_entity"]
    grid_entity = config["entities"]["grid_power_entity"]
    solar_entity = config["entities"]["solar_power_entity"]
    load_entity = config["entities"]["house_load_entity"]

    soc = _get_sensor_float(ha_api, soc_entity)
    grid_power = _get_sensor_float(ha_api, grid_entity)
    solar_power = _get_sensor_float(ha_api, solar_entity)
    house_load = _get_sensor_float(ha_api, load_entity)

    logger.info(
        "Sensors: soc(%s)=%s grid(%s)=%s solar(%s)=%s load(%s)=%s",
        soc_entity,
        soc,
        grid_entity,
        grid_power,
        solar_entity,
        solar_power,
        load_entity,
        house_load,
    )

    if grid_power is None and not state.warned_missing_grid:
        logger.warning("Grid power sensor unavailable, skipping export prevention")
        state.warned_missing_grid = True

    if (solar_power is None or house_load is None) and not state.warned_missing_solar:
        logger.warning("Solar sensors unavailable, skipping opportunistic charging")
        state.warned_missing_solar = True

    ev_power = None
    if config["ev_charger"]["enabled"]:
        ev_power = _get_sensor_float(ha_api, config["ev_charger"]["entity_id"])
        logger.info("EV sensor %s=%s", config["ev_charger"]["entity_id"], ev_power)
        if ev_power is None and not state.warned_missing_ev:
            logger.warning("EV charger sensor unavailable, skipping EV integration")
            state.warned_missing_ev = True

    now = datetime.utcnow()

    active_discharge = any(_is_period_active(period, now) for period in state.schedule.get("discharge", []))
    active_charge = any(_is_period_active(period, now) for period in state.schedule.get("charge", []))

    import_curve = _get_price_curve(ha_api, config["entities"]["price_curve_entity"]) or state.last_price_curve
    export_curve = _get_export_price_curve(ha_api, config["entities"]["export_price_curve_entity"]) or import_curve

    interval_minutes = detect_interval_minutes(import_curve or [])
    top_x_charge_count = calculate_top_x_count(config["heuristics"]["top_x_charge_hours"], interval_minutes)
    top_x_discharge_hours = config["heuristics"]["top_x_discharge_hours"]
    if config["temperature_based_discharge"]["enabled"]:
        temperature = _get_sensor_float(ha_api, config["entities"]["temperature_entity"])
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

    current_import_entry = get_current_price_entry(import_curve or [], now, interval_minutes) if import_curve else None
    current_export_entry = get_current_price_entry(export_curve or [], now, interval_minutes) if export_curve else None

    import_price = float(current_import_entry.get("price", 0.0)) if current_import_entry else 0.0
    export_price = float(current_export_entry.get("price", import_price)) if current_export_entry else import_price
    price_range = _determine_price_range(import_price, export_price, load_range, discharge_range)

    if state.last_price_range != price_range:
        _safe_update_entity_state(
            mqtt_client,
            build_entity_configs()[3],
            price_range,
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
        )
        state.last_price_range = price_range

    regen_cooldown = config["timing"].get("schedule_regen_cooldown_seconds", 60)
    if price_range == "load" and not active_charge and import_curve:
        if not state.last_schedule_publish or (now - state.last_schedule_publish).total_seconds() >= regen_cooldown:
            logger.info("Price moved into load range - regenerating rolling schedule")
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
        should_pause = should_pause_discharge(ev_power, ev_threshold)
        if should_pause:
            pause_reasons.append(f"ev_charging>{ev_threshold}W")

    reduce_discharge = should_reduce_discharge(grid_power, threshold=500)
    if reduce_discharge:
        reduce_reasons.append("grid_export<-500W")

    if soc is not None:
        if soc <= config["soc"]["min_soc"]:
            should_pause = True
            pause_reasons.append(f"soc<=min({config['soc']['min_soc']}%)")
        elif soc < config["soc"]["conservative_soc"]:
            reduce_discharge = True
            reduce_reasons.append(f"soc<conservative({config['soc']['conservative_soc']}%)")

    logger.info(
        "Decision flags: active_charge=%s active_discharge=%s pause=%s reduce=%s",
        active_charge,
        active_discharge,
        should_pause,
        reduce_discharge,
    )
    if pause_reasons:
        logger.info("Pause reasons: %s", pause_reasons)
    if reduce_reasons:
        logger.info("Reduce reasons: %s", reduce_reasons)

    if active_discharge and (should_pause or reduce_discharge):
        if should_pause:
            logger.info("Pausing discharge due to EV charging or SOC protection")

        if reduce_discharge and not should_pause:
            logger.info("Reducing discharge due to grid export or conservative SOC")
            reduced = []
            for period in state.schedule.get("discharge", []):
                reduced_power = max(
                    int(period.get("power", 0) * 0.5),
                    config["power"]["min_discharge_power"],
                )
                reduced.append({**period, "power": reduced_power})

            override = {"charge": state.schedule.get("charge", []), "discharge": reduced}
            _publish_schedule(mqtt_client, override)
            _safe_update_entity_state(
                mqtt_client,
                build_entity_configs()[0],
                "reduced",
                {"reason": "conservative"},
            )
            return

        override = {"charge": state.schedule.get("charge", []), "discharge": []}
        _publish_schedule(mqtt_client, override, config.get("dry_run", False))
        _safe_update_entity_state(
            mqtt_client,
            build_entity_configs()[0],
            "paused",
            {"reason": "override"},
        )
    elif active_charge:
        _safe_update_entity_state(mqtt_client, build_entity_configs()[0], "charging")
    elif active_discharge:
        _safe_update_entity_state(mqtt_client, build_entity_configs()[0], "discharging")
    else:
        _safe_update_entity_state(mqtt_client, build_entity_configs()[0], "idle")

    if active_discharge and not should_pause:
        discharge_periods = state.schedule.get("discharge", [])
        active_period = next((p for p in discharge_periods if _is_period_active(p, now)), None)
        current_power = int(active_period.get("power", 0)) if active_period else 0

        effective_range = price_range
        if soc is not None and soc <= config["soc"]["conservative_soc"] and price_range == "discharge":
            effective_range = "adaptive"

        max_power = config["power"]["max_discharge_power"]
        min_scaled_power = config["power"].get("min_scaled_power", config["power"]["min_discharge_power"])
        adaptive_grace = config["timing"].get("adaptive_power_grace_seconds", 60)

        target_power: Optional[int] = None
        if effective_range == "discharge" and export_curve:
            rank = get_current_period_rank(export_curve, top_x_discharge_count, now, reverse=True)
            if rank:
                target_power = calculate_rank_scaled_power(rank, top_x_discharge_count, max_power, min_scaled_power)
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
            if state.last_power_adjustment and (now - state.last_power_adjustment).total_seconds() < adaptive_grace:
                logger.info("Adaptive adjustment skipped (grace period active)")
            elif target_power != current_power:
                updated = []
                for period in discharge_periods:
                    if period is active_period:
                        updated.append({**period, "power": target_power})
                    else:
                        updated.append(period)
                override = {"charge": state.schedule.get("charge", []), "discharge": updated}
                _publish_schedule(mqtt_client, override, config.get("dry_run", False))
                state.last_power_adjustment = now
                _safe_update_entity_state(
                    mqtt_client,
                    build_entity_configs()[4],
                    effective_range,
                    {
                        "target_power": target_power,
                        "current_power": current_power,
                        "grid_power": grid_power,
                        "range": effective_range,
                    },
                )

        if (
            effective_range == "adaptive"
            and current_power == 0
            and grid_power is not None
            and grid_power < -1000
            and soc is not None
            and soc < 99
        ):
            _safe_update_entity_state(
                mqtt_client,
                build_entity_configs()[4],
                "opportunistic_solar",
                {"excess_solar": abs(grid_power), "soc": soc},
            )

    if solar_power is not None and house_load is not None:
        excess = detect_excess_solar(solar_power, house_load, config["heuristics"]["excess_solar_threshold"])
        if should_charge_from_solar(excess, config["heuristics"]["excess_solar_threshold"]):
            _safe_update_entity_state(
                mqtt_client,
                build_entity_configs()[4],
                "opportunistic_charge",
                {"excess_solar": excess},
            )


def _mqtt_adapter(mqtt_client: Any):
    if hasattr(mqtt_client, "publish"):
        return mqtt_client

    class Adapter:
        def __init__(self, client):
            self._client = client

        def publish(self, topic: str, payload: str):
            if hasattr(self._client, "publish_raw"):
                self._client.publish_raw(topic, payload, retain=True)

    return Adapter(mqtt_client)


def _safe_update_entity_state(
    mqtt_client: Any,
    entity_config: Dict[str, Any],
    state_value: str,
    attributes: Dict[str, Any] | None = None,
) -> None:
    if mqtt_client is None:
        return
    update_entity_state(_mqtt_adapter(mqtt_client), entity_config, state_value, attributes)


def main() -> int:
    logger.info("Battery Manager add-on starting...")

    shutdown_event = setup_signal_handlers(logger)
    config = _load_config()

    if not config.get("enabled", True):
        logger.info("Battery Manager disabled via configuration, exiting")
        return 0

    ha_api = HomeAssistantApi()

    mqtt_client = setup_mqtt_client(
        addon_name="Battery Manager",
        addon_id="battery_manager",
        config=config,
        manufacturer="HA Addons",
        model="Battery Manager",
    )

    if mqtt_client:
        publish_discovery(_mqtt_adapter(mqtt_client), build_entity_configs())

    state = RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)

    run_once = get_run_once_mode()

    def schedule_task():
        state.schedule = generate_schedule(config, ha_api, mqtt_client, state)
        state.schedule_generated_at = datetime.utcnow()
        state.last_schedule_publish = state.schedule_generated_at

    schedule_task()

    while not shutdown_event.is_set():
        try:
            monitor_active_period(config, ha_api, mqtt_client, state)
        except Exception as exc:
            logger.error("Monitoring loop error: %s", exc, exc_info=True)

        if run_once:
            logger.info("RUN_ONCE mode complete, exiting")
            break

        if state.schedule_generated_at:
            elapsed = (datetime.utcnow() - state.schedule_generated_at).total_seconds()
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
