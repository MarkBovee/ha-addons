"""Water Heater Scheduler add-on main entry point.

Schedules domestic hot water heating based on electricity prices,
optimizing for cost while maintaining comfort and legionella protection.
"""

import logging
import os
from datetime import datetime
from typing import Optional, Tuple

from .models import ScheduleConfig, HeaterState, ProgramType
from .price_analyzer import PriceAnalyzer
from .scheduler import Scheduler
from .water_heater_controller import WaterHeaterController, EntityStateReader

# Import shared modules
from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.ha_api import HomeAssistantApi, get_ha_api_config
from shared.config_loader import load_addon_config, get_run_once_mode
from shared.mqtt_setup import setup_mqtt_client, is_mqtt_available

# Configure logging
logger = setup_logging(name=__name__)


# Configuration defaults
WH_CONFIG_DEFAULTS = {
    'water_heater_entity_id': '',
    'price_sensor_entity_id': 'sensor.ep_price_import',
    'away_mode_entity_id': '',
    'bath_mode_entity_id': '',
    'evaluation_interval_minutes': 5,
    'night_window_start': '00:00',
    'night_window_end': '06:00',
    'heating_duration_hours': 1,
    'legionella_day': 'Saturday',
    'legionella_duration_hours': 3,
    'bath_auto_off_temp': 50,
    'temperature_preset': 'comfort',
    'min_cycle_gap_minutes': 50,
    'log_level': 'info',
    'dynamic_window_mode': False,
}

WH_REQUIRED_FIELDS = ['water_heater_entity_id']

# Old entities to clean up on startup (from previous versions)
OLD_ENTITIES = [
    # None currently - sensors are managed by this add-on
]

# Status entity to update (compatible with NetDaemon WaterHeater app)
STATUS_TEXT_ENTITY = 'input_text.heating_schedule_status'


WINTER_MONTHS = {10, 11, 12, 1, 2, 3}


def get_status_visual(program: ProgramType, current_time: datetime) -> Tuple[str, Optional[str]]:
    """Return icon + color to match the current program and season."""
    is_winter = current_time.month in WINTER_MONTHS
    if program == ProgramType.DAY:
        icon = "mdi:weather-snowy-sunny" if is_winter else "mdi:weather-sunny"
        color = "#8ec5ff" if is_winter else "#fbc02d"
    elif program == ProgramType.NIGHT:
        icon = "mdi:snowflake"
        color = "#9bc8ff" if is_winter else "#bbdefb"
    elif program == ProgramType.NEGATIVE_PRICE:
        icon = "mdi:lightning-bolt-circle"
        color = "#ffb300"
    elif program == ProgramType.LEGIONELLA:
        icon = "mdi:shield-heat"
        color = "#ff7043"
    elif program == ProgramType.BATH:
        icon = "mdi:bathtub"
        color = "#4dd0e1"
    elif program == ProgramType.AWAY:
        icon = "mdi:bag-suitcase"
        color = "#78909c"
    else:
        icon = "mdi:information-outline"
        color = "#b0bec5" if is_winter else "#cfd8dc"
    return icon, color


def load_config() -> ScheduleConfig:
    """Load Water Heater Scheduler configuration.
    
    Returns:
        ScheduleConfig instance
    """
    raw_config = load_addon_config(
        defaults=WH_CONFIG_DEFAULTS,
        required_fields=WH_REQUIRED_FIELDS
    )
    
    config = ScheduleConfig.from_config(raw_config)
    
    # Set log level
    log_levels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
    }
    level = log_levels.get(config.log_level.lower(), logging.INFO)
    logging.getLogger().setLevel(level)
    
    logger.info("Loaded configuration:")
    logger.info("  Water heater: %s", config.water_heater_entity_id)
    logger.info("  Price sensor: %s", config.price_sensor_entity_id)
    logger.info("  Night window: %s - %s", config.night_window_start, config.night_window_end)
    logger.info("  Preset: %s", config.temperature_preset)
    logger.info("  Legionella: %s, %dh duration", config.legionella_day, config.legionella_duration_hours)
    logger.info("  Cycle gap: %d minutes", config.min_cycle_gap_minutes)
    logger.info("  Dynamic window mode: %s", "enabled" if config.dynamic_window_mode else "disabled")
    
    if config.away_mode_entity_id:
        logger.info("  Away mode entity: %s", config.away_mode_entity_id)
    else:
        logger.info("  Away mode: disabled (no entity configured)")
    
    if config.bath_mode_entity_id:
        logger.info("  Bath mode entity: %s", config.bath_mode_entity_id)
    else:
        logger.info("  Bath mode: disabled (no entity configured)")
    
    # Validate and log warnings
    warnings = config.validate()
    for warning in warnings:
        if warning.startswith("ERROR:"):
            logger.error(warning)
        else:
            logger.warning(warning)
    
    # Exit on fatal errors
    if any(w.startswith("ERROR:") for w in warnings):
        raise SystemExit(1)
    
    return config


def create_sensors(
    ha_api: HomeAssistantApi,
    program: ProgramType,
    target_temp: int,
    status_msg: str,
    status_icon: str = "mdi:information-outline",
    status_icon_color: Optional[str] = None,
):
    """Create/update water heater status sensors.
    
    Args:
        ha_api: Home Assistant API client
        program: Current program type
        target_temp: Current target temperature
        status_msg: Human-readable status message
        status_icon: Icon for the status sensor
    """
    # Update the input_text status entity (compatible with NetDaemon)
    text_attributes = {
        "friendly_name": "Heating Schedule Status",
        "icon": status_icon,
        "program": program.value,
        "target_temp": target_temp,
    }
    if status_icon_color:
        text_attributes["icon_color"] = status_icon_color
    ha_api.create_or_update_entity(
        entity_id=STATUS_TEXT_ENTITY,
        state=status_msg,
        attributes=text_attributes,
        log_success=False
    )
    
    # Sensor: Current program
    ha_api.create_or_update_entity(
        entity_id="sensor.wh_program",
        state=program.value,
        attributes={
            "friendly_name": "Water Heater Program",
            "icon": "mdi:water-boiler",
        },
        log_success=False
    )
    
    # Sensor: Target temperature
    ha_api.create_or_update_entity(
        entity_id="sensor.wh_target_temp",
        state=str(target_temp),
        attributes={
            "friendly_name": "Water Heater Target",
            "unit_of_measurement": "°C",
            "icon": "mdi:thermometer",
            "device_class": "temperature",
        },
        log_success=False
    )
    
    # Sensor: Status message
    status_attributes = {
        "friendly_name": "Water Heater Status",
        "icon": status_icon,
    }
    if status_icon_color:
        status_attributes["icon_color"] = status_icon_color
    ha_api.create_or_update_entity(
        entity_id="sensor.wh_status",
        state=status_msg,
        attributes=status_attributes,
        log_success=False
    )


def run_evaluation_cycle(
    config: ScheduleConfig,
    ha_api: HomeAssistantApi,
    state: HeaterState,
    price_analyzer: PriceAnalyzer,
    heater_controller: WaterHeaterController,
    entity_reader: EntityStateReader,
    first_run: bool = False
) -> None:
    """Run a single evaluation cycle.
    
    Args:
        config: Schedule configuration
        ha_api: Home Assistant API client
        state: Persistent heater state
        price_analyzer: Price analyzer instance
        heater_controller: Water heater controller
        entity_reader: Entity state reader
        first_run: If True, log more details
    """
    # Align evaluation timestamp with price analyzer timezone to avoid naive vs aware comparisons
    now = datetime.now(price_analyzer.timezone)
    
    # 1. Update price data
    price_state = entity_reader.get_sensor_state(config.price_sensor_entity_id)
    if price_state:
        if not price_analyzer.update_prices(price_state):
            logger.warning("Price sensor has no valid price_curve data")
    else:
        logger.warning("Price sensor %s unavailable - skipping cycle", config.price_sensor_entity_id)
        return
    
    # 2. Get current water heater state
    heater_state = heater_controller.get_state()
    if not heater_state:
        logger.error("Water heater %s unavailable - skipping cycle", config.water_heater_entity_id)
        return
    
    current_temp = heater_controller.current_temperature
    current_target = heater_controller.target_temperature
    
    # 3. Check mode entities
    away_mode_on = entity_reader.is_entity_on(config.away_mode_entity_id)
    bath_mode_on = entity_reader.is_entity_on(config.bath_mode_entity_id)
    
    # 4. Check bath mode auto-disable
    if bath_mode_on and current_temp is not None:
        if current_temp >= config.bath_auto_off_temp:
            logger.info("Bath mode auto-disabled at %.1f°C (threshold: %d°C)",
                       current_temp, config.bath_auto_off_temp)
            entity_reader.turn_off_entity(config.bath_mode_entity_id)
            bath_mode_on = False
    
    # 5. Create scheduler and select program
    scheduler = Scheduler(config, price_analyzer, state)
    decision = scheduler.select_program(
        away_mode_on=away_mode_on,
        bath_mode_on=bath_mode_on,
        current_water_temp=current_temp,
        now=now
    )
    program = decision.program
    target_temp = decision.target_temp
    
    # 6. Get program window for scheduling
    window = scheduler.get_program_window(program, now)
    
    if window:
        start_time, end_time = window
        in_window = start_time <= now <= end_time
        
        if first_run or logger.isEnabledFor(logging.DEBUG):
            logger.debug("Program window: %s to %s (in_window=%s)",
                        start_time.strftime("%H:%M"), end_time.strftime("%H:%M"), in_window)
        
        # Only apply temperature during program window
        if in_window:
            if scheduler.can_start_program(now) or state.heater_on:
                if target_temp != current_target or not state.heater_on:
                    heater_controller.apply_program(target_temp)
                    state.heater_on = True
                    state.target_temperature = target_temp
                    state.current_program = program.value
                    state.save()
                    logger.info("Started %s program: %d°C", program.value, target_temp)
            else:
                logger.debug("Waiting for cycle gap to pass")
        else:
            # Outside window - check if program just ended
            if state.heater_on:
                scheduler.mark_cycle_complete()
                logger.info("Program %s complete", state.current_program)
                
            # Set idle temperature
            idle_temp = config.get_preset().idle
            if current_target != idle_temp:
                heater_controller.apply_program(idle_temp)
                
    else:
        # No specific window (Bath/Away/NegativePrice/Idle) - apply immediately
        if target_temp != current_target:
            heater_controller.apply_program(target_temp)
            state.target_temperature = target_temp
            state.current_program = program.value
            state.save()
            
            if program not in (ProgramType.IDLE,):
                logger.info("Applied %s: %d°C", program.value, target_temp)
    
    status_msg = scheduler.build_status_message(decision, window, now)
    status_icon, status_icon_color = get_status_visual(program, now)
    
    # 7. Update sensors
    create_sensors(
        ha_api,
        program,
        target_temp,
        status_msg,
        status_icon=status_icon,
        status_icon_color=status_icon_color,
    )
    
    # Log cycle summary
    if first_run:
        logger.info("Cycle: program=%s, target=%d°C, current=%.1f°C, price=%.4f",
                   program.value, target_temp, current_temp or 0,
                   price_analyzer.current_price or 0)


def main():
    """Main entry point for Water Heater Scheduler add-on."""
    logger.info("Starting Water Heater Scheduler add-on...")
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = setup_signal_handlers(logger)
    
    # Load configuration
    try:
        config = load_config()
    except SystemExit:
        return
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        return
    
    # Initialize Home Assistant API
    base_url, token = get_ha_api_config()
    ha_api = HomeAssistantApi(base_url, token)
    
    # Test connection
    if not ha_api.test_connection():
        logger.error("Failed to connect to Home Assistant API")
        return
    
    # Clean up old entities on startup
    ha_api.delete_entities(OLD_ENTITIES)
    
    # Initialize components
    price_analyzer = PriceAnalyzer()
    heater_controller = WaterHeaterController(ha_api, config.water_heater_entity_id)
    entity_reader = EntityStateReader(ha_api)
    
    # Load persistent state
    state = HeaterState.load()
    
    # Get run-once mode
    run_once = get_run_once_mode()
    
    if run_once:
        logger.info("Running single evaluation (RUN_ONCE mode)")
    
    # Main loop
    interval_seconds = config.evaluation_interval_minutes * 60
    first_run = True
    
    while not shutdown_event.is_set():
        try:
            run_evaluation_cycle(
                config=config,
                ha_api=ha_api,
                state=state,
                price_analyzer=price_analyzer,
                heater_controller=heater_controller,
                entity_reader=entity_reader,
                first_run=first_run
            )
            first_run = False
            
        except Exception as e:
            logger.error("Error in evaluation cycle: %s", e, exc_info=True)
        
        if run_once:
            logger.info("Single evaluation complete, exiting")
            break
        
        # Wait for next cycle
        if not sleep_with_shutdown_check(shutdown_event, interval_seconds):
            break
    
    logger.info("Water Heater Scheduler shutting down...")


if __name__ == "__main__":
    main()
