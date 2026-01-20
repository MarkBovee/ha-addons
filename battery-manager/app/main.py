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
from .power_calculator import calculate_scaled_power
from .price_analyzer import find_top_x_charge_periods, find_top_x_discharge_periods
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
    "timing": {"update_interval": 3600, "monitor_interval": 60},
    "power": {"max_charge_power": 8000, "max_discharge_power": 8000, "min_discharge_power": 4000},
    "soc": {"min_soc": 5, "conservative_soc": 40, "target_eod_soc": 20},
    "heuristics": {"top_x_charge_hours": 3, "top_x_discharge_hours": 2, "excess_solar_threshold": 1000},
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
    "ev_charger": {"enabled": True, "charging_threshold": 500, "entity_id": "sensor.ev_charger_power"},
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

    top_x_charge = config["heuristics"]["top_x_charge_hours"]
    top_x_discharge = config["heuristics"]["top_x_discharge_hours"]

    if config["temperature_based_discharge"]["enabled"]:
        temperature_entity = config["entities"]["temperature_entity"]
        temperature = _get_sensor_float(ha_api, temperature_entity)
        logger.info("Temperature sensor %s=%s", temperature_entity, temperature)
        if temperature is None and state and not state.warned_missing_temperature:
            logger.warning("Temperature sensor unavailable, using default discharge hours")
            state.warned_missing_temperature = True
        top_x_discharge = get_discharge_hours(
            temperature,
            config["temperature_based_discharge"]["thresholds"],
        )
        logger.info("Effective discharge hours from temperature: %d", top_x_discharge)

    charge_periods = find_top_x_charge_periods(import_curve, top_x_charge)
    discharge_periods = find_top_x_discharge_periods(export_curve, top_x_discharge)
    logger.info(
        "Selected periods: charge=%d (import curve), discharge=%d (export curve)",
        len(charge_periods),
        len(discharge_periods),
    )

    fallback_duration = 60
    charge_prepared = _prepare_periods([p.value for p in charge_periods], fallback_duration)
    discharge_prepared = _prepare_periods([p.value for p in discharge_periods], fallback_duration)

    charge_schedule = build_charge_schedule(
        charge_prepared,
        power=config["power"]["max_charge_power"],
        duration_minutes=fallback_duration,
    )

    power_ranks = [
        calculate_scaled_power(rank + 1, config["power"]["max_discharge_power"], config["power"]["min_discharge_power"])
        for rank in range(len(discharge_prepared))
    ]
    if power_ranks:
        logger.info("Discharge power ranks: %s", power_ranks)
    discharge_schedule = build_discharge_schedule(
        discharge_prepared,
        power_ranks=power_ranks,
        duration_minutes=fallback_duration,
    )

    schedule = merge_schedules(charge_schedule, discharge_schedule)
    if state:
        state.last_price_curve = import_curve
    _publish_schedule(mqtt_client, schedule, config.get("dry_run", False))
    logger.info("Schedule generated: %d charge, %d discharge periods", len(schedule["charge"]), len(schedule["discharge"]))

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

    should_pause = False
    reduce_discharge = False
    if config["ev_charger"]["enabled"]:
        should_pause = should_pause_discharge(ev_power, config["ev_charger"]["charging_threshold"])

    reduce_discharge = should_reduce_discharge(grid_power, threshold=500)

    if soc is not None:
        if soc <= config["soc"]["min_soc"]:
            should_pause = True
        elif soc < config["soc"]["conservative_soc"]:
            reduce_discharge = True

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
            update_entity_state(
                _mqtt_adapter(mqtt_client),
                build_entity_configs()[0],
                "reduced",
                {"reason": "conservative"},
            )
            return

        override = {"charge": state.schedule.get("charge", []), "discharge": []}
        _publish_schedule(mqtt_client, override, config.get("dry_run", False))
        update_entity_state(
            _mqtt_adapter(mqtt_client),
            build_entity_configs()[0],
            "paused",
            {"reason": "override"},
        )
    elif active_charge:
        update_entity_state(_mqtt_adapter(mqtt_client), build_entity_configs()[0], "charging")
    elif active_discharge:
        update_entity_state(_mqtt_adapter(mqtt_client), build_entity_configs()[0], "discharging")
    else:
        update_entity_state(_mqtt_adapter(mqtt_client), build_entity_configs()[0], "idle")

    if solar_power is not None and house_load is not None:
        excess = detect_excess_solar(solar_power, house_load, config["heuristics"]["excess_solar_threshold"])
        if should_charge_from_solar(excess, config["heuristics"]["excess_solar_threshold"]):
            update_entity_state(
                _mqtt_adapter(mqtt_client),
                build_entity_configs()[1],
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
