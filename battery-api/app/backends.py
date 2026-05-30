"""Battery API provider backends."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.ha_api import HomeAssistantApi

try:
    from .models import BatteryChargeType, ChargingPeriod
except ImportError:
    from models import BatteryChargeType, ChargingPeriod

logger = logging.getLogger(__name__)

MODE_VERIFY_ATTEMPTS = 20
MODE_VERIFY_DELAY_SECONDS = 1.0
SCHEDULE_INPUT_VERIFY_ATTEMPTS = 6
SCHEDULE_INPUT_VERIFY_DELAY_SECONDS = 0.25

PASSIVE_MODE_OPTIONS = ["Off", "Passive charge", "Passive discharge"]
PASSIVE_MODE_SELECT_TO_VALUE = {
    "Off": 0,
    "Passive discharge": 1,
    "Passive charge": 2,
}
PASSIVE_MODE_VALUE_TO_SELECT = {
    "0": "Off",
    "1": "Passive discharge",
    "2": "Passive charge",
    0: "Off",
    1: "Passive discharge",
    2: "Passive charge",
}


def _load_saj_api_client():
    """Import SAJ cloud client only when API provider is used."""
    try:
        from .saj_api import SajApiClient
    except ModuleNotFoundError as exc:
        if exc.name != "app.saj_api":
            raise
        from saj_api import SajApiClient
    return SajApiClient


MODE_SELECT_TO_PROVIDER = {
    "Self-consumption": "self_consumption",
    "Time-of-use": "time_of_use",
    "AI": "ai",
}

MODE_PROVIDER_TO_SELECT = {
    "self_consumption": "Self-consumption",
    "time_of_use": "Time-of-use",
    "self-consumption": "Self-consumption",
    "time-of-use": "Time-of-use",
    "ai": "AI",
    "0": "Self-consumption",
    "1": "Time-of-use",
    "12": "AI",
    0: "Self-consumption",
    1: "Time-of-use",
    12: "AI",
}

MODE_SELECT_TO_MODBUS_APP_MODE = {
    "Self-consumption": 0,
    "Time-of-use": 1,
    "AI": 12,
}

DEFAULT_MODBUS_DISCOVERY = {
    "soc": "sensor.saj_battery_energy_percent",
    "battery_power": "sensor.saj_battery_power",
    "pv_power": "sensor.saj_pv_power",
    "grid_power": "sensor.saj_total_grid_power",
    "load_power": "sensor.saj_total_load_power",
    "battery_capacity": "sensor.saj_battery_capacity",
    "battery_current": "sensor.saj_battery_1_current",
    "battery_charge_power_limit": "sensor.saj_battery_charge_power_limit",
    "battery_discharge_power_limit": "sensor.saj_battery_discharge_power_limit",
    "grid_charge_power_limit": "sensor.saj_grid_charge_power_limit",
    "grid_discharge_power_limit": "sensor.saj_grid_discharge_power_limit",
    "battery_on_grid_discharge_depth": "sensor.saj_battery_on_grid_discharge_depth",
    "battery_off_grid_discharge_depth": "sensor.saj_battery_offgrid_discharge_depth",
    "app_mode": "sensor.saj_app_mode",
    "direction_battery": "sensor.saj_direction_battery",
    "direction_grid": "sensor.saj_direction_grid",
    "direction_pv": "sensor.saj_direction_pv",
    "direction_output": "sensor.saj_direction_ouput",
    "charge_time_enable": "sensor.saj_charge_time_enable_bitmask",
    "discharge_time_enable": "sensor.saj_discharge_time_enable_bitmask",
    "export_limit": "number.saj_export_limit_input",
    "passive_charge_enable": "number.saj_passive_charge_enable_input",
    "passive_grid_charge_power": "number.saj_passive_grid_charge_power_input",
    "passive_grid_discharge_power": "number.saj_passive_grid_discharge_power_input",
    "passive_battery_charge_power": "number.saj_passive_battery_charge_power_input",
    "passive_battery_discharge_power": "number.saj_passive_battery_discharge_power_input",
    "charge_time_enable_input": "number.saj_charge_time_enable_input",
    "discharge_time_enable_input": "number.saj_discharge_time_enable_input",
    "switch_charging": "switch.saj_charging_control",
    "switch_discharging": "switch.saj_discharging_control",
    "switch_passive_charge": "switch.saj_passive_charge_control",
    "switch_passive_discharge": "switch.saj_passive_discharge_control",
    "app_mode_input": "number.saj_app_mode_input",
    "battery_charge_power_limit_input": "number.saj_battery_charge_power_limit_input",
    "battery_discharge_power_limit_input": "number.saj_battery_discharge_power_limit_input",
    "grid_charge_power_limit_input": "number.saj_grid_max_charge_power_input",
    "grid_discharge_power_limit_input": "number.saj_grid_max_discharge_power_input",
}

DISCOVERY_ENTITY_ALIASES = {
    "passive_charge_enable": [
        "number.saj_passive_charge_enable_input",
        "number.saj_passive_charge_enable",
    ],
    "passive_grid_charge_power": [
        "number.saj_passive_grid_charge_power_input",
        "number.saj_passive_grid_charge_power",
    ],
    "passive_grid_discharge_power": [
        "number.saj_passive_grid_discharge_power_input",
        "number.saj_passive_grid_discharge_power",
    ],
    "passive_battery_charge_power": [
        "number.saj_passive_battery_charge_power_input",
        "number.saj_passive_battery_charge_power",
        "number.saj_passive_bat_charge_power",
    ],
    "passive_battery_discharge_power": [
        "number.saj_passive_battery_discharge_power_input",
        "number.saj_passive_battery_discharge_power",
        "number.saj_passive_bat_discharge_power",
    ],
}


@dataclass
class BackendContext:
    """Mutable state shared with provider backends."""

    config: Dict[str, Any]
    status: Dict[str, Any]
    simulation_mode: bool
    battery_mode_setting: str
    schedule_json: str
    validated_schedule: Optional[Dict[str, List[Dict[str, Any]]]]


class BatteryBackend(ABC):
    """Provider-neutral backend contract."""

    def __init__(self, context: BackendContext):
        self.context = context

    @property
    def provider_name(self) -> str:
        return str(self.context.config.get("provider", "api"))

    @abstractmethod
    def setup(self) -> bool:
        """Initialize backend and return readiness."""

    @abstractmethod
    def poll_status(self) -> None:
        """Refresh status fields in the shared context."""

    @abstractmethod
    def fetch_current_schedule(self) -> None:
        """Refresh current schedule and mode from provider."""

    @abstractmethod
    def save_schedule(self, periods: List[ChargingPeriod], schedule_json: str) -> bool:
        """Persist schedule to provider."""

    @abstractmethod
    def set_mode(self, mode: str) -> bool:
        """Apply battery mode to provider."""

    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capability map."""
        return {}

    def set_export_limit(self, value: int) -> bool:
        """Optionally support export limit writes."""
        return False

    def set_passive_mode(self, mode: str) -> bool:
        """Optionally support passive charge/discharge control."""
        return False

    def _set_status(self, **updates: Any) -> None:
        self.context.status.update(updates)


class ApiBatteryBackend(BatteryBackend):
    """Existing SAJ cloud API backend."""

    def __init__(self, context: BackendContext):
        super().__init__(context)
        config = context.config
        saj_api_client_cls = _load_saj_api_client()
        self.client = saj_api_client_cls(
            username=config["saj_username"],
            password=config["saj_password"],
            device_serial=config["device_serial_number"],
            plant_uid=config["plant_uid"],
            simulation_mode=context.simulation_mode,
        )

    def setup(self) -> bool:
        if self.context.simulation_mode:
            self._set_status(
                api_status="Simulation",
                current_schedule='{"mode": "simulation", "charge": [], "discharge": []}',
            )
            return True

        if self.client.authenticate():
            self._set_status(api_status="Connected")
            self.fetch_current_schedule()
            return True

        self._set_status(api_status="Auth Failed")
        return False

    def poll_status(self) -> None:
        if self.context.simulation_mode:
            self._set_status(
                battery_soc=75,
                battery_power=500,
                battery_direction=1,
                pv_power=3000,
                grid_power=-200,
                grid_direction=-1,
                load_power=2500,
                last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                user_mode="EMS",
                battery_capacity=50,
                battery_current=2.5,
                plant_name="Simulation",
                inverter_model="HS2-8K-T2",
                inverter_sn="SIM123456",
                api_status="Simulation",
            )
            return

        flow_data = self.client.get_energy_flow_data()
        if not flow_data:
            return

        self._set_status(
            battery_soc=flow_data.get("battery_soc"),
            battery_power=flow_data.get("battery_power"),
            battery_direction=flow_data.get("battery_direction"),
            pv_power=flow_data.get("pv_power"),
            grid_power=flow_data.get("grid_power"),
            grid_direction=flow_data.get("grid_direction"),
            load_power=flow_data.get("load_power"),
            battery_capacity=flow_data.get("battery_capacity"),
            battery_current=flow_data.get("battery_current"),
            battery_charge_today=flow_data.get("battery_charge_today"),
            battery_discharge_today=flow_data.get("battery_discharge_today"),
            battery_charge_total=flow_data.get("battery_charge_total"),
            battery_discharge_total=flow_data.get("battery_discharge_total"),
            pv_direction=flow_data.get("pv_direction"),
            solar_power=flow_data.get("solar_power"),
            home_load_power=flow_data.get("home_load_power"),
            backup_load_power=flow_data.get("backup_load_power"),
            input_output_power=flow_data.get("input_output_power"),
            output_direction=flow_data.get("output_direction"),
            plant_name=flow_data.get("plant_name"),
            inverter_model=flow_data.get("inverter_model"),
            inverter_sn=flow_data.get("inverter_sn"),
            last_update=flow_data.get("update_time"),
            user_mode=flow_data.get("user_mode"),
            api_status="Connected",
        )

    def fetch_current_schedule(self) -> None:
        schedule = self.client.get_schedule()
        if not schedule:
            self._set_status(current_schedule="{}")
            return

        self._set_status(current_schedule=json.dumps(schedule))
        mode = schedule.get("mode")
        if mode in MODE_PROVIDER_TO_SELECT:
            self.context.battery_mode_setting = MODE_PROVIDER_TO_SELECT[mode]

        schedule_for_input = {
            "charge": schedule.get("charge", []),
            "discharge": schedule.get("discharge", []),
        }
        if schedule_for_input["charge"] or schedule_for_input["discharge"]:
            self.context.schedule_json = json.dumps(schedule_for_input, indent=2)
            self.context.validated_schedule = schedule_for_input
            self._set_status(
                schedule_status=(
                    f"Synced: {len(schedule_for_input['charge'])} charge, "
                    f"{len(schedule_for_input['discharge'])} discharge"
                )
            )

    def save_schedule(self, periods: List[ChargingPeriod], schedule_json: str) -> bool:
        charge_count = sum(1 for period in periods if period.charge_type == BatteryChargeType.CHARGE)
        discharge_count = sum(1 for period in periods if period.charge_type == BatteryChargeType.DISCHARGE)
        if charge_count > 3 or discharge_count > 6:
            self._set_status(
                schedule_status=(
                    f"Apply failed: API provider supports max 3 charge and 6 discharge periods "
                    f"(got {charge_count} charge, {discharge_count} discharge)"
                )
            )
            return False

        if self.context.simulation_mode:
            self._set_status(
                last_applied=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                api_status="Simulation",
                current_schedule=schedule_json,
            )
            return True

        success = self.client.save_schedule(periods)
        if success:
            self._set_status(
                last_applied=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                api_status="Connected",
                current_schedule=schedule_json,
            )
        return success

    def set_mode(self, mode: str) -> bool:
        provider_mode = MODE_SELECT_TO_PROVIDER.get(mode, "self_consumption")
        if self.context.simulation_mode:
            self._set_status(api_status="Simulation")
            return True
        return self.client.set_battery_mode(provider_mode)

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "provider": "api",
            "mode_control": True,
            "schedule_control": True,
            "max_charge_periods": 3,
            "max_discharge_periods": 6,
            "export_limit": False,
            "passive_mode": False,
        }


class ModbusEntityDiscovery:
    """Discover and resolve live SAJ entity ids from HA."""

    def __init__(self, ha_api: HomeAssistantApi, configured: Optional[Dict[str, str]] = None):
        self.ha_api = ha_api
        self.configured = configured or {}
        self._states: Optional[List[Dict[str, Any]]] = None

    def resolve(self) -> Dict[str, str]:
        states = self._get_states()
        all_ids = {state.get("entity_id") for state in states}
        resolved: Dict[str, str] = {}

        for key, default_id in DEFAULT_MODBUS_DISCOVERY.items():
            configured_id = self.configured.get(key)
            if configured_id:
                if configured_id in all_ids:
                    resolved[key] = configured_id
                else:
                    logger.warning("Configured Modbus entity missing for %s: %s", key, configured_id)
                continue

            candidates = [default_id, *DISCOVERY_ENTITY_ALIASES.get(key, [])]
            for candidate_id in candidates:
                if candidate_id in all_ids:
                    resolved[key] = candidate_id
                    break

        for slot_type in ("charge", "discharge"):
            for index in range(1, 8):
                read_prefix = self._slot_read_prefix(slot_type, index)
                write_prefix = self._slot_write_prefix(slot_type, index)
                candidates = {
                    f"{slot_type}{index}_start_time": f"sensor.{read_prefix}_start_time",
                    f"{slot_type}{index}_end_time": f"sensor.{read_prefix}_end_time",
                    f"{slot_type}{index}_day_mask": f"sensor.{read_prefix}_day_mask",
                    f"{slot_type}{index}_power_percent": f"sensor.{read_prefix}_power_percent",
                    f"{slot_type}{index}_start_time_input": f"text.{write_prefix}_start_time_time",
                    f"{slot_type}{index}_end_time_input": f"text.{write_prefix}_end_time_time",
                    f"{slot_type}{index}_day_mask_input": f"number.{write_prefix}_day_mask_input",
                    f"{slot_type}{index}_power_percent_input": f"number.{write_prefix}_power_percent_input",
                }
                for key, entity_id in candidates.items():
                    configured_id = self.configured.get(key)
                    candidate_id = configured_id or entity_id
                    if candidate_id in all_ids:
                        resolved[key] = candidate_id

        return resolved

    def _get_states(self) -> List[Dict[str, Any]]:
        if self._states is None:
            self._states = self.ha_api.get_states()
        return self._states

    def _slot_read_prefix(self, slot_type: str, index: int) -> str:
        if index == 1:
            return f"saj_{slot_type}"
        return f"saj_{slot_type}_{index}"

    def _slot_write_prefix(self, slot_type: str, index: int) -> str:
        return f"saj_{slot_type}{index}"


class ModbusHaBatteryBackend(BatteryBackend):
    """Read and control SAJ Modbus entities via Home Assistant."""

    def __init__(self, context: BackendContext):
        super().__init__(context)
        self.ha_api = HomeAssistantApi()
        self.discovery = ModbusEntityDiscovery(
            self.ha_api,
            configured=context.config.get("modbus_entities") or {},
        )
        self.entities: Dict[str, str] = {}
        self.inverter_power_reference_w = int(context.config.get("modbus_inverter_power_w", 8000))
        self._state_snapshot: Optional[Dict[str, Dict[str, Any]]] = None

    def setup(self) -> bool:
        if self.context.simulation_mode:
            self._set_status(api_status="Simulation")
            self.entities = DEFAULT_MODBUS_DISCOVERY.copy()
            return True

        if not self.ha_api.test_connection():
            self._set_status(api_status="HA Unavailable")
            return False

        self.entities = self.discovery.resolve()
        missing = [
            key for key in ("soc", "battery_power", "pv_power", "grid_power", "load_power", "app_mode_input")
            if key not in self.entities
        ]
        if missing:
            self._set_status(api_status=f"Modbus mapping missing: {', '.join(missing)}")
            return False

        self._set_status(api_status="Connected")
        self.fetch_current_schedule()
        return True

    def poll_status(self) -> None:
        if self.context.simulation_mode:
            self._set_status(
                battery_soc=75,
                battery_power=-500,
                battery_direction=-1,
                pv_power=3000,
                grid_power=200,
                grid_direction=1,
                load_power=2500,
                user_mode="TimeOfUse",
                passive_mode="Off",
                last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                inverter_model="HS2-8K-T2",
                api_status="Simulation",
            )
            return

        with self._state_snapshot_context():
            self._set_status(
                battery_soc=self._get_float("soc"),
                battery_power=self._get_signed_power("battery_power", "direction_battery"),
                battery_direction=self._get_int("direction_battery"),
                pv_power=self._get_float("pv_power"),
                grid_power=self._get_signed_power("grid_power", "direction_grid"),
                grid_direction=self._get_int("direction_grid"),
                load_power=self._get_float("load_power"),
                battery_capacity=self._get_float("battery_capacity"),
                battery_current=self._get_float("battery_current"),
                battery_charge_power_limit=self._get_float("battery_charge_power_limit"),
                battery_discharge_power_limit=self._get_float("battery_discharge_power_limit"),
                grid_charge_power_limit=self._get_float("grid_charge_power_limit"),
                grid_discharge_power_limit=self._get_float("grid_discharge_power_limit"),
                battery_on_grid_discharge_depth=self._get_float("battery_on_grid_discharge_depth"),
                battery_off_grid_discharge_depth=self._get_float("battery_off_grid_discharge_depth"),
                export_limit=self._get_float("export_limit"),
                passive_mode=self._get_passive_mode(),
                pv_direction=self._get_int("direction_pv"),
                output_direction=self._get_int("direction_output"),
                user_mode=self._get_state_value("app_mode"),
                last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                inverter_model=f"Modbus ({self.inverter_power_reference_w // 1000}kW)",
                api_status="Connected",
            )

    def fetch_current_schedule(self) -> None:
        with self._state_snapshot_context():
            schedule = self._read_schedule_from_ha()
            self._set_status(current_schedule=json.dumps(schedule))
            mode = self._get_state_value("app_mode")
            if mode in MODE_PROVIDER_TO_SELECT:
                self.context.battery_mode_setting = MODE_PROVIDER_TO_SELECT[mode]
            if schedule["charge"] or schedule["discharge"]:
                self.context.schedule_json = json.dumps(schedule, indent=2)
                self.context.validated_schedule = schedule
                self._set_status(
                    schedule_status=f"Synced: {len(schedule['charge'])} charge, {len(schedule['discharge'])} discharge"
                )

    def save_schedule(self, periods: List[ChargingPeriod], schedule_json: str) -> bool:
        schedule = self._deserialize_schedule(schedule_json)
        charge = schedule.get("charge", [])
        discharge = schedule.get("discharge", [])

        if len(charge) > 7 or len(discharge) > 7:
            self._set_status(schedule_status="Apply failed: Modbus supports max 7 charge and 7 discharge slots")
            return False

        if self.context.simulation_mode:
            self._set_status(
                last_applied=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                api_status="Simulation",
                current_schedule=schedule_json,
            )
            return True

        try:
            self._write_slots("charge", charge)
            self._write_slots("discharge", discharge)
            self._set_number("charge_time_enable_input", self._build_enable_mask(len(charge)))
            self._set_number("discharge_time_enable_input", self._build_enable_mask(len(discharge)))
            mode = "Time-of-use" if charge or discharge else "Self-consumption"
            if not self.set_mode(mode):
                self._set_status(schedule_status="Apply failed: mode write failed")
                return False
            read_back = self._wait_for_schedule_inputs(schedule)
            if not self._schedule_matches(read_back, schedule):
                self._set_status(schedule_status="Apply failed: command verify mismatch")
                return False
            self._set_status(
                last_applied=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                api_status="Connected",
                current_schedule=json.dumps(schedule),
            )
            return True
        except Exception as exc:
            logger.error("Modbus schedule apply error: %s", exc)
            self._set_status(schedule_status=f"Error: {exc}", api_status=f"Error: {exc}")
            return False

    def set_mode(self, mode: str) -> bool:
        target = MODE_SELECT_TO_MODBUS_APP_MODE.get(mode)
        if target is None:
            logger.error("Unsupported Modbus mode: %s", mode)
            return False
        if self.context.simulation_mode:
            self._set_status(api_status="Simulation")
            return True
        self._set_number("app_mode_input", target)
        actual = self._wait_for_int_value(
            "app_mode",
            target,
            attempts=MODE_VERIFY_ATTEMPTS,
            delay_seconds=MODE_VERIFY_DELAY_SECONDS,
        )
        if actual != target:
            self._set_status(api_status=f"Mode verify failed: expected {target}, got {actual}")
            return False
        self.context.battery_mode_setting = mode
        self._set_status(api_status="Connected")
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        passive_mode_mapped = all(
            key in self.entities
            for key in (
                "passive_charge_enable",
                "switch_passive_charge",
                "switch_passive_discharge",
            )
        )
        experimental_controls: List[str] = []
        if passive_mode_mapped:
            experimental_controls.append("passive_mode")
        if "passive_grid_charge_power" in self.entities:
            experimental_controls.append("passive_grid_charge_power")
        if "passive_grid_discharge_power" in self.entities:
            experimental_controls.append("passive_grid_discharge_power")

        return {
            "provider": "modbus_ha",
            "mode_control": "app_mode_input" in self.entities,
            "schedule_control": all(
                key in self.entities
                for key in ("charge_time_enable_input", "discharge_time_enable_input", "app_mode_input")
            ),
            "max_charge_periods": 7,
            "max_discharge_periods": 7,
            "export_limit": "export_limit" in self.entities,
            "passive_mode": passive_mode_mapped,
            "passive_mode_mapped": passive_mode_mapped,
            "experimental_controls": experimental_controls,
            "unsupported_controls": ["pv_off"],
            "discovered_entities": self.entities,
            "inverter_power_reference_w": self.inverter_power_reference_w,
        }

    def set_export_limit(self, value: int) -> bool:
        if "export_limit" not in self.entities:
            return False
        if self.context.simulation_mode:
            self._set_status(api_status="Simulation")
            return True
        clamped = max(0, min(1100, int(value)))
        self._call_service("number", "set_value", self.entities["export_limit"], clamped)
        actual = self._wait_for_int_value("export_limit", clamped)
        if actual != clamped:
            self._set_status(api_status=f"Export limit verify failed: expected {clamped}, got {actual}")
            return False
        self._set_status(export_limit=clamped, api_status="Connected")
        return True

    def set_passive_mode(self, mode: str) -> bool:
        target = PASSIVE_MODE_SELECT_TO_VALUE.get(mode)
        if target is None:
            logger.error("Unsupported passive mode: %s", mode)
            return False
        if not self.get_capabilities().get("passive_mode"):
            logger.error("Passive mode control unavailable: missing mapped entities")
            return False
        if self.context.simulation_mode:
            self._set_status(passive_mode=mode, api_status="Simulation")
            return True

        current = self._get_int("passive_charge_enable")
        if current == target:
            self._set_status(passive_mode=mode, api_status="Connected")
            return True

        if target == 2:
            self._call_service("switch", "turn_on", self.entities["switch_passive_charge"], None)
        elif target == 1:
            self._call_service("switch", "turn_on", self.entities["switch_passive_discharge"], None)
        else:
            self._turn_off_passive_mode(current)

        actual = self._wait_for_int_value(
            "passive_charge_enable",
            target,
            attempts=MODE_VERIFY_ATTEMPTS,
            delay_seconds=MODE_VERIFY_DELAY_SECONDS,
        )
        if actual != target:
            self._set_status(api_status=f"Passive mode verify failed: expected {target}, got {actual}")
            return False

        self._set_status(
            passive_mode=PASSIVE_MODE_VALUE_TO_SELECT.get(actual, mode),
            api_status="Connected",
        )
        return True

    def _read_schedule_from_ha(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "charge": self._read_slots("charge"),
            "discharge": self._read_slots("discharge"),
        }

    def _read_schedule_inputs_from_ha(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "charge": self._read_slot_inputs("charge"),
            "discharge": self._read_slot_inputs("discharge"),
        }

    def _get_passive_mode(self) -> Optional[str]:
        if "passive_charge_enable" not in self.entities:
            return None
        value = self._get_int("passive_charge_enable")
        if value is None:
            return None
        return PASSIVE_MODE_VALUE_TO_SELECT.get(value, "Off")

    def _read_slots(self, slot_type: str) -> List[Dict[str, Any]]:
        count = 7
        enabled_mask = self._get_int("charge_time_enable" if slot_type == "charge" else "discharge_time_enable") or 0
        periods: List[Dict[str, Any]] = []
        for index in range(1, count + 1):
            if not enabled_mask & (1 << (index - 1)):
                continue
            start = self._get_state_value(f"{slot_type}{index}_start_time")
            end = self._get_state_value(f"{slot_type}{index}_end_time")
            percent = self._get_float(f"{slot_type}{index}_power_percent")
            if not start or not end:
                continue
            duration = self._duration_minutes(start, end)
            periods.append(
                {
                    "start": start,
                    "duration": duration,
                    "power": self._percent_to_watts(percent or 0),
                }
            )
        return periods

    def _read_slot_inputs(self, slot_type: str) -> List[Dict[str, Any]]:
        count = 7
        enable_key = "charge_time_enable_input" if slot_type == "charge" else "discharge_time_enable_input"
        enabled_mask = self._get_int(enable_key) or 0
        periods: List[Dict[str, Any]] = []
        for index in range(1, count + 1):
            if not enabled_mask & (1 << (index - 1)):
                continue
            start = self._get_state_value(f"{slot_type}{index}_start_time_input")
            end = self._get_state_value(f"{slot_type}{index}_end_time_input")
            percent = self._get_float(f"{slot_type}{index}_power_percent_input")
            if not start or not end:
                continue
            duration = self._duration_minutes(start, end)
            periods.append(
                {
                    "start": start,
                    "duration": duration,
                    "power": self._percent_to_watts(percent or 0),
                }
            )
        return periods

    def _write_slots(self, slot_type: str, periods: List[Dict[str, Any]]) -> None:
        for index in range(1, 8):
            if index <= len(periods):
                period = periods[index - 1]
                end_time = self._end_time(period["start"], int(period["duration"]))
                power_percent = self._watts_to_percent(int(period["power"]))
                self._set_text(f"{slot_type}{index}_start_time_input", period["start"])
                self._set_text(f"{slot_type}{index}_end_time_input", end_time)
                self._set_number(f"{slot_type}{index}_power_percent_input", power_percent)
                self._set_number(f"{slot_type}{index}_day_mask_input", 127)
            else:
                self._set_text(f"{slot_type}{index}_start_time_input", "00:00")
                self._set_text(f"{slot_type}{index}_end_time_input", "00:00")
                self._set_number(f"{slot_type}{index}_power_percent_input", 0)
                self._set_number(f"{slot_type}{index}_day_mask_input", 0)

    def _schedule_matches(self, actual: Dict[str, List[Dict[str, Any]]], expected: Dict[str, List[Dict[str, Any]]]) -> bool:
        def _normalize(items: List[Dict[str, Any]]) -> List[tuple[str, int, int]]:
            return sorted(
                (
                    str(item.get("start")),
                    int(item.get("duration", 0)),
                    int(item.get("power", 0)),
                )
                for item in items
            )

        return _normalize(actual.get("charge", [])) == _normalize(expected.get("charge", [])) and _normalize(
            actual.get("discharge", [])
        ) == _normalize(expected.get("discharge", []))

    def _wait_for_schedule(
        self,
        expected: Dict[str, List[Dict[str, Any]]],
        attempts: int = 30,
        delay_seconds: float = 2.0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        actual = self._read_schedule_from_ha()
        if self._schedule_matches(actual, expected):
            return actual

        refresh_keys = self._schedule_refresh_keys()
        for _attempt in range(attempts):
            self._refresh_entities(refresh_keys)
            time.sleep(delay_seconds)
            actual = self._read_schedule_from_ha()
            if self._schedule_matches(actual, expected):
                return actual
        return actual

    def _wait_for_schedule_inputs(
        self,
        expected: Dict[str, List[Dict[str, Any]]],
        attempts: int = SCHEDULE_INPUT_VERIFY_ATTEMPTS,
        delay_seconds: float = SCHEDULE_INPUT_VERIFY_DELAY_SECONDS,
    ) -> Dict[str, List[Dict[str, Any]]]:
        actual = self._read_schedule_inputs_from_ha()
        if self._schedule_matches(actual, expected):
            return actual

        for _attempt in range(attempts):
            time.sleep(delay_seconds)
            actual = self._read_schedule_inputs_from_ha()
            if self._schedule_matches(actual, expected):
                return actual
        return actual

    def _deserialize_schedule(self, schedule_json: str) -> Dict[str, List[Dict[str, Any]]]:
        try:
            data = json.loads(schedule_json)
        except json.JSONDecodeError:
            return {"charge": [], "discharge": []}
        if not isinstance(data, dict):
            return {"charge": [], "discharge": []}
        return {
            "charge": list(data.get("charge") or []),
            "discharge": list(data.get("discharge") or []),
        }

    def _build_enable_mask(self, count: int) -> int:
        mask = 0
        for idx in range(max(0, count)):
            mask |= 1 << idx
        return mask

    def _watts_to_percent(self, power_w: int) -> int:
        if self.inverter_power_reference_w <= 0:
            raise ValueError("Invalid Modbus inverter power reference")
        percent = round((max(0, power_w) / float(self.inverter_power_reference_w)) * 100)
        return max(0, min(100, int(percent)))

    def _percent_to_watts(self, percent: float) -> int:
        return int(round((max(0.0, float(percent)) / 100.0) * self.inverter_power_reference_w))

    def _duration_minutes(self, start_hhmm: str, end_hhmm: str) -> int:
        start_minutes = int(start_hhmm[:2]) * 60 + int(start_hhmm[3:])
        end_minutes = int(end_hhmm[:2]) * 60 + int(end_hhmm[3:])
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60
        return end_minutes - start_minutes

    def _end_time(self, start_hhmm: str, duration_minutes: int) -> str:
        start_minutes = int(start_hhmm[:2]) * 60 + int(start_hhmm[3:])
        end_minutes = (start_minutes + duration_minutes) % (24 * 60)
        return f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"

    def _get_state_value(self, key: str) -> Optional[str]:
        entity_id = self.entities.get(key)
        if not entity_id:
            return None
        state = self._get_state_payload(entity_id)
        if not state:
            return None
        value = state.get("state")
        if value in (None, "unknown", "unavailable"):
            return None
        return str(value)

    def _get_state_payload(self, entity_id: str) -> Optional[Dict[str, Any]]:
        if self._state_snapshot is not None:
            return self._state_snapshot.get(entity_id)
        return self.ha_api.get_entity_state(entity_id)

    @contextmanager
    def _state_snapshot_context(self):
        if self._state_snapshot is not None:
            yield
            return

        states = self.ha_api.get_states()
        self._state_snapshot = {
            state.get("entity_id"): state
            for state in states
            if isinstance(state, dict) and state.get("entity_id")
        }
        try:
            yield
        finally:
            self._state_snapshot = None

    def _get_float(self, key: str) -> Optional[float]:
        value = self._get_state_value(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_int(self, key: str) -> Optional[int]:
        value = self._get_state_value(key)
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _wait_for_int_value(self, key: str, expected: int, attempts: int = 6, delay_seconds: float = 0.5) -> Optional[int]:
        actual = self._get_int(key)
        if actual == expected:
            return actual
        for _attempt in range(attempts):
            self._refresh_entities([key])
            time.sleep(delay_seconds)
            actual = self._get_int(key)
            if actual == expected:
                return actual
        return actual

    def _schedule_refresh_keys(self) -> List[str]:
        keys = ["app_mode", "charge_time_enable", "discharge_time_enable"]
        for slot_type in ("charge", "discharge"):
            for index in range(1, 8):
                keys.extend(
                    [
                        f"{slot_type}{index}_start_time",
                        f"{slot_type}{index}_end_time",
                        f"{slot_type}{index}_power_percent",
                        f"{slot_type}{index}_day_mask",
                    ]
                )
        return [key for key in keys if key in self.entities]

    def _refresh_entities(self, keys: List[str]) -> None:
        seen: set[str] = set()
        for key in keys:
            entity_id = self.entities.get(key)
            if not entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            ok = self.ha_api.call_service("homeassistant", "update_entity", {"entity_id": entity_id})
            if not ok:
                logger.debug("Failed to refresh HA entity for %s (%s)", key, entity_id)

    def _get_signed_power(self, power_key: str, direction_key: str) -> Optional[float]:
        power = self._get_float(power_key)
        direction = self._get_int(direction_key)
        if power is None:
            return None
        if direction is None:
            return power
        if direction < 0:
            return -abs(power)
        if direction > 0:
            return abs(power)
        return 0.0 if abs(power) < 0.001 else power

    def _turn_off_passive_mode(self, current: Optional[int]) -> None:
        if current == 2:
            self._call_service("switch", "turn_off", self.entities["switch_passive_charge"], None)
            return
        if current == 1:
            self._call_service("switch", "turn_off", self.entities["switch_passive_discharge"], None)
            return

        self._call_service("switch", "turn_off", self.entities["switch_passive_charge"], None)
        self._call_service("switch", "turn_off", self.entities["switch_passive_discharge"], None)

    def _set_number(self, key: str, value: int) -> bool:
        entity_id = self.entities.get(key)
        if not entity_id:
            raise ValueError(f"Missing Modbus number entity for {key}")
        return self._call_service("number", "set_value", entity_id, value)

    def _set_text(self, key: str, value: str) -> bool:
        entity_id = self.entities.get(key)
        if not entity_id:
            raise ValueError(f"Missing Modbus text entity for {key}")
        return self._call_service("text", "set_value", entity_id, value)

    def _call_service(self, domain: str, service: str, entity_id: str, value: Any) -> bool:
        data = {"entity_id": entity_id}
        if domain == "number":
            data["value"] = value
        elif domain == "text":
            data["value"] = value
        elif domain == "switch":
            pass
        ok = self.ha_api.call_service(domain, service, data)
        if not ok:
            raise RuntimeError(f"HA service failed: {domain}.{service} for {entity_id}")
        return True


def build_backend(context: BackendContext) -> BatteryBackend:
    """Create backend instance for configured provider."""
    provider = str(context.config.get("provider", "api")).lower()
    if provider == "modbus_ha":
        return ModbusHaBatteryBackend(context)
    return ApiBatteryBackend(context)
