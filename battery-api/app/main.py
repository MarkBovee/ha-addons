"""Battery API add-on main entry point.

Controls SAJ Electric battery inverters via Home Assistant entities.
Provides charge/discharge scheduling through MQTT-based number, select, and button entities.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

# Add parent directory to path for shared module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import shared modules
from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.config_loader import load_addon_config, get_run_once_mode
from shared.ha_mqtt_discovery import (
    MqttDiscovery,
    EntityConfig,
    NumberConfig,
    SelectConfig,
    ButtonConfig,
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


def load_config() -> dict:
    """Load Battery API configuration.
    
    Returns:
        Configuration dictionary
    """
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


class BatteryApiAddon:
    """Main add-on class for Battery API.
    
    Manages the lifecycle of the add-on:
    - SAJ API client for inverter communication
    - MQTT entities for control and status
    - Main polling loop
    """
    
    def __init__(self, config: dict, shutdown_event):
        """Initialize the add-on.
        
        Args:
            config: Configuration dictionary
            shutdown_event: Threading event for graceful shutdown
        """
        self.config = config
        self.shutdown_event = shutdown_event
        self.simulation_mode = config.get('simulation_mode', False)
        
        # Control entity states (updated from MQTT commands)
        self.control_state = {
            'charge_power_w': 6000,
            'charge_duration_min': 60,
            'charge_start_time': '00:00',
            'discharge_power_w': 6000,
            'discharge_duration_min': 60,
            'discharge_start_time': '00:00',
            'schedule_type': 'Both',  # Charge Only, Discharge Only, Both, Clear
        }
        
        # Status (updated from SAJ API)
        self.status = {
            'battery_soc': None,
            'battery_mode': None,
            'charge_direction': None,
            'current_schedule': None,
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
        """Set up the add-on (MQTT, entities, etc.).
        
        Returns:
            True if setup successful, False otherwise
        """
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
        """Publish MQTT Discovery configs for all control and status entities."""
        if not self.mqtt:
            return
        
        logger.info("Publishing MQTT Discovery configs...")
        
        # ===== Control Entities (inputs) =====
        
        # Charge Power (number input)
        self.mqtt.publish_number(
            NumberConfig(
                object_id="charge_power",
                name="Charge Power",
                min_value=0,
                max_value=10000,
                step=100,
                state=str(self.control_state['charge_power_w']),
                unit_of_measurement="W",
                device_class="power",
                icon="mdi:lightning-bolt",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('charge_power_w', int(v)),
        )
        
        # Charge Duration (number input)
        self.mqtt.publish_number(
            NumberConfig(
                object_id="charge_duration",
                name="Charge Duration",
                min_value=0,
                max_value=1440,  # 24 hours in minutes
                step=15,
                state=str(self.control_state['charge_duration_min']),
                unit_of_measurement="min",
                icon="mdi:timer-outline",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('charge_duration_min', int(v)),
        )
        
        # Charge Start Time (text input with pattern)
        self.mqtt.publish_text(
            TextConfig(
                object_id="charge_start_time",
                name="Charge Start Time",
                state=self.control_state['charge_start_time'],
                min_length=5,
                max_length=5,
                pattern="^[0-2][0-9]:[0-5][0-9]$",
                icon="mdi:clock-start",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('charge_start_time', v),
        )
        
        # Discharge Power (number input)
        self.mqtt.publish_number(
            NumberConfig(
                object_id="discharge_power",
                name="Discharge Power",
                min_value=0,
                max_value=10000,
                step=100,
                state=str(self.control_state['discharge_power_w']),
                unit_of_measurement="W",
                device_class="power",
                icon="mdi:lightning-bolt-outline",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('discharge_power_w', int(v)),
        )
        
        # Discharge Duration (number input)
        self.mqtt.publish_number(
            NumberConfig(
                object_id="discharge_duration",
                name="Discharge Duration",
                min_value=0,
                max_value=1440,  # 24 hours in minutes
                step=15,
                state=str(self.control_state['discharge_duration_min']),
                unit_of_measurement="min",
                icon="mdi:timer-outline",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('discharge_duration_min', int(v)),
        )
        
        # Discharge Start Time (text input with pattern)
        self.mqtt.publish_text(
            TextConfig(
                object_id="discharge_start_time",
                name="Discharge Start Time",
                state=self.control_state['discharge_start_time'],
                min_length=5,
                max_length=5,
                pattern="^[0-2][0-9]:[0-5][0-9]$",
                icon="mdi:clock-start",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('discharge_start_time', v),
        )
        
        # Schedule Type (select dropdown)
        self.mqtt.publish_select(
            SelectConfig(
                object_id="schedule_type",
                name="Schedule Type",
                options=["Charge Only", "Discharge Only", "Both", "Clear"],
                state=self.control_state['schedule_type'],
                icon="mdi:battery-sync",
                entity_category="config",
            ),
            command_callback=lambda v: self._handle_command('schedule_type', v),
        )
        
        # Apply Schedule Button
        self.mqtt.publish_button(
            ButtonConfig(
                object_id="apply_schedule",
                name="Apply Schedule",
                icon="mdi:play-circle",
            ),
            press_callback=self.apply_schedule,
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
                icon="mdi:battery-charging",
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
    
    def _handle_command(self, key: str, value: Any):
        """Handle a command from an MQTT control entity.
        
        Args:
            key: Control state key to update
            value: New value
        """
        old_value = self.control_state.get(key)
        self.control_state[key] = value
        logger.info("Control %s changed: %s -> %s", key, old_value, value)
    
    def poll_status(self):
        """Poll SAJ API for current battery status."""
        if self.simulation_mode:
            # Simulated status
            self.status['battery_soc'] = 75
            self.status['battery_mode'] = 'TimeOfUse'
            self.status['charge_direction'] = 'idle'
            logger.debug("SIMULATION: Status poll (SOC=75%%, mode=TimeOfUse)")
            return
        
        try:
            # Get user mode
            mode_result = self.saj_client.get_user_mode()
            if mode_result:
                self.status['battery_mode'] = mode_result
                self.status['api_status'] = 'Connected'
            
            # TODO: Add SOC and charge direction polling in Phase 2
            
        except Exception as e:
            logger.error("Status poll failed: %s", e)
            self.status['api_status'] = f'Poll Error: {e}'
    
    def apply_schedule(self):
        """Apply the configured schedule to the inverter."""
        schedule_type = self.control_state['schedule_type']
        
        periods = []
        
        # Build charge period if requested
        if schedule_type in ('Charge Only', 'Both'):
            periods.append(ChargingPeriod(
                charge_type=BatteryChargeType.CHARGE,
                start_time=self.control_state['charge_start_time'],
                duration_minutes=self.control_state['charge_duration_min'],
                power_w=self.control_state['charge_power_w'],
            ))
        
        # Build discharge period if requested
        if schedule_type in ('Discharge Only', 'Both'):
            periods.append(ChargingPeriod(
                charge_type=BatteryChargeType.DISCHARGE,
                start_time=self.control_state['discharge_start_time'],
                duration_minutes=self.control_state['discharge_duration_min'],
                power_w=self.control_state['discharge_power_w'],
            ))
        
        if not periods:
            logger.info("Clear schedule requested")
            # TODO: Implement clear schedule in Phase 3
            return
        
        logger.info("Applying schedule with %d periods", len(periods))
        for p in periods:
            logger.info("  %s: %s for %d min at %dW", 
                       p.charge_type.value, p.start_time, p.duration_minutes, p.power_w)
        
        if self.simulation_mode:
            logger.info("SIMULATION: Schedule would be applied")
            self.status['last_applied'] = datetime.now().isoformat()
            return
        
        # Apply via SAJ API
        try:
            success = self.saj_client.save_schedule(periods)
            if success:
                self.status['last_applied'] = datetime.now().isoformat()
                logger.info("Schedule applied successfully")
            else:
                logger.error("Failed to apply schedule")
        except Exception as e:
            logger.error("Schedule application error: %s", e)
    
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
