"""Water Heater Scheduler add-on main entry point.

Schedules domestic hot water heating based on electricity prices.
Logic ported directly from NetDaemon WaterHeater.cs for reliability.
"""

import logging
from datetime import datetime, timedelta

from .models import ScheduleConfig, HeaterState
from .water_heater_controller import WaterHeaterController, EntityStateReader
from .price_analyzer import parse_price_curve
from .scheduler import set_water_temperature

# Import shared modules
from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.ha_api import HomeAssistantApi
from shared.config_loader import load_addon_config, get_run_once_mode

# Configure logging
logger = setup_logging(name=__name__)


# Configuration defaults
WH_CONFIG_DEFAULTS = {
    'water_heater_entity_id': '',
    'price_sensor_entity_id': 'sensor.energy_prices_price_import',
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
    'initial_legionella_date': '',
}

WH_REQUIRED_FIELDS = ['water_heater_entity_id']


def load_config() -> ScheduleConfig:
    """Load Water Heater Scheduler configuration."""
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
    logger.info("  Night window end (hour): %s", config.night_window_end)
    logger.info("  Preset: %s", config.temperature_preset)
    logger.info("  Legionella: %s, %dh duration", config.legionella_day, config.legionella_duration_hours)
    
    if config.away_mode_entity_id:
        logger.info("  Away mode entity: %s", config.away_mode_entity_id)
    if config.bath_mode_entity_id:
        logger.info("  Bath mode entity: %s", config.bath_mode_entity_id)
    
    # Validate
    warnings = config.validate()
    for warning in warnings:
        if warning.startswith("ERROR:"):
            logger.error(warning)
        else:
            logger.warning(warning)
    
    if any(w.startswith("ERROR:") for w in warnings):
        raise SystemExit(1)
    
    return config


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
    ha_api = HomeAssistantApi()
    
    # Test connection
    if not ha_api.test_connection():
        logger.error("Failed to connect to Home Assistant API")
        return
    
    # Initialize components
    heater_controller = WaterHeaterController(ha_api, config.water_heater_entity_id)
    entity_reader = EntityStateReader(ha_api)
    
    # Load persistent state
    state = HeaterState.load()
    
    # Check for initial_legionella_date config (bootstrap setting)
    raw_config = load_addon_config(defaults=WH_CONFIG_DEFAULTS, required_fields=[])
    initial_date = raw_config.get('initial_legionella_date', '')
    if initial_date and state.last_legionella_protection is None:
        try:
            # Parse date like "2025-12-06" or "2025-12-06 05:00" or "2025-12-06T05:00:00"
            from datetime import datetime as dt
            if 'T' in initial_date:
                parsed = dt.fromisoformat(initial_date)
            elif ' ' in initial_date:
                parsed = dt.strptime(initial_date, '%Y-%m-%d %H:%M')
            else:
                parsed = dt.strptime(initial_date + ' 05:00', '%Y-%m-%d %H:%M')
            state.set_last_legionella_protection(parsed)
            state.save()
            logger.info("Initialized last_legionella_protection from config: %s", parsed.isoformat())
            logger.info("You can now clear 'initial_legionella_date' from the add-on config.")
        except ValueError as e:
            logger.warning("Invalid initial_legionella_date format '%s': %s", initial_date, e)
    
    # Get run-once mode
    run_once = get_run_once_mode()
    
    if run_once:
        logger.info("Running single evaluation (RUN_ONCE mode)")
    
    # Main loop (runs every 5 minutes like NetDaemon)
    interval_seconds = config.evaluation_interval_minutes * 60
    
    while not shutdown_event.is_set():
        try:
            # Get price data from sensor
            price_state = entity_reader.get_sensor_state(config.price_sensor_entity_id)
            
            if not price_state:
                logger.warning("Price sensor %s unavailable", config.price_sensor_entity_id)
            else:
                # Parse prices
                prices_today = parse_price_curve(price_state)
                
                # Get tomorrow's prices (if available)
                # They're in the same price_curve, just filter by date
                tomorrow = datetime.now() + timedelta(days=1)
                prices_tomorrow = {dt: p for dt, p in prices_today.items() 
                                   if dt.date() == tomorrow.date()}
                prices_today = {dt: p for dt, p in prices_today.items() 
                               if dt.date() == datetime.now().date()}
                
                current_price = float(price_state.get("state", 0))
                
                if not prices_today:
                    logger.warning("No price data for today")
                else:
                    # Run the main logic
                    set_water_temperature(
                        config=config,
                        ha_api=ha_api,
                        state=state,
                        heater_controller=heater_controller,
                        entity_reader=entity_reader,
                        prices_today=prices_today,
                        prices_tomorrow=prices_tomorrow,
                        current_price=current_price,
                    )
            
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
