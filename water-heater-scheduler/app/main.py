"""Water Heater Scheduler add-on main entry point.

Schedules domestic hot water heating based on electricity prices.
Logic ported directly from NetDaemon WaterHeater.cs for reliability.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from .models import ScheduleConfig, HeaterState, ProgramType
from .water_heater_controller import WaterHeaterController, EntityStateReader

# Import shared modules
from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.ha_api import HomeAssistantApi, get_ha_api_config
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
}

WH_REQUIRED_FIELDS = ['water_heater_entity_id']

# Status entity to update (compatible with NetDaemon WaterHeater app)
STATUS_TEXT_ENTITY = 'input_text.heating_schedule_status'

# Day of week mapping (matches C# DayOfWeek enum)
DAYS_OF_WEEK = {
    "Sunday": 6,
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
}

WINTER_MONTHS = {10, 11, 12, 1, 2, 3}


def get_status_visual(program: ProgramType, current_time: datetime) -> Tuple[str, Optional[str]]:
    """Return icon + color to match the current program and season."""
    is_winter = current_time.month in WINTER_MONTHS
    light_blue = "#ADD8E6"
    
    if program in (ProgramType.DAY, ProgramType.NIGHT):
        icon = "mdi:snowflake-thermometer" if is_winter else "mdi:water-thermometer"
        color = light_blue
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
        color = "#b0bec5"
    return icon, color


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


def parse_price_curve(sensor_state: Dict[str, Any]) -> Dict[datetime, float]:
    """Parse price_curve from sensor attributes into datetime->price dict.
    
    Mirrors PriceHelper.PricesToday in NetDaemon.
    """
    prices = {}
    attributes = sensor_state.get("attributes", {})
    price_curve = attributes.get("price_curve", [])
    
    for entry in price_curve:
        if not isinstance(entry, dict):
            continue
        start_str = entry.get("start") or entry.get("time")
        price = entry.get("price")
        if start_str is None or price is None:
            continue
        try:
            dt = datetime.fromisoformat(str(start_str))
            # Convert to local time for comparison (strip timezone for simple comparisons)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            prices[dt] = float(price)
        except (ValueError, TypeError):
            continue
    
    return prices


def get_lowest_price_in_range(prices: Dict[datetime, float], start_hour: int, end_hour: int, 
                               target_date: datetime) -> Tuple[datetime, float]:
    """Get the lowest price in a time range.
    
    Mirrors PriceHelper.GetLowestNightPrice / GetLowestDayPrice.
    """
    target_day = target_date.date()
    filtered = {}
    
    for dt, price in prices.items():
        if dt.date() != target_day:
            continue
        hour = dt.hour
        if start_hour <= end_hour:
            # Normal range (e.g., 6-23)
            if start_hour <= hour < end_hour:
                filtered[dt] = price
        else:
            # Overnight range (e.g., 0-6)
            if hour >= start_hour or hour < end_hour:
                filtered[dt] = price
    
    if not filtered:
        # Return a default if no prices found
        default_time = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        return (default_time, 0.5)
    
    lowest_dt = min(filtered, key=filtered.get)
    return (lowest_dt, filtered[lowest_dt])


def get_lowest_night_price(prices: Dict[datetime, float], target_date: datetime) -> Tuple[datetime, float]:
    """Get lowest price during night hours (0:00 - 6:00)."""
    return get_lowest_price_in_range(prices, 0, 6, target_date)


def get_lowest_day_price(prices: Dict[datetime, float], target_date: datetime) -> Tuple[datetime, float]:
    """Get lowest price during day hours (6:00 - 24:00)."""
    return get_lowest_price_in_range(prices, 6, 24, target_date)


def get_next_night_price(prices_tomorrow: Dict[datetime, float], tomorrow: datetime) -> Tuple[datetime, float]:
    """Get lowest night price for tomorrow."""
    return get_lowest_night_price(prices_tomorrow, tomorrow)


def get_price_level(current_price: float, prices: Dict[datetime, float]) -> str:
    """Determine price level (None/Low/Medium/High) based on fixed price thresholds.
    
    Matches NetDaemon PriceHelper.GetEnergyPriceLevel() exactly:
    - None: price < 0 (actual negative/free energy)
    - Low: price < 0.10 EUR/kWh
    - Medium: price < 0.35 EUR/kWh (and below threshold)
    - High: price < 0.45 EUR/kWh or above threshold
    - Maximum: price >= 0.45 EUR/kWh
    """
    if not prices:
        return "Medium"
    
    # Calculate price threshold (average of today's prices, min 0.28)
    avg_price = sum(prices.values()) / len(prices) if prices else 0.28
    price_threshold = max(avg_price, 0.28)
    
    # Fixed thresholds matching NetDaemon PriceHelper.cs GetEnergyPriceLevel()
    if current_price < 0:
        return "None"  # Actual negative price - free energy
    elif current_price < 0.10:
        return "Low"   # Very cheap (< 10 cents/kWh)
    elif current_price < 0.35:
        # Medium if below threshold, High if above
        return "Medium" if current_price < price_threshold else "High"
    elif current_price < 0.45:
        return "High"
    else:
        return "Maximum"


def update_status_entity(ha_api: HomeAssistantApi, status_msg: str, 
                         program: ProgramType, target_temp: int,
                         status_icon: str, status_color: Optional[str]):
    """Update the status input_text entity."""
    attributes = {
        "friendly_name": "Heating Schedule Status",
        "icon": status_icon,
        "program": program.value,
        "target_temp": target_temp,
    }
    if status_color:
        attributes["icon_color"] = status_color
    
    ha_api.create_or_update_entity(
        entity_id=STATUS_TEXT_ENTITY,
        state=status_msg,
        attributes=attributes,
        log_success=False
    )


def set_water_temperature(
    config: ScheduleConfig,
    ha_api: HomeAssistantApi,
    state: HeaterState,
    heater_controller: WaterHeaterController,
    entity_reader: EntityStateReader,
    prices_today: Dict[datetime, float],
    prices_tomorrow: Dict[datetime, float],
    current_price: float,
) -> None:
    """Set the water temperature for the heat pump.
    
    This is a direct port of WaterHeater.cs SetWaterTemperature() method.
    """
    now = datetime.now()
    preset = config.get_preset()
    
    # Get current water heater state
    heater_state = heater_controller.get_state()
    if not heater_state:
        logger.warning("Water heater unavailable")
        return
    
    current_temp = heater_controller.current_temperature or 35
    current_target_temp = heater_controller.target_temperature or 35
    
    # Check away mode
    away_mode = entity_reader.is_entity_on(config.away_mode_entity_id)
    
    # Determine program type based on time (matching WaterHeater.cs logic exactly)
    night_end_hour = config.get_night_window_end().hour
    use_night_program = now.hour < night_end_hour
    
    # Check legionella day (Saturday by default)
    legionella_weekday = DAYS_OF_WEEK.get(config.legionella_day, 5)
    use_legionella_protection = not use_night_program and now.weekday() == legionella_weekday
    
    # Determine program type string
    if away_mode:
        program_type = "Away"
        program = ProgramType.AWAY
    elif use_night_program:
        program_type = "Night"
        program = ProgramType.NIGHT
    elif use_legionella_protection:
        program_type = "Legionella Protection"
        program = ProgramType.LEGIONELLA
    else:
        program_type = "Day"
        program = ProgramType.DAY
    
    # Check bath mode and auto-disable if water temp > 50
    bath_mode = entity_reader.is_entity_on(config.bath_mode_entity_id)
    if bath_mode and current_temp > config.bath_auto_off_temp:
        entity_reader.turn_off_entity(config.bath_mode_entity_id)
        bath_mode = False
        logger.info("Bath mode auto-disabled at %.1f°C", current_temp)
    
    if bath_mode:
        program_type = "Bath"
        program = ProgramType.BATH
    
    # Get price slots
    lowest_night_price = get_lowest_night_price(prices_today, now)
    lowest_day_price = get_lowest_day_price(prices_today, now)
    tomorrow = now + timedelta(days=1)
    next_night_price = get_next_night_price(prices_tomorrow, tomorrow) if prices_tomorrow else (tomorrow, 999.0)
    
    logger.debug("Schedule: program=%s, night=%s@%.4f, day=%s@%.4f",
                program_type,
                lowest_night_price[0].strftime("%H:%M"), lowest_night_price[1],
                lowest_day_price[0].strftime("%H:%M"), lowest_day_price[1])
    
    # Determine start time
    start_time = lowest_night_price[0] if use_night_program else lowest_day_price[0]
    
    # Legionella optimization: check if 15 min before is cheaper than 15 min after
    if use_legionella_protection and 0 < start_time.hour < 23:
        prev_time = start_time - timedelta(minutes=15)
        next_time = start_time + timedelta(minutes=15)
        
        prev_price = prices_today.get(prev_time)
        next_price = prices_today.get(next_time)
        
        if prev_price is not None and next_price is not None and prev_price < next_price:
            start_time = prev_time
            logger.info("Legionella: Adjusted start to %s (prev=%.4f < next=%.4f)",
                       start_time.strftime("%H:%M"), prev_price, next_price)
    
    # Set end time: 3 hours for legionella, 1 hour for normal
    duration_hours = config.legionella_duration_hours if use_legionella_protection else config.heating_duration_hours
    end_time = start_time + timedelta(hours=duration_hours)
    
    # Get energy price level for temperature decisions
    energy_price_level = get_price_level(current_price, prices_today)
    
    logger.debug("Price analysis: current=%.4f EUR/kWh, level=%s", current_price, energy_price_level)
    
    # === Temperature Selection Logic (from WaterHeater.cs) ===
    idle_temperature = preset.idle  # 35
    heating_temperature = idle_temperature
    program_temperature = idle_temperature
    
    # Build next heating info for idle messages
    if start_time > now:
        next_heating_info = f"Next: {program_type} heating at {start_time.strftime('%H:%M')}"
    else:
        # Check if tomorrow's prices are available for next window prediction
        if prices_tomorrow:
            next_heating_info = "Next: Tomorrow's schedule ready"
        else:
            next_heating_info = "Waiting for tomorrow's prices"
    
    # Build idle text based on mode
    if away_mode:
        idle_text = f"🏖️ Away mode | {next_heating_info}"
    elif bath_mode:
        idle_text = f"🛁 Bath mode ready"
    else:
        idle_text = f"💤 Idle | {next_heating_info}"
    
    if away_mode:
        # Away mode: only heat for legionella on Saturday
        if use_legionella_protection and not use_night_program:
            program_temperature = 66 if current_price < 0.2 else 60
        else:
            program_temperature = preset.away  # 35
    elif bath_mode:
        program_temperature = preset.bath  # 58
        heating_temperature = preset.bath
    else:
        # Normal operation - set heating temp based on price level
        if energy_price_level == "None":
            heating_temperature = 70  # Free energy
        elif energy_price_level == "Low":
            heating_temperature = 50
        else:
            heating_temperature = 35
        
        # Set program temperature based on program type
        if use_night_program:
            # Night: higher temp if night is cheaper than day
            night_cheaper = lowest_night_price[1] < lowest_day_price[1]
            program_temperature = preset.night_preheat if night_cheaper else preset.night_minimal
        elif use_legionella_protection:
            program_temperature = 70 if energy_price_level == "None" else preset.legionella
        else:
            # Day program
            if energy_price_level == "None":
                program_temperature = 70
            else:
                program_temperature = preset.day_preheat  # 58
                
                # If tomorrow night is cheaper, skip heating now
                if next_night_price[1] > 0 and next_night_price[1] < current_price:
                    if energy_price_level in ("Medium", "High"):
                        program_temperature = heating_temperature
                        logger.debug("Tomorrow cheaper - using heating temp instead")
    
    # === Apply Temperature (matching WaterHeater.cs logic) ===
    try:
        in_window = start_time <= now <= end_time
        
        logger.debug("Window check: now=%s, start=%s, end=%s, in_window=%s",
                    now.strftime("%H:%M"), start_time.strftime("%H:%M"), 
                    end_time.strftime("%H:%M"), in_window)
        
        if in_window:
            # Inside heating window
            if program_temperature <= state.target_temperature and state.heater_on:
                # Already heating at same or higher temp
                return
            
            state.target_temperature = program_temperature
            state.heater_on = True
            state.current_program = program.value
            state.save()
            
            heater_controller.set_operation_mode("Manual")
            heater_controller.set_temperature(program_temperature)
            
            if current_temp < program_temperature:
                # Active heating - show what and until when
                if away_mode:
                    status_msg = f"🏖️ Away mode | Legionella cycle ({program_temperature}°C) until {end_time.strftime('%H:%M')}"
                elif bath_mode:
                    status_msg = f"🛁 Bath mode | Heating to {program_temperature}°C"
                elif energy_price_level == "None":
                    status_msg = f"⚡ Free energy! Heating to {program_temperature}°C"
                elif use_legionella_protection:
                    status_msg = f"🦠 Legionella protection ({program_temperature}°C) until {end_time.strftime('%H:%M')}"
                else:
                    status_msg = f"🔥 {program_type} heating ({program_temperature}°C) until {end_time.strftime('%H:%M')}"
            else:
                # Reached target temp during window
                status_msg = f"✅ {program_type} heating complete | {next_heating_info}"
            
            logger.info("Started %s: %d°C (window %s-%s)", 
                       program_type, program_temperature,
                       start_time.strftime("%H:%M"), end_time.strftime("%H:%M"))
        else:
            # Outside heating window - use wait cycles logic
            if state.target_temperature > idle_temperature and state.wait_cycles > 0:
                state.wait_cycles -= 1
                state.save()
                
                if current_temp < state.target_temperature:
                    # Still finishing a heat cycle after window ended
                    status_msg = f"⏳ Finishing heat cycle ({state.target_temperature}°C)"
                else:
                    # Heat cycle complete, show next
                    status_msg = f"✅ Heat cycle complete | {next_heating_info}"
            else:
                # Reset to heating temperature
                state.target_temperature = heating_temperature
                state.wait_cycles = 10
                state.heater_on = False
                state.save()
                
                if current_target_temp != heating_temperature:
                    heater_controller.set_operation_mode("Manual")
                    heater_controller.set_temperature(heating_temperature)
                
                if heating_temperature > idle_temperature:
                    if current_temp < heating_temperature:
                        # Opportunistic heating due to low prices
                        if energy_price_level == "None":
                            status_msg = f"⚡ Free energy! Heating to {heating_temperature}°C"
                        elif energy_price_level == "Low":
                            status_msg = f"💰 Low price heating ({heating_temperature}°C)"
                        else:
                            status_msg = f"🔥 Heating ({heating_temperature}°C) | {next_heating_info}"
                    else:
                        status_msg = idle_text
                else:
                    status_msg = idle_text
        
        # Update status entity
        status_icon, status_color = get_status_visual(program, now)
        update_status_entity(ha_api, status_msg, program, state.target_temperature, status_icon, status_color)
        
    except Exception as e:
        logger.error("Failed to set temperature: %s", e, exc_info=True)
        state.target_temperature = 0
        state.wait_cycles = 0
        state.heater_on = False
        state.save()


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
