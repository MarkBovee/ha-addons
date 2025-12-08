"""Water Heater Scheduler add-on main entry point.

Schedules domestic hot water heating based on electricity prices.
Logic ported directly from NetDaemon WaterHeater.cs for reliability.
"""

import logging
from datetime import datetime, timedelta

from .models import ScheduleConfig, HeaterState, ProgramType
from .water_heater_controller import WaterHeaterController, EntityStateReader
from .price_analyzer import PriceAnalyzer
from .scheduler import Scheduler
from .status_manager import get_status_visual, update_status_entity, update_legionella_entity

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
    price_analyzer = PriceAnalyzer()
    
    # Load persistent state
    state = HeaterState.load()
    
    # Initialize scheduler with state
    scheduler = Scheduler(config, price_analyzer, state)
    
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
                if not price_analyzer.update_prices(price_state):
                    logger.warning("Failed to update price data from sensor %s", config.price_sensor_entity_id)
                elif not price_analyzer.has_prices:
                    logger.warning("No price data available after parsing price_curve")
                else:
                    # Determine current context
                    current_price = price_analyzer.current_price or float(price_state.get("state", 0))
                    away_mode_on = entity_reader.is_entity_on(config.away_mode_entity_id)
                    bath_mode_on = entity_reader.is_entity_on(config.bath_mode_entity_id)
                    heater_controller.get_state()
                    current_water_temp = heater_controller.current_temperature

                    decision = scheduler.select_program(
                        away_mode_on=away_mode_on,
                        bath_mode_on=bath_mode_on,
                        current_water_temp=current_water_temp,
                    )

                    window = scheduler.get_program_window(decision.program)
                    now = datetime.now(price_analyzer.timezone)
                    if window is not None:
                        start_raw, end_raw = window
                        start = start_raw if start_raw.tzinfo else start_raw.replace(tzinfo=price_analyzer.timezone)
                        end = end_raw if end_raw.tzinfo else end_raw.replace(tzinfo=price_analyzer.timezone)
                        in_window = start <= now <= end
                    else:
                        in_window = False
                    can_start = scheduler.can_start_program(now)

                    apply_now = (
                        decision.program in (ProgramType.NEGATIVE_PRICE, ProgramType.BATH)
                        or (in_window and can_start)
                    )

                    if apply_now:
                        heater_controller.apply_program(decision.target_temp)
                        state.current_program = decision.program.value
                        state.target_temperature = decision.target_temp
                        state.heater_on = True
                        state.save()
                    else:
                        state.heater_on = False
                        state.save()

                    status_msg = scheduler.build_status_message(decision, window, now=now)
                    status_icon, status_color = get_status_visual(decision.program, now)
                    update_status_entity(
                        ha_api,
                        status_msg,
                        decision.program,
                        decision.target_temp,
                        status_icon,
                        status_color,
                    )
                    update_legionella_entity(ha_api, state.get_last_legionella_protection())
            
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
