"""Scheduler for Water Heater - program selection logic.

Implements the decision tree for selecting heating programs based on:
- Price conditions (negative price)
- Mode entities (away, bath)
- Time windows (night, day, legionella)
- Cycle gap protection
"""

import logging
from dataclasses import dataclass
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


@dataclass
class ProgramDecision:
    """Decision metadata for a heating cycle."""

    program: ProgramType
    target_temp: int
    reason: str
    planned_time: Optional[datetime] = None
    planned_price: Optional[float] = None
    extra: Optional[str] = None


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
    
    def _build_day_decision(
        self,
        night_end: time,
        prefix: str = "Day",
        slot: Optional[Tuple[datetime, float]] = None,
    ) -> ProgramDecision:
        """Construct a ProgramDecision for the day window."""
        slot = slot or self.price_analyzer.get_lowest_day_price(night_end)
        today_cheaper = self.price_analyzer.compare_today_vs_tomorrow(night_end)
        target = self.preset.day_preheat
        reason = ""
        if today_cheaper is True:
            reason = f"{prefix}: today cheaper than tomorrow"
        elif today_cheaper is False:
            target = self.preset.day_minimal
            reason = f"{prefix}: tomorrow cheaper than today"
        return ProgramDecision(
            ProgramType.DAY,
            target,
            reason,
            planned_time=slot[0] if slot else None,
            planned_price=slot[1] if slot else None,
        )
    
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
    ) -> ProgramDecision:
        """Select the appropriate heating program."""
        
        if now is None:
            now = datetime.now()
        
        # 1. Check for negative/zero price (free energy)
        if self.price_analyzer.is_negative_price():
            logger.info("Negative/zero price detected - heating to maximum")
            return ProgramDecision(
                ProgramType.NEGATIVE_PRICE,
                self.preset.negative_price,
                "Free energy - maximizing temperature",
                planned_price=self.price_analyzer.current_price,
            )
        
        # 2. Check away mode
        if away_mode_on:
            logger.debug("Away mode active")
            if self.is_legionella_day(now) and not self.is_in_night_window(now):
                day_slot = self.price_analyzer.get_lowest_day_price(self.config.get_night_window_end())
                return ProgramDecision(
                    ProgramType.LEGIONELLA,
                    self.preset.legionella,
                    "Away mode + legionella protection",
                    planned_time=day_slot[0] if day_slot else None,
                    planned_price=day_slot[1] if day_slot else None,
                )
            return ProgramDecision(
                ProgramType.AWAY,
                self.preset.away,
                "Away mode active",
            )
        
        # 3. Check bath mode
        if bath_mode_on:
            if current_water_temp is not None and current_water_temp < self.preset.bath:
                reason = "Bath mode active - heating to bath target"
            else:
                reason = f"Bath mode holding at {self.preset.bath}°C"
            return ProgramDecision(
                ProgramType.BATH,
                self.preset.bath,
                reason,
                extra=(
                    f"Current water {current_water_temp:.0f}°C"
                    if current_water_temp is not None
                    else None
                ),
            )
        
        # Get time windows and price slots
        night_start = self.config.get_night_window_start()
        night_end = self.config.get_night_window_end()
        in_night = self.is_in_night_window(now)
        night_slot = self.price_analyzer.get_lowest_night_price(night_start, night_end)
        day_slot = self.price_analyzer.get_lowest_day_price(night_end)
        night_vs_day = self.price_analyzer.compare_night_vs_day(night_start, night_end)
        
        # 4. Dynamic selection (auto day vs night)
        if self.config.dynamic_window_mode:
            if night_vs_day is True:
                return ProgramDecision(
                    ProgramType.NIGHT,
                    self.preset.night_preheat,
                    "Dynamic: night window cheaper than day",
                    planned_time=night_slot[0] if night_slot else None,
                    planned_price=night_slot[1] if night_slot else None,
                )
            if night_vs_day is False:
                decision = self._build_day_decision(
                    night_end,
                    prefix="Dynamic day window",
                    slot=day_slot,
                )
                extra_reason = "Night window more expensive"
                if decision.reason:
                    decision.reason += f" | {extra_reason}"
                else:
                    decision.reason = extra_reason
                return decision
            logger.debug("Dynamic window mode enabled but insufficient price data")
        
        # 5. Legionella day in regular mode
        if self.is_legionella_day(now) and not in_night:
            return ProgramDecision(
                ProgramType.LEGIONELLA,
                self.preset.legionella,
                "Legionella protection day",
                planned_time=day_slot[0] if day_slot else None,
                planned_price=day_slot[1] if day_slot else None,
            )
        
        # 6. Night program (within night window)
        if in_night:
            if night_vs_day is True:
                reason = "Night prices cheaper than day"
                target = self.preset.night_preheat
            elif night_vs_day is False:
                reason = "Day prices cheaper - night minimal"
                target = self.preset.night_minimal
            else:
                reason = ""
                target = self.preset.night_minimal
            return ProgramDecision(
                ProgramType.NIGHT,
                target,
                reason,
                planned_time=night_slot[0] if night_slot else None,
                planned_price=night_slot[1] if night_slot else None,
            )
        
        # 7. Day program (default)
        return self._build_day_decision(night_end, slot=day_slot)
    
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

    def get_next_planned_window(
        self,
        after: datetime,
    ) -> Optional[Tuple[ProgramType, Tuple[datetime, datetime]]]:
        """Find the next planned heating window after a timestamp.

        Currently only used in dynamic window mode, once tomorrow's prices are
        available. Returns the selected program and its window.
        """
        if not self.config.dynamic_window_mode:
            return None
        if not self.price_analyzer.has_tomorrow_prices():
            return None
        if after.tzinfo is None:
            tz_after = after.replace(tzinfo=self.price_analyzer.timezone)
        else:
            tz_after = after.astimezone(self.price_analyzer.timezone)
        night_start = self.config.get_night_window_start()
        night_end = self.config.get_night_window_end()
        heating_duration = timedelta(hours=self.config.heating_duration_hours)
        # Look at the remainder of today plus the next two days to find a slot
        for offset in range(0, 3):
            date_ref = tz_after + timedelta(days=offset)
            preference = self.price_analyzer.compare_night_vs_day(
                night_start,
                night_end,
                target_date=date_ref,
            )
            if preference is None:
                continue
            if preference is True:
                slot = self.price_analyzer.get_lowest_night_price(
                    night_start,
                    night_end,
                    target_date=date_ref,
                )
                program = ProgramType.NIGHT
            else:
                slot = self.price_analyzer.get_lowest_day_price(
                    night_end,
                    target_date=date_ref,
                )
                program = ProgramType.DAY
            if slot is None:
                continue
            start = slot[0]
            if start <= tz_after:
                continue
            end = start + heating_duration
            return program, (start, end)
        return None
    
    def build_status_message(
        self,
        decision: ProgramDecision,
        window: Optional[Tuple[datetime, datetime]],
        now: Optional[datetime] = None,
    ) -> str:
        """Create a simple status string: current state + next program if any.
        
        Format: "Idle" or "Heating (58°C)" or "Idle, heating at 22:00"
        """
        if now is None:
            now = datetime.now()
        
        program = decision.program
        
        # Determine if currently heating
        is_heating = False
        if window:
            start, end = window
            is_heating = start <= now <= end
        elif program in (ProgramType.BATH, ProgramType.AWAY, ProgramType.NEGATIVE_PRICE):
            # These programs are immediate/continuous
            is_heating = True
        
        # Build current state
        if program == ProgramType.AWAY:
            return f"Away mode ({decision.target_temp}°C)"
        elif program == ProgramType.BATH:
            return f"Bath mode ({decision.target_temp}°C)"
        elif program == ProgramType.NEGATIVE_PRICE:
            return f"Free energy! ({decision.target_temp}°C)"
        elif is_heating:
            return f"Heating ({decision.target_temp}°C)"
        else:
            # Idle - check for next planned program
            if window:
                start, _ = window
                if start > now:
                    return f"Idle, heating at {start.strftime('%H:%M')}"
            next_window = self.get_next_planned_window(now)
            if next_window:
                _, (start, _) = next_window
                return f"Idle, heating at {start.strftime('%H:%M')}"
            return "Idle"
    
    def mark_cycle_complete(self) -> None:
        """Mark current heating cycle as complete."""
        self.state.set_last_cycle_end(datetime.now())
        self.state.heater_on = False
        self.state.save()
        logger.debug("Marked cycle complete at %s", self.state.last_cycle_end)
