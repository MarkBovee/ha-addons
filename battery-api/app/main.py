"""Battery API add-on main entry point.

Controls SAJ Electric battery inverters via Home Assistant entities.
Provides charge/discharge scheduling through JSON-based text entities.
"""

import json
import logging
import os
import sys
import time
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
    get_mqtt_config_from_env,
)

# Import local modules
from .saj_api import SajApiClient
from .models import BatteryChargeType, ChargingPeriod

# Configure logging
logger = setup_logging(name=__name__)

# Entity prefix for all battery-api entities
ENTITY_PREFIX = "ba"

# Battery API configuration defaults
BA_CONFIG_DEFAULTS = {
    'poll_interval_seconds': 60,
    'log_level': 'info',
    'simulation_mode': False,
}

BA_REQUIRED_FIELDS = ['saj_username', 'saj_password', 'device_serial_number', 'plant_uid']

# Example schedule JSON for documentation
SCHEDULE_EXAMPLE = '''[
  {"start": "02:00", "power": 3000, "duration": 180},
  {"start": "14:00", "power": 2000, "duration": 60}
]'''


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


def parse_schedule_json(json_str: str) -> List[Dict[str, Any]]:
    """Parse and validate schedule JSON.
    
    Expected format:
    [
      {"start": "HH:MM", "power": 3000, "duration": 180},
      ...
    ]
    
    Args:
        json_str: JSON string (or empty string for no schedule)
        
    Returns:
        List of period dictionaries
        
    Raises:
        ValueError: If JSON is invalid or periods are malformed
    """
    if not json_str or json_str.strip() in ('', '[]'):
        return []
    
    try:
        periods = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    
    if not isinstance(periods, list):
        raise ValueError("Schedule must be a JSON array")
    
    validated = []
    for i, period in enumerate(periods):
        if not isinstance(period, dict):
            raise ValueError(f"Period {i} must be an object")
        
        # Required fields
        if 'start' not in period:
            raise ValueError(f"Period {i} missing 'start' field (format: 'HH:MM')")
        if 'power' not in period:
            raise ValueError(f"Period {i} missing 'power' field (watts)")
        if 'duration' not in period:
            raise ValueError(f"Period {i} missing 'duration' field (minutes)")
        
        # Validate start time format
        start = period['start']
        if not isinstance(start, str) or len(start) != 5 or start[2] != ':':
            raise ValueError(f"Period {i} 'start' must be 'HH:MM' format")
        try:
            hour, minute = int(start[:2]), int(start[3:])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"Period {i} 'start' has invalid time: {start}")
        
        # Validate power
        power = period['power']
        if not isinstance(power, (int, float)) or power < 0 or power > 10000:
            raise ValueError(f"Period {i} 'power' must be 0-10000 watts")
        
        # Validate duration
        duration = period['duration']
        if not isinstance(duration, (int, float)) or duration < 0 or duration > 1440:
            raise ValueError(f"Period {i} 'duration' must be 0-1440 minutes")
        
        validated.append({
            'start': start,
            'power': int(power),
            'duration': int(duration),
        })
    
    return validated


class BatteryApiAddon:
    """Main add-on class for Battery API.
    
    Manages the lifecycle of the add-on:
    - SAJ API client for inverter communication
    - MQTT entities for control and status
    - Main polling loop
    """
    
    def __init__(self, config: dict, shutdown_event):
        """Initialize the add-on."""
        self.config = config
        self.shutdown_event = shutdown_event
        self.simulation_mode = config.get('simulation_mode', False)
        
        # Schedule state (JSON strings)
        self.charge_schedule_json = "[]"
        self.discharge_schedule_json = "[]"
        
        # Status (updated from SAJ API)
        self.status = {
            'battery_soc': None,
            'battery_mode': None,
            'active_schedule': None,
            'last_applied': None,
            'api_status': 'Initializing',
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
            self.status['api_status'] = 'Simulation Mode'
        else:
            try:
                if self.saj_client.authenticate():
                    logger.info("SAJ API authentication successful")
                    self.status['api_status'] = 'Connected'
                else:
                    logger.error("SAJ API authentication failed")
                    self.status['api_status'] = 'Authentication Failed'
            except Exception as e:
                logger.error("SAJ API connection error: %s", e)
                self.status['api_status'] = f'Error: {e}'
        
        return True
    
    def _publish_discovery_configs(self):
        """Publish MQTT Discovery configs for all entities."""
        if not self.mqtt:
            return
        
        logger.info("Publishing MQTT Discovery configs...")
        
        # ===== Schedule Input Entities =====
        
        # Charge Schedule (JSON text input)
        self.mqtt.publish_text(
            TextConfig(
                object_id="charge_schedule",
                name="Charge Schedule",
                state=self.charge_schedule_json,
                min_length=0,
                max_length=1024,
                icon="mdi:battery-charging-high",
                entity_category="config",
            ),
            command_callback=self._handle_charge_schedule,
        )
        
        # Discharge Schedule (JSON text input)
        self.mqtt.publish_text(
            TextConfig(
                object_id="discharge_schedule",
                name="Discharge Schedule",
                state=self.discharge_schedule_json,
                min_length=0,
                max_length=1024,
                icon="mdi:battery-arrow-down",
                entity_category="config",
            ),
            command_callback=self._handle_discharge_schedule,
        )
        
        # ===== Status Entities (read-only sensors) =====
        
        # Battery SOC
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="battery_soc",
                name="Battery State of Charge",
                state=str(self.status.get('battery_soc', 0)) if self.status.get('battery_soc') is not None else "unknown",
                unit_of_measurement="%",
                device_class="battery",
                state_class="measurement",
                icon="mdi:battery",
            )
        )
        
        # Battery Mode
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="battery_mode",
                name="Battery Mode",
                state=self.status.get('battery_mode', 'unknown') or "unknown",
                icon="mdi:battery-sync",
            )
        )
        
        # Active Schedule (JSON showing current schedule)
        self.mqtt.publish_sensor(
            EntityConfig(
                object_id="active_schedule",
                name="Active Schedule",
                state=self.status.get('active_schedule') or "none",
                icon="mdi:calendar-clock",
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
                name="Last Schedule Applied",
                state=self.status.get('last_applied', 'never') or "never",
                icon="mdi:clock-check-outline",
                entity_category="diagnostic",
            )
        )
        
        logger.info("Published %d entities", len(self.mqtt.get_published_entities()))
    
    def _handle_charge_schedule(self, json_str: str):
        """Handle charge schedule JSON input - validates and applies immediately."""
        logger.info("Received charge schedule: %s", json_str[:100] if json_str else "(empty)")
        
        try:
            periods = parse_schedule_json(json_str)
            self.charge_schedule_json = json_str if json_str else "[]"
            logger.info("Parsed %d charge periods", len(periods))
            
            # Apply schedule immediately
            self._apply_schedules()
            
        except ValueError as e:
            logger.error("Invalid charge schedule: %s", e)
            self.status['api_status'] = f'Invalid schedule: {e}'
            self.update_entities()
    
    def _handle_discharge_schedule(self, json_str: str):
        """Handle discharge schedule JSON input - validates and applies immediately."""
        logger.info("Received discharge schedule: %s", json_str[:100] if json_str else "(empty)")
        
        try:
            periods = parse_schedule_json(json_str)
            self.discharge_schedule_json = json_str if json_str else "[]"
            logger.info("Parsed %d discharge periods", len(periods))
            
            # Apply schedule immediately
            self._apply_schedules()
            
        except ValueError as e:
            logger.error("Invalid discharge schedule: %s", e)
            self.status['api_status'] = f'Invalid schedule: {e}'
            self.update_entities()
    
    def _apply_schedules(self):
        """Apply both charge and discharge schedules to the inverter."""
        # Parse both schedules
        try:
            charge_periods = parse_schedule_json(self.charge_schedule_json)
            discharge_periods = parse_schedule_json(self.discharge_schedule_json)
        except ValueError as e:
            logger.error("Schedule parse error: %s", e)
            return
        
        # Convert to ChargingPeriod objects
        periods: List[ChargingPeriod] = []
        
        for p in charge_periods[:3]:  # Max 3 charge slots
            periods.append(ChargingPeriod(
                charge_type=BatteryChargeType.CHARGE,
                start_time=p['start'],
                duration_minutes=p['duration'],
                power_w=p['power'],
            ))
        
        for p in discharge_periods[:6]:  # Max 6 discharge slots
            periods.append(ChargingPeriod(
                charge_type=BatteryChargeType.DISCHARGE,
                start_time=p['start'],
                duration_minutes=p['duration'],
                power_w=p['power'],
            ))
        
        if not periods:
            logger.info("No schedule periods defined - clearing schedule")
            # Build summary for active_schedule sensor
            self.status['active_schedule'] = "none"
        else:
            logger.info("Applying schedule with %d periods:", len(periods))
            for p in periods:
                logger.info("  %s: %s for %d min at %dW", 
                           p.charge_type.value, p.start_time, p.duration_minutes, p.power_w)
            
            # Build summary for active_schedule sensor
            summary = {
                'charge': [{'start': p.start_time, 'power': p.power_w, 'duration': p.duration_minutes} 
                          for p in periods if p.charge_type == BatteryChargeType.CHARGE],
                'discharge': [{'start': p.start_time, 'power': p.power_w, 'duration': p.duration_minutes} 
                             for p in periods if p.charge_type == BatteryChargeType.DISCHARGE],
            }
            self.status['active_schedule'] = json.dumps(summary, separators=(',', ':'))
        
        # Apply to inverter
        if self.simulation_mode:
            logger.info("SIMULATION: Schedule would be applied")
            self.status['last_applied'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.status['api_status'] = 'Simulation Mode'
        else:
            try:
                success = self.saj_client.save_schedule(periods)
                if success:
                    self.status['last_applied'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.status['api_status'] = 'Connected'
                    logger.info("Schedule applied successfully")
                else:
                    self.status['api_status'] = 'Apply Failed'
                    logger.error("Failed to apply schedule")
            except Exception as e:
                self.status['api_status'] = f'Error: {e}'
                logger.error("Schedule application error: %s", e)
        
        # Update sensors
        self.update_entities()
    
    def poll_status(self):
        """Poll SAJ API for current battery status."""
        if self.simulation_mode:
            # Simulated status
            self.status['battery_soc'] = 75
            self.status['battery_mode'] = 'TimeOfUse'
            logger.debug("SIMULATION: Status poll (SOC=75%%, mode=TimeOfUse)")
            return
        
        try:
            # Get user mode
            mode_result = self.saj_client.get_user_mode()
            if mode_result:
                self.status['battery_mode'] = mode_result
                self.status['api_status'] = 'Connected'
            
            # TODO: Add SOC polling when we decode that API endpoint
            
        except Exception as e:
            logger.error("Status poll failed: %s", e)
            self.status['api_status'] = f'Poll Error: {e}'
    
    def update_entities(self):
        """Publish updated status to MQTT entities."""
        if not self.mqtt:
            return
        
        # Update status sensors
        soc = self.status.get('battery_soc')
        self.mqtt.update_state("sensor", "battery_soc", 
                               str(soc) if soc is not None else "unknown")
        
        mode = self.status.get('battery_mode')
        self.mqtt.update_state("sensor", "battery_mode", mode or "unknown")
        
        active = self.status.get('active_schedule')
        self.mqtt.update_state("sensor", "active_schedule", active or "none")
        
        api_status = self.status.get('api_status')
        self.mqtt.update_state("sensor", "api_status", api_status or "unknown")
        
        last_applied = self.status.get('last_applied')
        self.mqtt.update_state("sensor", "last_applied", last_applied or "never")
    
    def run(self):
        """Main run loop."""
        poll_interval = self.config['poll_interval_seconds']
        run_once = get_run_once_mode()
        
        logger.info("Starting main loop (poll every %ds)", poll_interval)
        
        first_run = True
        while not self.shutdown_event.is_set():
            try:
                # Poll status
                self.poll_status()
                
                # Update entities
                self.update_entities()
                
                if first_run:
                    logger.info("Initial status: SOC=%s, mode=%s, api=%s",
                               self.status.get('battery_soc'),
                               self.status.get('battery_mode'),
                               self.status.get('api_status'))
                    first_run = False
                
            except Exception as e:
                logger.error("Error in main loop: %s", e)
            
            if run_once:
                logger.info("RUN_ONCE mode: exiting after first iteration")
                break
            
            # Sleep until next poll (checking for shutdown)
            if not sleep_with_shutdown_check(self.shutdown_event, poll_interval, logger):
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
    logger.info("=" * 60)
    logger.info("Battery API Add-on Starting")
    logger.info("=" * 60)
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = setup_signal_handlers(logger)
    
    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)
    
    # Create and run add-on
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
