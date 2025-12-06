"""Core scheduling logic for Water Heater Scheduler.

Contains the main temperature decision and heating window logic.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict

from shared.ha_api import HomeAssistantApi
from .models import ScheduleConfig, HeaterState, ProgramType
from .water_heater_controller import WaterHeaterController, EntityStateReader
from .constants import DAYS_OF_WEEK, LEGIONELLA_TEMP_THRESHOLD, LEGIONELLA_INTERVAL_DAYS
from .price_analyzer import (
    get_lowest_night_price,
    get_lowest_day_price,
    get_next_night_price,
    get_price_level,
)
from .status_manager import get_status_visual, update_status_entity, update_legionella_entity

logger = logging.getLogger(__name__)


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
    # Only trigger if: it's the right day AND we need protection (>= 7 days since last)
    legionella_weekday = DAYS_OF_WEEK.get(config.legionella_day, 5)
    is_legionella_day = not use_night_program and now.weekday() == legionella_weekday
    needs_legionella = state.needs_legionella_protection(LEGIONELLA_INTERVAL_DAYS)
    use_legionella_protection = is_legionella_day and needs_legionella
    
    # Check if current temp is already above legionella threshold (counts as protection)
    if current_temp >= LEGIONELLA_TEMP_THRESHOLD:
        last_protection = state.get_last_legionella_protection()
        # Only update if it's been a while or never set
        if last_protection is None or (now - last_protection).total_seconds() > 3600:
            logger.info("Water at %.1f°C >= %d°C threshold, recording legionella protection",
                       current_temp, LEGIONELLA_TEMP_THRESHOLD)
            state.set_last_legionella_protection(now)
            state.save()
    
    # Log legionella decision
    if is_legionella_day and not needs_legionella:
        last_protection = state.get_last_legionella_protection()
        days_since = (now - last_protection).days if last_protection else 0
        logger.info("Legionella day but protection not needed (last: %d days ago, threshold: %d days)",
                   days_since, LEGIONELLA_INTERVAL_DAYS)
    
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
            # Only log if the adjusted time is in the future (actionable info)
            if start_time > now:
                logger.info("Legionella: Optimized start to %s (€%.4f vs €%.4f after)",
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
    
    # Track decision reasoning for logging
    decision_reason = None
    
    if away_mode:
        # Away mode: only heat for legionella on Saturday
        if use_legionella_protection and not use_night_program:
            program_temperature = 66 if current_price < 0.2 else 60
            decision_reason = f"Away + Legionella day: {program_temperature}°C"
        else:
            program_temperature = preset.away  # 35
            decision_reason = "Away mode: minimal heating"
    elif bath_mode:
        program_temperature = preset.bath  # 58
        heating_temperature = preset.bath
        decision_reason = f"Bath mode: {program_temperature}°C"
    else:
        # Normal operation - set heating temp based on price level
        if energy_price_level == "None":
            heating_temperature = 70  # Free energy
            decision_reason = "Free energy: max heating"
        elif energy_price_level == "Low":
            heating_temperature = 50
            decision_reason = f"Low price (€{current_price:.3f}): opportunistic 50°C"
        else:
            heating_temperature = 35
        
        # Set program temperature based on program type
        if use_night_program:
            # Night: higher temp if night is cheaper than day
            night_cheaper = lowest_night_price[1] < lowest_day_price[1]
            program_temperature = preset.night_preheat if night_cheaper else preset.night_minimal
            if night_cheaper:
                decision_reason = f"Night cheaper (€{lowest_night_price[1]:.3f}) than day (€{lowest_day_price[1]:.3f}): preheat {program_temperature}°C"
            else:
                decision_reason = f"Day cheaper: minimal night heating {program_temperature}°C"
        elif use_legionella_protection:
            program_temperature = 70 if energy_price_level == "None" else preset.legionella
            decision_reason = f"Legionella protection: {program_temperature}°C"
        else:
            # Day program
            if energy_price_level == "None":
                program_temperature = 70
                decision_reason = "Free energy: max heating 70°C"
            else:
                program_temperature = preset.day_preheat  # 58
                decision_reason = f"Day program: {program_temperature}°C"
                
                # If tomorrow night is cheaper, skip heating now
                if next_night_price[1] > 0 and next_night_price[1] < current_price:
                    if energy_price_level in ("Medium", "High"):
                        program_temperature = heating_temperature
                        decision_reason = f"Tomorrow night cheaper (€{next_night_price[1]:.3f} vs €{current_price:.3f}): skip day heating"
    
    # === Apply Temperature (matching WaterHeater.cs logic) ===
    try:
        in_window = start_time <= now <= end_time
        
        # Determine action for logging
        if in_window:
            if current_temp < program_temperature:
                action = f"Heating to {program_temperature}°C"
            else:
                action = f"Target reached ({current_temp:.1f}°C)"
        elif heating_temperature > idle_temperature and current_temp < heating_temperature:
            action = f"Opportunistic {heating_temperature}°C"
        else:
            action = "Idle"
        
        # Log evaluation summary (always at INFO level for visibility)
        window_info = f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"
        logger.info("[%s] %s | €%.3f (%s) | Window: %s | %s",
                   program_type, action, current_price, energy_price_level, window_info,
                   decision_reason or "Standard operation")
        
        if in_window:
            # Inside heating window
            if program_temperature <= state.target_temperature and state.heater_on:
                # Already heating at same or higher temp
                return
            
            # Log state change
            old_temp = state.target_temperature
            old_heater = state.heater_on
            
            state.target_temperature = program_temperature
            state.heater_on = True
            state.current_program = program.value
            state.save()
            
            heater_controller.set_operation_mode("Manual")
            heater_controller.set_temperature(program_temperature)
            
            # Log significant state changes
            if old_temp != program_temperature or not old_heater:
                logger.info("State change: %d°C → %d°C, heater %s → ON",
                           old_temp, program_temperature, "ON" if old_heater else "OFF")
            
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
                
                # Record legionella protection completion when target reached during legionella cycle
                if use_legionella_protection and current_temp >= LEGIONELLA_TEMP_THRESHOLD:
                    state.set_last_legionella_protection(now)
                    state.save()
                    logger.info("Legionella protection complete at %.1f°C, recorded timestamp", current_temp)
        else:
            # Outside heating window - use wait cycles logic
            if state.target_temperature > idle_temperature and state.wait_cycles > 0:
                state.wait_cycles -= 1
                state.save()
                
                if current_temp < state.target_temperature:
                    # Still finishing a heat cycle after window ended
                    status_msg = f"⏳ Finishing heat cycle ({state.target_temperature}°C)"
                    logger.debug("Finishing cycle: %d°C, %d cycles remaining", 
                                state.target_temperature, state.wait_cycles)
                else:
                    # Heat cycle complete, show next
                    status_msg = f"✅ Heat cycle complete | {next_heating_info}"
                    logger.info("Heat cycle complete at %.1f°C", current_temp)
            else:
                # Reset to heating temperature
                old_temp = state.target_temperature
                old_heater = state.heater_on
                
                state.target_temperature = heating_temperature
                state.wait_cycles = 10
                state.heater_on = False
                state.save()
                
                if current_target_temp != heating_temperature:
                    heater_controller.set_operation_mode("Manual")
                    heater_controller.set_temperature(heating_temperature)
                    logger.info("Set heater target: %d°C (opportunistic)", heating_temperature)
                
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
        
        # Update legionella tracking entity
        update_legionella_entity(ha_api, state.get_last_legionella_protection())
        
    except Exception as e:
        logger.error("Failed to set temperature: %s", e, exc_info=True)
        state.target_temperature = 0
        state.wait_cycles = 0
        state.heater_on = False
        state.save()
