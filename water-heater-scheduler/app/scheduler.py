"""Scheduler for Water Heater - program selection logic.

Implements the decision tree for selecting heating programs based on:
- Price conditions (negative price)
- Mode entities (away, bath)
- Time windows (night, day, legionella)
- Cycle gap protection
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Tuple

from .models import (
    ProgramType, 
    ScheduleConfig, 
    HeaterState, 
    TemperaturePreset
)
from .price_analyzer import PriceAnalyzer

logger = logging.getLogger(__name__)


class Scheduler:
    """Select and manage heating programs."""
    
    # Day of week mapping
    DAYS = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }
    
    def __init__(
        self, 
        config: ScheduleConfig, 
        price_analyzer: PriceAnalyzer,
        state: HeaterState
    ):
        """Initialize the scheduler.
        
        Args:
            config: Schedule configuration
            price_analyzer: Price analyzer instance
            state: Persistent heater state
        """
        self.config = config
        self.price_analyzer = price_analyzer
        self.state = state
        self.preset = config.get_preset()
    
    def is_in_night_window(self, now: Optional[datetime] = None) -> bool:
        """Check if current time is in night window."""
        if now is None:
            now = datetime.now()
        
        current_time = now.time()
        start = self.config.get_night_window_start()
        end = self.config.get_night_window_end()
        
        # Handle overnight windows
        if start > end:
            return current_time >= start or current_time < end
        return start <= current_time < end
    
    def is_legionella_day(self, now: Optional[datetime] = None) -> bool:
        """Check if today is the configured legionella day."""
        if now is None:
            now = datetime.now()
        
        target_day = self.DAYS.get(self.config.legionella_day, 5)  # Default Saturday
        return now.weekday() == target_day
    
    def can_start_program(self, now: Optional[datetime] = None) -> bool:
        """Check if enough time has passed since last cycle (gap protection).
        
        Args:
            now: Current time (default: now)
            
        Returns:
            True if a new program can start
        """
        if now is None:
            now = datetime.now()
        
        last_end = self.state.get_last_cycle_end()
        if last_end is None:
            return True
        
        elapsed = now - last_end
        gap_minutes = self.config.min_cycle_gap_minutes
        
        if elapsed.total_seconds() < gap_minutes * 60:
            remaining = gap_minutes - (elapsed.total_seconds() / 60)
            logger.debug("Cycle gap: %.1f minutes remaining", remaining)
            return False
        
        return True
    
    def select_program(
        self, 
        away_mode_on: bool = False,
        bath_mode_on: bool = False,
        current_water_temp: Optional[float] = None,
        now: Optional[datetime] = None
    ) -> Tuple[ProgramType, int, str]:
        """Select the appropriate heating program.
        
        Decision tree (in order of priority):
        1. Negative/zero price → 70°C
        2. Away mode active → 35°C
        3. Bath mode active (temp < 58) → 58°C
        4. Legionella day in day window → legionella temp
        5. Night window → compare night vs day prices
        6. Day window → compare today vs tomorrow prices
        7. Otherwise → Idle 35°C
        
        Args:
            away_mode_on: Is away mode entity on?
            bath_mode_on: Is bath mode entity on?
            current_water_temp: Current water temperature
            now: Current time for testing
            
        Returns:
            Tuple of (ProgramType, target_temperature, status_message)
        """
        if now is None:
            now = datetime.now()
        
        # 1. Check for negative/zero price (free energy)
        if self.price_analyzer.is_negative_price():
            logger.info("Negative/zero price detected - heating to maximum")
            return (
                ProgramType.NEGATIVE_PRICE, 
                self.preset.negative_price,
                f"Free energy - heating to {self.preset.negative_price}°C"
            )
        
        # 2. Check away mode
        if away_mode_on:
            logger.debug("Away mode active")
            # Still allow legionella on scheduled day even in away mode
            if self.is_legionella_day(now) and not self.is_in_night_window(now):
                return (
                    ProgramType.LEGIONELLA,
                    self.preset.legionella,
                    f"Away + Legionella: {self.preset.legionella}°C"
                )
            return (
                ProgramType.AWAY,
                self.preset.away,
                f"Away mode: {self.preset.away}°C"
            )
        
        # 3. Check bath mode
        if bath_mode_on:
            if current_water_temp is not None and current_water_temp < self.preset.bath:
                return (
                    ProgramType.BATH,
                    self.preset.bath,
                    f"Bath mode: heating to {self.preset.bath}°C"
                )
            # Bath mode on but already hot enough
            return (
                ProgramType.BATH,
                self.preset.bath,
                f"Bath mode: at {current_water_temp:.0f}°C (target {self.preset.bath}°C)"
            )
        
        # Get time windows
        night_start = self.config.get_night_window_start()
        night_end = self.config.get_night_window_end()
        in_night = self.is_in_night_window(now)
        
        # 4. Check legionella day (only in day window)
        if self.is_legionella_day(now) and not in_night:
            return (
                ProgramType.LEGIONELLA,
                self.preset.legionella,
                f"Legionella protection: {self.preset.legionella}°C"
            )
        
        # 5. Night program
        if in_night:
            night_cheaper = self.price_analyzer.compare_night_vs_day(night_start, night_end)
            
            if night_cheaper is True:
                return (
                    ProgramType.NIGHT,
                    self.preset.night_preheat,
                    f"Night (cheaper): preheat to {self.preset.night_preheat}°C"
                )
            elif night_cheaper is False:
                return (
                    ProgramType.NIGHT,
                    self.preset.night_minimal,
                    f"Night (day cheaper): minimal {self.preset.night_minimal}°C"
                )
            else:
                # No price data
                return (
                    ProgramType.NIGHT,
                    self.preset.night_minimal,
                    f"Night (no price data): minimal {self.preset.night_minimal}°C"
                )
        
        # 6. Day program
        today_cheaper = self.price_analyzer.compare_today_vs_tomorrow(night_end)
        
        if today_cheaper is True:
            return (
                ProgramType.DAY,
                self.preset.day_preheat,
                f"Day (today cheaper): preheat to {self.preset.day_preheat}°C"
            )
        elif today_cheaper is False:
            return (
                ProgramType.DAY,
                self.preset.day_minimal,
                f"Day (tomorrow cheaper): minimal {self.preset.day_minimal}°C"
            )
        
        # 7. Default to idle
        return (
            ProgramType.IDLE,
            self.preset.idle,
            f"Idle: standby at {self.preset.idle}°C"
        )
    
    def get_program_window(
        self, 
        program: ProgramType,
        now: Optional[datetime] = None
    ) -> Optional[Tuple[datetime, datetime]]:
        """Get the start/end times for a program.
        
        Args:
            program: The selected program
            now: Current time
            
        Returns:
            Tuple of (start_time, end_time) or None for Idle
        """
        if now is None:
            now = datetime.now()
        
        night_start = self.config.get_night_window_start()
        night_end = self.config.get_night_window_end()
        
        if program == ProgramType.IDLE:
            return None
        
        if program == ProgramType.LEGIONELLA:
            start = self.price_analyzer.get_optimal_legionella_start(
                night_end, 
                self.config.legionella_duration_hours
            )
            if start:
                end = start + timedelta(hours=self.config.legionella_duration_hours)
                return (start, end)
        
        if program == ProgramType.NIGHT:
            lowest = self.price_analyzer.get_lowest_night_price(night_start, night_end)
            if lowest:
                start = lowest[0]
                end = start + timedelta(hours=self.config.heating_duration_hours)
                return (start, end)
        
        if program == ProgramType.DAY:
            lowest = self.price_analyzer.get_lowest_day_price(night_end)
            if lowest:
                start = lowest[0]
                end = start + timedelta(hours=self.config.heating_duration_hours)
                return (start, end)
        
        # Bath/Away/NegativePrice are immediate - no specific window
        return None
    
    def mark_cycle_complete(self) -> None:
        """Mark current heating cycle as complete."""
        self.state.set_last_cycle_end(datetime.now())
        self.state.heater_on = False
        self.state.save()
        logger.debug("Marked cycle complete at %s", self.state.last_cycle_end)
