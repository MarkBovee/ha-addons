"""Battery API add-on main entry point.

Controls SAJ Electric battery inverters via Home Assistant entities.
Provides charge/discharge scheduling through a single JSON text entity.
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent directory to path for shared module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import shared modules
from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.config_loader import load_addon_config, get_run_once_mode
from shared.ha_mqtt_discovery import (
    MqttDiscovery,
    EntityConfig,
    TextConfig,
    SelectConfig,
    get_mqtt_config_from_env,
)

# Import local modules
from .saj_api import SajApiClient
from .models import BatteryChargeType, ChargingPeriod, get_today_weekday_mask

# Configure logging
logger = setup_logging(name=__name__)

# Battery API configuration defaults
BA_CONFIG_DEFAULTS = {
    'poll_interval_seconds': 60,
    'log_level': 'info',
    'simulation_mode': False,
}

BA_REQUIRED_FIELDS = ['saj_username', 'saj_password', 'device_serial_number', 'plant_uid']

# Example schedule JSON for documentation
SCHEDULE_EXAMPLE = '''{
  "charge": [
    {"start": "02:00", "power": 3000, "duration": 180}
  ],
  "discharge": [
    {"start": "17:00", "power": 2500, "duration": 120}
  ]
}'''

# Battery mode options for the select entity
BATTERY_MODE_OPTIONS = ["Self-consumption", "Time-of-use", "AI"]
BATTERY_MODE_API_MAP = {
    "Self-consumption": "self_consumption",
    "Time-of-use": "time_of_use",
    "AI": "ai",
}
BATTERY_MODE_REVERSE_MAP = {v: k for k, v in BATTERY_MODE_API_MAP.items()}

# Map from API response mode (hyphenated) to select option
API_MODE_TO_SELECT = {
    "self-consumption": "Self-consumption",
    "time-of-use": "Time-of-use",
    "ai": "AI",
}


def load_config() -> dict:
    """Load Battery API configuration."""
    config = load_addon_config(
        defaults=BA_CONFIG_DEFAULTS,
        required_fields=BA_REQUIRED_FIELDS
    )
    
    # Log level adjustment
    log_level = config.get('log_level', 'info').upper()
    if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR'):
        logging.getLogger().setLevel(getattr(logging, log_level))
    
    logger.info("Loaded configuration: device=%s, poll=%ds, simulation=%s",
                config.get('device_serial_number', 'unknown')[:8] + "...",
                config['poll_interval_seconds'],
                config.get('simulation_mode', False))
    
    return config


class ScheduleValidationError(Exception):
    """Raised when schedule validation fails."""
    pass


def validate_period(period: dict, index: int, period_type: str) -> Dict[str, Any]:
    """Validate a single period object.
    
    Args:
        period: Period dictionary to validate
        index: Index in the array (for error messages)
        period_type: 'charge' or 'discharge' (for error messages)
        
    Returns:
        Validated period with normalized values
        
    Raises:
        ScheduleValidationError: If validation fails
    """
    if not isinstance(period, dict):
        raise ScheduleValidationError(f"{period_type}[{index}] must be an object")
    
    # Required fields
    if 'start' not in period:
        raise ScheduleValidationError(f"{period_type}[{index}] missing 'start' (format: 'HH:MM')")
    if 'power' not in period:
        raise ScheduleValidationError(f"{period_type}[{index}] missing 'power' (watts)")
    if 'duration' not in period:
        raise ScheduleValidationError(f"{period_type}[{index}] missing 'duration' (minutes)")
    
    # Validate start time format
    start = period['start']
    if not isinstance(start, str) or len(start) != 5 or start[2] != ':':
        raise ScheduleValidationError(f"{period_type}[{index}] 'start' must be 'HH:MM' format")
    try:
        hour, minute = int(start[:2]), int(start[3:])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except (ValueError, TypeError):
        raise ScheduleValidationError(f"{period_type}[{index}] invalid time: {start}")
    
    # Validate power
    power = period['power']
    if not isinstance(power, (int, float)) or power < 0 or power > 10000:
        raise ScheduleValidationError(f"{period_type}[{index}] 'power' must be 0-10000 watts")
    
    # Validate duration
    duration = period['duration']
    if not isinstance(duration, (int, float)) or duration < 0 or duration > 1440:
        raise ScheduleValidationError(f"{period_type}[{index}] 'duration' must be 0-1440 minutes")
    
    return {
        'start': start,
        'power': int(power),
        'duration': int(duration),
    }


def validate_schedule(json_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """Validate complete schedule JSON.
    
    Expected format:
    {
      "charge": [
        {"start": "HH:MM", "power": 3000, "duration": 180},
        ...
      ],
      "discharge": [
        {"start": "HH:MM", "power": 2500, "duration": 120},
        ...
      ]
    }
    
    Args:
        json_str: JSON string (or empty/null for clearing)
        
    Returns:
        Validated schedule dict with 'charge' and 'discharge' lists
        
    Raises:
        ScheduleValidationError: If validation fails
    """
    # Handle empty/clear cases
    if not json_str or json_str.strip() in ('', '{}', 'null', 'clear'):
        return {'charge': [], 'discharge': []}
    
    # Parse JSON
    try:
        schedule = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ScheduleValidationError(f"Invalid JSON: {e}")
    
    if not isinstance(schedule, dict):
        raise ScheduleValidationError("Schedule must be a JSON object with 'charge' and/or 'discharge' arrays")
    
    result = {'charge': [], 'discharge': []}
    
    # Validate charge periods
    if 'charge' in schedule:
        charge_list = schedule['charge']
        if not isinstance(charge_list, list):
            raise ScheduleValidationError("'charge' must be an array")
        if len(charge_list) > 3:
            raise ScheduleValidationError(f"Maximum 3 charge periods allowed (got {len(charge_list)})")
        for i, period in enumerate(charge_list):
            result['charge'].append(validate_period(period, i, 'charge'))
    
    # Validate discharge periods
    if 'discharge' in schedule:
        discharge_list = schedule['discharge']
        if not isinstance(discharge_list, list):
            raise ScheduleValidationError("'discharge' must be an array")
        if len(discharge_list) > 6:
            raise ScheduleValidationError(f"Maximum 6 discharge periods allowed (got {len(discharge_list)})")
        for i, period in enumerate(discharge_list):
            result['discharge'].append(validate_period(period, i, 'discharge'))
    
    # Check for overlapping time periods within same type
    for period_type in ('charge', 'discharge'):
        periods = result[period_type]
        for i, p1 in enumerate(periods):
            start1 = int(p1['start'][:2]) * 60 + int(p1['start'][3:])
            end1 = start1 + p1['duration']
            for j, p2 in enumerate(periods[i+1:], i+1):
                start2 = int(p2['start'][:2]) * 60 + int(p2['start'][3:])
                end2 = start2 + p2['duration']
                # Check overlap (handling midnight wrap would need more logic)
                if start1 < end2 and start2 < end1:
                    raise ScheduleValidationError(
                        f"{period_type}[{i}] and {period_type}[{j}] overlap "
                        f"({p1['start']} +{p1['duration']}min vs {p2['start']} +{p2['duration']}min)"
                    )
    
    # Check for overlapping time periods across charge and discharge
    for i, p1 in enumerate(result['charge']):
        start1 = int(p1['start'][:2]) * 60 + int(p1['start'][3:])
        end1 = start1 + p1['duration']
        for j, p2 in enumerate(result['discharge']):
            start2 = int(p2['start'][:2]) * 60 + int(p2['start'][3:])
            end2 = start2 + p2['duration']
            if start1 < end2 and start2 < end1:
                raise ScheduleValidationError(
                    f"charge[{i}] and discharge[{j}] overlap "
                    f"({p1['start']} +{p1['duration']}min vs {p2['start']} +{p2['duration']}min)"
                )
    
    return result


class BatteryApiAddon:
    """Main add-on class for Battery API."""
    
    def __init__(self, config: dict, shutdown_event):
        """Initialize the add-on."""
        self.config = config
        self.shutdown_event = shutdown_event
        self.simulation_mode = config.get('simulation_mode', False)
        
        # Thread lock for protecting SAJ API calls and status updates
        # MQTT callbacks run in a separate thread, so we need to synchronize
        self._api_lock = threading.Lock()
        
        # Schedule state
        self.schedule_json = "{}"
        self.validated_schedule: Optional[Dict[str, List]] = None
        
        # Battery mode setting (what user selected)
        self.battery_mode_setting = "Self-consumption"  # Default
        
        # Status (updated from SAJ API)
        self.status = {
            'battery_soc': None,
            'battery_power': None,  # W (positive=charging, negative=discharging)
            'battery_direction': None,  # 1=charging, -1=discharging, 0=idle
            'battery_capacity': None,
            'battery_current': None,
            'battery_charge_today': None,
            'battery_discharge_today': None,
            'battery_charge_total': None,
            'battery_discharge_total': None,
            'pv_power': None,       # W
            'pv_direction': None,
            'solar_power': None,
            'grid_power': None,     # W (positive=importing, negative=exporting)
            'grid_direction': None,  # 1=importing, -1=exporting, 0=none
            'load_power': None,     # W
            'home_load_power': None,
            'backup_load_power': None,
            'input_output_power': None,
            'output_direction': None,
            'schedule_status': 'No schedule',
            'last_applied': None,
            'api_status': 'Initializing',
            'current_schedule': None,  # Fetched on startup and after apply
            'last_update': None,    # Timestamp from inverter
            'user_mode': None,      # Current inverter mode
            'plant_name': None,
            'inverter_model': None,
            'inverter_sn': None,
        }
        
        # Initialize SAJ API client
        self.saj_client = SajApiClient(
            username=config['saj_username'],
            password=config['saj_password'],
            device_serial=config['device_serial_number'],
            plant_uid=config['plant_uid'],
            simulation_mode=self.simulation_mode,
        )
        
        # MQTT Discovery client (initialized in setup)
        self.mqtt: Optional[MqttDiscovery] = None
    
    def setup(self) -> bool:
        """Set up the add-on (MQTT, entities, etc.)."""
        # Set up MQTT Discovery
        mqtt_config = get_mqtt_config_from_env()
        
        try:
            self.mqtt = MqttDiscovery(
                addon_name="Battery API",
                addon_id="battery_api",
                mqtt_host=mqtt_config['mqtt_host'],
                mqtt_port=mqtt_config['mqtt_port'],
                mqtt_user=mqtt_config.get('mqtt_user'),
                mqtt_password=mqtt_config.get('mqtt_password'),
                manufacturer="SAJ Electric",
                model="Inverter Battery Control",
            )
            
            if self.mqtt.connect():
                logger.info("MQTT connected successfully")
                self._publish_discovery_configs()
            else:
                logger.warning("MQTT connection failed, entities will not be available")
                self.mqtt = None
        except ImportError:
            logger.warning("paho-mqtt not available, entities will not be available")
            self.mqtt = None
        except Exception as e:
            logger.warning("MQTT setup failed: %s", e)
            self.mqtt = None
        
        # Test SAJ API connection
        if self.simulation_mode:
            logger.info("SIMULATION MODE: SAJ API calls will be logged but not executed")
            self.status['api_status'] = 'Simulation'
            self.status['current_schedule'] = '{"mode": "simulation", "charge": [], "discharge": []}'
        else:
            try:
                if self.saj_client.authenticate():
                    logger.info("SAJ API authentication successful")
                    self.status['api_status'] = 'Connected'
                    # Fetch current schedule once at startup
                    self._fetch_current_schedule()
                else:
                    logger.error("SAJ API authentication failed")
                    self.status['api_status'] = 'Auth Failed'
            except Exception as e:
                logger.error("SAJ API connection error: %s", e)
                self.status['api_status'] = f'Error: {e}'
        
        return True
    
    def _cleanup_old_entities(self):
        """Remove old/deprecated MQTT Discovery entities from previous versions.
        
        Publishes empty configs to remove old entities that were renamed or removed.
        This is idempotent - safe to call even if entities don't exist.
        """
        if not self.mqtt:
            return
        
        # List of old entity IDs that were renamed or removed
        old_entities = [
            # v0.1.x had separate charge/discharge text entities
            ("text", "charge_schedule"),
            ("text", "discharge_schedule"),
            # v0.2.0 renamed battery_mode_setting to battery_mode
            ("select", "battery_mode_setting"),
            # Any other deprecated entities can be added here
        ]
        
        for component, object_id in old_entities:
            try:
                self.mqtt.remove_entity(component, object_id)
                logger.debug("Sent removal for old entity: %s.battery_api_%s", component, object_id)
            except Exception as e:
                logger.debug("Could not remove old entity %s.%s: %s", component, object_id, e)
    
    def _publish_discovery_configs(self):
        """Publish MQTT Discovery configs for all entities."""
        if not self.mqtt:
            return
        
        # Clean up old entities from previous versions first
        self._cleanup_old_entities()
        
        logger.info("Publishing MQTT Discovery configs...")
        
        # ===== Control Entities =====
        
        # Battery Mode Setting (select entity for mode control)
        self.mqtt.publish_select(
            SelectConfig(
                object_id="battery_mode_setting",
                name="Battery Mode",
                options=BATTERY_MODE_OPTIONS,
                state=self.battery_mode_setting,
                icon="mdi:battery-sync",
                entity_category="config",
            ),
            command_callback=self._handle_mode_select,
        )
        
        # ===== Schedule Input Entity =====
        
        # Battery Schedule (unified JSON input)
        self.mqtt.publish_text(
            TextConfig(
                object_id="schedule",
                name="Battery Schedule",
                state=self.schedule_json,
                min_length=0,
                max_length=2048,
                icon="mdi:battery-clock",
                entity_category="config",
            ),
            command_callback=self._handle_schedule_input,
        )
        
        # ===== Status Entities (read-only sensors) =====
        
        # Battery SOC - with rich attributes showing all power flow data
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="battery_soc",
                name="Battery SOC",
                state=str(self.status.get('battery_soc', 0)) if self.status.get('battery_soc') is not None else "unknown",
                unit_of_measurement="%",
                device_class="battery",
                state_class="measurement",
                icon="mdi:battery",
                attributes=self._build_power_attributes(),
            )
        )
        
        # Battery Power (charging/discharging)
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="battery_power",
                name="Battery Power",
                state=str(int(self.status.get('battery_power', 0))) if self.status.get('battery_power') is not None else "unknown",
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
                icon="mdi:battery-charging",
                attributes={'direction': self._battery_direction_str()},
            )
        )
        
        # PV Power (solar production)
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="pv_power",
                name="PV Power",
                state=str(int(self.status.get('pv_power', 0))) if self.status.get('pv_power') is not None else "unknown",
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
                icon="mdi:solar-power",
            )
        )
        
        # Grid Power (import/export)
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="grid_power",
                name="Grid Power",
                state=str(int(self.status.get('grid_power', 0))) if self.status.get('grid_power') is not None else "unknown",
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
                icon="mdi:transmission-tower",
                attributes={'direction': self._grid_direction_str()},
            )
        )
        
        # Load Power (consumption)
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="load_power",
                name="Load Power",
                state=str(int(self.status.get('load_power', 0))) if self.status.get('load_power') is not None else "unknown",
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
                icon="mdi:home-lightning-bolt",
            )
        )
        
        # Schedule Status (shows validation result or active schedule summary)
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="schedule_status",
                name="Schedule Status",
                state=self.status.get('schedule_status', 'No schedule'),
                icon="mdi:calendar-check",
            )
        )
        
        # API Status
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="api_status",
                name="API Status",
                state=self.status.get('api_status', 'unknown') or "unknown",
                icon="mdi:api",
                entity_category="diagnostic",
            )
        )
        
        # Last Applied Timestamp
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="last_applied",
                name="Last Applied",
                state=self.status.get('last_applied', 'never') or "never",
                icon="mdi:clock-check-outline",
                entity_category="diagnostic",
            )
        )
        
        logger.info("Published %d entities", len(self.mqtt.get_published_entities()))
    
    def _handle_mode_select(self, mode: str):
        """Handle battery mode selection.
        
        Uses _api_lock to prevent concurrent SAJ API calls.
        """
        logger.info("Mode change: %s -> %s", self.battery_mode_setting, mode)
        
        if mode not in BATTERY_MODE_OPTIONS:
            logger.error("Invalid mode: %s (expected one of %s)", mode, BATTERY_MODE_OPTIONS)
            return
        
        with self._api_lock:
            # Store the setting
            self.battery_mode_setting = mode
            
            # Apply to inverter
            api_mode = BATTERY_MODE_API_MAP.get(mode, "self_consumption")
            
            if self.simulation_mode:
                logger.info("SIMULATION: Would set mode to %s", mode)
                self.status['api_status'] = 'Simulation'
            else:
                try:
                    success = self.saj_client.set_battery_mode(api_mode)
                    if success:
                        self.status['api_status'] = 'Connected'
                        logger.info("Mode set to %s successfully", mode)
                    else:
                        self.status['api_status'] = 'Mode Set Failed'
                        logger.error("Failed to set mode to %s", mode)
                except Exception as e:
                    self.status['api_status'] = f'Error: {e}'
                    logger.error("Mode setting error: %s", e)
            
            # Update entities
            self.update_entities()

    def _format_periods_compact(self, validated: dict) -> str:
        """Format validated schedule periods into a compact single-line summary."""
        parts = []
        for p in validated.get('charge', []):
            parts.append(f"CHG {p['start']} {p['power']}W/{p['duration']}m")
        for p in validated.get('discharge', []):
            parts.append(f"DIS {p['start']} {p['power']}W/{p['duration']}m")
        return ", ".join(parts) if parts else "empty"

    def _handle_schedule_input(self, json_str: str):
        """Handle schedule JSON input - validates and applies if valid."""
        # Step 1: Validate
        try:
            validated = validate_schedule(json_str)
            self.validated_schedule = validated
            self.schedule_json = json_str if json_str else "{}"
            
            charge_count = len(validated['charge'])
            discharge_count = len(validated['discharge'])
            
            if charge_count == 0 and discharge_count == 0:
                self.status['schedule_status'] = 'Cleared'
                logger.info("Schedule received: cleared")
            else:
                self.status['schedule_status'] = f'Valid: {charge_count} charge, {discharge_count} discharge'
                # Build compact period summary
                period_summary = self._format_periods_compact(validated)
                logger.info("Schedule received: %s", period_summary)
            
        except ScheduleValidationError as e:
            self.status['schedule_status'] = f'Invalid: {e}'
            logger.error("Schedule validation failed: %s", e)
            self.update_entities()
            return  # Don't apply invalid schedule
        
        # Step 2: Apply valid schedule
        self._apply_schedule()
    
    def _apply_schedule(self):
        """Apply the validated schedule to the inverter.
        
        Uses _api_lock to prevent concurrent SAJ API calls from main loop.
        """
        if self.validated_schedule is None:
            logger.warning("No validated schedule to apply")
            return
        
        with self._api_lock:
            # Determine weekday mask based on config
            schedule_days = self.config.get('schedule_days', 'today')
            if schedule_days == 'today':
                weekdays = get_today_weekday_mask()
            else:
                weekdays = "1,1,1,1,1,1,1"  # All days
            
            # Convert to ChargingPeriod objects
            periods: List[ChargingPeriod] = []
            
            for p in self.validated_schedule['charge']:
                periods.append(ChargingPeriod(
                    charge_type=BatteryChargeType.CHARGE,
                    start_time=p['start'],
                    duration_minutes=p['duration'],
                    power_w=p['power'],
                    weekdays=weekdays,
                ))
            
            for p in self.validated_schedule['discharge']:
                periods.append(ChargingPeriod(
                    charge_type=BatteryChargeType.DISCHARGE,
                    start_time=p['start'],
                    duration_minutes=p['duration'],
                    power_w=p['power'],
                    weekdays=weekdays,
                ))
            
            if not periods:
                logger.debug("Clearing schedule (no periods)")
            
            # Apply to inverter
            if self.simulation_mode:
                logger.info("SIMULATION: Schedule would be applied")
                self.status['last_applied'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.status['api_status'] = 'Simulation'
                # Update local schedule state (simulation)
                self.status['current_schedule'] = self.schedule_json
            else:
                try:
                    success = self.saj_client.save_schedule(periods)
                    if success:
                        self.status['last_applied'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.status['api_status'] = 'Connected'
                        # Update local schedule state - no need to re-fetch from API
                        self.status['current_schedule'] = self.schedule_json
                        logger.debug("Schedule applied to inverter")
                    else:
                        self.status['api_status'] = 'Apply Failed'
                        self.status['schedule_status'] = 'Apply failed'
                        logger.error("Failed to apply schedule")
                except Exception as e:
                    self.status['api_status'] = f'Error: {e}'
                    self.status['schedule_status'] = f'Error: {e}'
                    logger.error("Schedule application error: %s", e)
            
            # Update sensors
            self.update_entities()
    
    def _fetch_current_schedule(self):
        """Fetch current schedule from inverter and sync controls (called on startup and after apply)."""
        try:
            schedule = self.saj_client.get_schedule()
            if schedule:
                self.status['current_schedule'] = json.dumps(schedule)
                logger.debug("Fetched schedule from inverter: mode=%s, charge=%d, discharge=%d",
                           schedule.get('mode'), 
                           len(schedule.get('charge', [])),
                           len(schedule.get('discharge', [])))
                
                # Sync battery mode setting from inverter
                api_mode = schedule.get('mode')
                if api_mode and api_mode in API_MODE_TO_SELECT:
                    self.battery_mode_setting = API_MODE_TO_SELECT[api_mode]
                
                # Sync schedule JSON (rebuild from fetched data)
                schedule_for_input = {
                    "charge": schedule.get('charge', []),
                    "discharge": schedule.get('discharge', [])
                }
                if schedule_for_input['charge'] or schedule_for_input['discharge']:
                    self.schedule_json = json.dumps(schedule_for_input, indent=2)
                    self.validated_schedule = schedule_for_input
                    charge_count = len(schedule_for_input['charge'])
                    discharge_count = len(schedule_for_input['discharge'])
                    self.status['schedule_status'] = f'Synced: {charge_count} charge, {discharge_count} discharge'
            else:
                self.status['current_schedule'] = '{}'
                logger.warning("Failed to fetch current schedule")
        except Exception as e:
            logger.error("Error fetching current schedule: %s", e)
            self.status['current_schedule'] = '{}'
    
    def poll_status(self):
        """Poll SAJ API for current battery status."""
        if self.simulation_mode:
            self.status['battery_soc'] = 75
            self.status['battery_power'] = 500
            self.status['battery_direction'] = 1
            self.status['pv_power'] = 3000
            self.status['grid_power'] = -200
            self.status['grid_direction'] = -1
            self.status['load_power'] = 2500
            self.status['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.status['user_mode'] = 'EMS'
            self.status['battery_capacity'] = 50
            self.status['battery_current'] = 2.5
            self.status['plant_name'] = 'Simulation'
            self.status['inverter_model'] = 'HS2-8K-T2'
            self.status['inverter_sn'] = 'SIM123456'
            logger.debug("SIMULATION: Status poll (SOC=75%%, bat=500W, pv=3000W)")
            return
        
        try:
            # Use lock only for the API call itself
            with self._api_lock:
                flow_data = self.saj_client.get_energy_flow_data()
            
            if flow_data:
                # Core power values
                self.status['battery_soc'] = flow_data.get('battery_soc')
                self.status['battery_power'] = flow_data.get('battery_power')
                self.status['battery_direction'] = flow_data.get('battery_direction')
                self.status['pv_power'] = flow_data.get('pv_power')
                self.status['grid_power'] = flow_data.get('grid_power')
                self.status['grid_direction'] = flow_data.get('grid_direction')
                self.status['load_power'] = flow_data.get('load_power')
                
                # Extended battery info
                self.status['battery_capacity'] = flow_data.get('battery_capacity')
                self.status['battery_current'] = flow_data.get('battery_current')
                self.status['battery_charge_today'] = flow_data.get('battery_charge_today')
                self.status['battery_discharge_today'] = flow_data.get('battery_discharge_today')
                self.status['battery_charge_total'] = flow_data.get('battery_charge_total')
                self.status['battery_discharge_total'] = flow_data.get('battery_discharge_total')
                
                # Extended power info
                self.status['pv_direction'] = flow_data.get('pv_direction')
                self.status['solar_power'] = flow_data.get('solar_power')
                self.status['home_load_power'] = flow_data.get('home_load_power')
                self.status['backup_load_power'] = flow_data.get('backup_load_power')
                self.status['input_output_power'] = flow_data.get('input_output_power')
                self.status['output_direction'] = flow_data.get('output_direction')
                
                # Device info
                self.status['plant_name'] = flow_data.get('plant_name')
                self.status['inverter_model'] = flow_data.get('inverter_model')
                self.status['inverter_sn'] = flow_data.get('inverter_sn')
                
                self.status['last_update'] = flow_data.get('update_time')
                self.status['user_mode'] = flow_data.get('user_mode')
                self.status['api_status'] = 'Connected'
        except Exception as e:
            logger.error("Status poll failed: %s", e)
            self.status['api_status'] = f'Poll Error: {e}'
    
    def _battery_direction_str(self) -> str:
        """Convert battery direction code to human-readable string.
        
        SAJ API: batteryDirection > 0 = discharging, < 0 = charging, 0 = idle
        """
        direction = self.status.get('battery_direction')
        if direction is None:
            return "Unknown"
        if direction > 0:
            return "Discharging"
        if direction < 0:
            return "Charging"
        return "Idle"
    
    def _grid_direction_str(self) -> str:
        """Convert grid direction code to human-readable string."""
        direction = self.status.get('grid_direction')
        if direction is None:
            return "Unknown"
        if direction > 0:
            return "Importing"
        if direction < 0:
            return "Exporting"
        return "Standby"
    
    def _pv_direction_str(self) -> str:
        """Convert PV direction code to human-readable string."""
        direction = self.status.get('pv_direction')
        if direction is None:
            return "Unknown"
        if direction != 0:
            return "Exporting"
        return "Idle"
    
    def _output_direction_str(self) -> str:
        """Convert output direction code to human-readable string."""
        direction = self.status.get('output_direction')
        if direction is None:
            return "Unknown"
        return str(direction)
    
    def _build_power_attributes(self) -> dict:
        """Build comprehensive attributes dict for the main battery SOC sensor.
        
        Mirrors the attributes from the SAJ integration's sensor.
        """
        attrs = {
            # Device info
            'plant_name': self.status.get('plant_name'),
            'plant_uid': self.config.get('plant_uid'),
            'inverter_model': self.status.get('inverter_model'),
            'inverter_sn': self.status.get('inverter_sn'),
            
            # Battery info
            'battery_capacity': self.status.get('battery_capacity'),
            'battery_current': self.status.get('battery_current'),
            'battery_power': self.status.get('battery_power'),
            'battery_direction': self._battery_direction_str(),
            
            # Grid info
            'grid_power': self.status.get('grid_power'),
            'grid_direction': self._grid_direction_str(),
            
            # Solar/PV info
            'photovoltaics_power': self.status.get('pv_power'),
            'photovoltaics_direction': self._pv_direction_str(),
            'solar_power': self.status.get('solar_power'),
            
            # Load info
            'total_load_power': self.status.get('load_power'),
            'home_load_power': self.status.get('home_load_power'),
            'backup_load_power': self.status.get('backup_load_power'),
            
            # I/O
            'input_output_power': self.status.get('input_output_power'),
            'output_direction': self._output_direction_str(),
            
            # Energy totals
            'battery_charge_today_energy': self.status.get('battery_charge_today'),
            'battery_discharge_today_energy': self.status.get('battery_discharge_today'),
            'battery_charge_total_energy': self.status.get('battery_charge_total'),
            'battery_discharge_total_energy': self.status.get('battery_discharge_total'),
            
            # Mode and timing
            'user_mode': self.status.get('user_mode'),
            'last_update': self.status.get('last_update'),
        }
        
        # Filter out None values for cleaner output
        return {k: v for k, v in attrs.items() if v is not None}
    
    def update_entities(self):
        """Publish updated status to MQTT entities."""
        if not self.mqtt:
            return
        
        # Build common attributes for power sensors
        power_attrs = self._build_power_attributes()
        
        # Battery SOC - with all attributes
        soc = self.status.get('battery_soc')
        self.mqtt.update_state("sensor", "battery_soc", 
                               str(soc) if soc is not None else "unknown",
                               attributes=power_attrs)
        
        # Battery Power (charging/discharging)
        bat_power = self.status.get('battery_power')
        self.mqtt.update_state("sensor", "battery_power",
                               str(int(bat_power)) if bat_power is not None else "unknown",
                               attributes={'direction': self._battery_direction_str()})
        
        # PV Power
        pv_power = self.status.get('pv_power')
        self.mqtt.update_state("sensor", "pv_power",
                               str(int(pv_power)) if pv_power is not None else "unknown")
        
        # Grid Power
        grid_power = self.status.get('grid_power')
        self.mqtt.update_state("sensor", "grid_power",
                               str(int(grid_power)) if grid_power is not None else "unknown",
                               attributes={'direction': self._grid_direction_str()})
        
        # Load Power
        load_power = self.status.get('load_power')
        self.mqtt.update_state("sensor", "load_power",
                               str(int(load_power)) if load_power is not None else "unknown")
        
        self.mqtt.update_state("sensor", "schedule_status", 
                               self.status.get('schedule_status') or "No schedule")
        
        self.mqtt.update_state("sensor", "api_status", 
                               self.status.get('api_status') or "unknown")
        
        self.mqtt.update_state("sensor", "last_applied", 
                               self.status.get('last_applied') or "never")
        
        # Update control entities with synced values
        self.mqtt.update_state("select", "battery_mode_setting", 
                               self.battery_mode_setting)
        
        self.mqtt.update_state("text", "schedule",
                               self.schedule_json)
    
    def run(self):
        """Main run loop."""
        poll_interval = self.config['poll_interval_seconds']
        run_once = get_run_once_mode()
        
        logger.info("Starting main loop (poll every %ds)", poll_interval)
        
        while not self.shutdown_event.is_set():
            try:
                # Poll status - uses lock internally only for API calls
                self.poll_status()
                self.update_entities()
                
                # Log status every poll
                soc = self.status.get('battery_soc')
                bat_power = self.status.get('battery_power', 0)
                pv_power = self.status.get('pv_power', 0)
                grid_power = self.status.get('grid_power', 0)
                load_power = self.status.get('load_power', 0)
                
                logger.info("Poll: SOC=%s%%, Bat=%dW, PV=%dW, Grid=%dW, Load=%dW, Mode=%s, API=%s",
                           soc if soc is not None else '?',
                           int(bat_power) if bat_power else 0,
                           int(pv_power) if pv_power else 0,
                           int(grid_power) if grid_power else 0,
                           int(load_power) if load_power else 0,
                           self.battery_mode_setting,
                           self.status.get('api_status', 'unknown'))
                
            except Exception as e:
                logger.error("Error in main loop: %s", e)
            
            if run_once:
                logger.info("RUN_ONCE mode: exiting")
                break
            
            if not sleep_with_shutdown_check(self.shutdown_event, poll_interval):
                break
        
        logger.info("Main loop exiting")
    
    def cleanup(self):
        """Clean up resources."""
        if self.mqtt:
            try:
                self.mqtt.disconnect()
            except Exception:
                pass
        logger.info("Cleanup complete")


def main():
    """Main entry point for the Battery API add-on."""
    logger.info("Battery API Add-on Starting")
    
    shutdown_event = setup_signal_handlers(logger)
    
    try:
        config = load_config()
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)
    
    addon = BatteryApiAddon(config, shutdown_event)
    
    try:
        if addon.setup():
            addon.run()
        else:
            logger.error("Add-on setup failed")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error("Unhandled exception: %s", e)
        raise
    finally:
        addon.cleanup()
    
    logger.info("Battery API Add-on stopped")


if __name__ == "__main__":
    main()
