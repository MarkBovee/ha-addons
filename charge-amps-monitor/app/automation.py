"""Charging schedule automation coordinator using price slot analysis."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from shared.ha_api import HomeAssistantApi

from .charger_api import ChargerApi
from .price_slot_analyzer import DailyPriceAnalysis, PriceSlot, PriceSlotAnalyzer

logger = logging.getLogger(__name__)
WEEK_SECONDS = 7 * 24 * 60 * 60


@dataclass
class AutomationConfig:
    """Configuration for the charging automation."""
    enabled: bool
    operation_mode: str  # 'standalone' or 'hems'
    price_entity_id: str
    top_x_charge_count: int
    price_threshold: float  # EUR/kWh - max price for charging (standalone only)
    max_current_per_phase: int
    connector_id: int
    timezone: str


@dataclass
class AutomationStatus:
    """Status of the automation system."""
    state: str
    message: str
    next_start: Optional[str]
    next_end: Optional[str]
    last_error: Optional[str]
    plan_date: Optional[str]
    attributes: dict = field(default_factory=dict)


@dataclass 
class ChargingSchedule:
    """Represents a full charging schedule with cheap slots for today and tomorrow."""
    today_slots: List[PriceSlot]
    tomorrow_slots: List[PriceSlot]
    today_analysis: Optional[DailyPriceAnalysis]
    tomorrow_analysis: Optional[DailyPriceAnalysis]
    
    def log_schedule(self) -> None:
        """Log the full charging schedule (debug level)."""
        logger.debug("=" * 70)
        logger.debug("📅 CHARGING SCHEDULE - Top %d cheapest slots per day", 
                    len(self.today_slots) if self.today_slots else 0)
        logger.debug("=" * 70)
        
        if self.today_analysis:
            logger.debug("")
            logger.debug("📊 TODAY (%s)", self.today_analysis.target_date.isoformat())
            logger.debug("-" * 50)
            logger.debug("   Price range: %.2f - %.2f cents/kWh (avg: %.2f)",
                       self.today_analysis.min_price,
                       self.today_analysis.max_price,
                       self.today_analysis.avg_price)
            logger.debug("   Total slots available: %d", len(self.today_analysis.all_slots))
            logger.debug("")
            logger.debug("   ⚡ CHEAPEST CHARGING SLOTS:")
            for slot in self.today_slots:
                logger.debug("      Rank %2d: %s - %s @ %.2f cents/kWh",
                           slot.rank,
                           slot.start.strftime("%H:%M"),
                           slot.end.strftime("%H:%M"),
                           slot.price)
        else:
            logger.debug("   ⚠️ No price data available for today")
        
        logger.debug("")
        
        if self.tomorrow_analysis:
            logger.debug("📊 TOMORROW (%s)", self.tomorrow_analysis.target_date.isoformat())
            logger.debug("-" * 50)
            logger.debug("   Price range: %.2f - %.2f cents/kWh (avg: %.2f)",
                       self.tomorrow_analysis.min_price,
                       self.tomorrow_analysis.max_price,
                       self.tomorrow_analysis.avg_price)
            logger.debug("   Total slots available: %d", len(self.tomorrow_analysis.all_slots))
            logger.debug("")
            logger.debug("   ⚡ CHEAPEST CHARGING SLOTS:")
            for slot in self.tomorrow_slots:
                logger.debug("      Rank %2d: %s - %s @ %.2f cents/kWh",
                           slot.rank,
                           slot.start.strftime("%H:%M"),
                           slot.end.strftime("%H:%M"),
                           slot.price)
        else:
            logger.debug("   ℹ️ Tomorrow's prices not yet available (usually published around 13:00)")
        
        logger.debug("")
        logger.debug("=" * 70)


class ChargingAutomationCoordinator:
    """Coordinates price analysis and schedule management."""

    def __init__(
        self,
        charger_api: ChargerApi,
        ha_api: HomeAssistantApi,
        config: AutomationConfig,
        data_path: str = "/data",
    ) -> None:
        self._charger_api = charger_api
        self._ha_api = ha_api
        self._config = config
        self._tz = ZoneInfo(config.timezone)
        self._analyzer = PriceSlotAnalyzer(
            ha_api=ha_api,
            price_entity_id=config.price_entity_id,
            timezone_name=config.timezone,
            top_x_count=config.top_x_charge_count,
            price_threshold=config.price_threshold,
        )
        self._last_schedule: Optional[ChargingSchedule] = None
        self._last_analysis_time: Optional[datetime] = None
        self._last_pushed_periods: Optional[List[dict]] = None  # Track last pushed schedule
        self._force_refresh = False
        self._status = AutomationStatus(
            state="disabled" if not config.enabled else "idle",
            message="Automation disabled" if not config.enabled else "Idle",
            next_start=None,
            next_end=None,
            last_error=None,
            plan_date=None,
            attributes={"automation_enabled": config.enabled},
        )

    def update_config(self, config: AutomationConfig) -> None:
        """Update the configuration."""
        self._config = config
        self._tz = ZoneInfo(config.timezone)
        self._analyzer = PriceSlotAnalyzer(
            ha_api=self._ha_api,
            price_entity_id=config.price_entity_id,
            timezone_name=config.timezone,
            top_x_count=config.top_x_charge_count,
            price_threshold=config.price_threshold,
        )
        self._status.attributes.update({"automation_enabled": config.enabled})
        if not config.enabled:
            self._force_refresh = False

    def request_force_refresh(self, source: str = "user") -> None:
        """Request a forced refresh of the schedule."""
        logger.info("Force schedule refresh requested via %s", source)
        self._force_refresh = True

    def analyze_prices(self) -> ChargingSchedule:
        """Analyze prices and create a charging schedule for today and tomorrow."""
        today_analysis = self._analyzer.analyze_today()
        tomorrow_analysis = self._analyzer.analyze_tomorrow()
        
        today_slots = today_analysis.cheapest_slots if today_analysis else []
        tomorrow_slots = tomorrow_analysis.cheapest_slots if tomorrow_analysis else []
        
        schedule = ChargingSchedule(
            today_slots=today_slots,
            tomorrow_slots=tomorrow_slots,
            today_analysis=today_analysis,
            tomorrow_analysis=tomorrow_analysis,
        )
        
        self._last_schedule = schedule
        self._last_analysis_time = datetime.now(self._tz)
        
        return schedule

    def tick(self, now: Optional[datetime] = None, charge_point_id: Optional[str] = None) -> AutomationStatus:
        """Process one tick of the automation loop.
        
        Args:
            now: Optional current time for testing
            charge_point_id: Charge point ID to push schedule to (required for schedule push)
        """
        now_local = (now or datetime.utcnow().replace(tzinfo=timezone.utc)).astimezone(self._tz)

        if not self._config.enabled:
            self._status = AutomationStatus(
                state="disabled",
                message="Automation disabled",
                next_start=None,
                next_end=None,
                last_error=None,
                plan_date=None,
                attributes={"automation_enabled": False},
            )
            return self._status

        # Check if we've crossed into a new week (Monday) - need to reset week anchor
        current_week_start = self._get_week_start(now_local)
        last_week_start = (
            self._get_week_start(self._last_analysis_time)
            if self._last_analysis_time
            else None
        )
        week_changed = last_week_start is not None and current_week_start != last_week_start

        if week_changed:
            logger.info("New week detected - resetting schedule cache")
            self._last_pushed_periods = None  # Force schedule push with new week anchor

        # Analyze prices if needed (force refresh or first run or new day)
        needs_analysis = (
            self._force_refresh 
            or self._last_schedule is None 
            or self._last_analysis_time is None
            or self._last_analysis_time.date() != now_local.date()
        )

        if needs_analysis:
            try:
                schedule = self.analyze_prices()
                schedule.log_schedule()
                self._force_refresh = False
                
                # Push schedule to charger if we have a charge point ID
                schedule_pushed = False
                if charge_point_id and (schedule.today_slots or schedule.tomorrow_slots):
                    schedule_pushed = self.push_schedule_to_charger(charge_point_id)
                elif not charge_point_id:
                    logger.warning("No charge point ID provided - schedule not pushed to charger")
                
                # Update status with next charging slot
                next_slot = self._find_next_charging_slot(now_local)
                if next_slot:
                    self._status = AutomationStatus(
                        state="scheduled",
                        message=f"Next cheap slot: {next_slot.start.strftime('%H:%M')} @ {next_slot.price:.2f}c",
                        next_start=next_slot.start.isoformat(),
                        next_end=next_slot.end.isoformat(),
                        last_error=None,
                        plan_date=now_local.date().isoformat(),
                        attributes={
                            "automation_enabled": True,
                            "top_x_charge_count": self._config.top_x_charge_count,
                            "today_slots": len(schedule.today_slots),
                            "tomorrow_slots": len(schedule.tomorrow_slots),
                            "schedule_pushed": schedule_pushed,
                        },
                    )
                else:
                    self._status = AutomationStatus(
                        state="waiting_for_prices",
                        message="No price data available",
                        next_start=None,
                        next_end=None,
                        last_error="Price sensor has no data",
                        plan_date=None,
                        attributes={"automation_enabled": True},
                    )
            except Exception as exc:
                logger.error("Failed to analyze prices: %s", exc, exc_info=True)
                self._status = AutomationStatus(
                    state="error",
                    message=f"Analysis failed: {exc}",
                    next_start=None,
                    next_end=None,
                    last_error=str(exc),
                    plan_date=None,
                    attributes={"automation_enabled": True},
                )

        self._status.attributes.update(
            {
                "connector_id": self._config.connector_id,
                "timezone": self._config.timezone,
            }
        )
        return self._status

    def _find_next_charging_slot(self, now: datetime) -> Optional[PriceSlot]:
        """Find the next upcoming charging slot."""
        if not self._last_schedule:
            return None
        
        # Check today's slots first
        for slot in self._last_schedule.today_slots:
            if slot.start > now:
                return slot
        
        # Then check tomorrow's slots
        for slot in self._last_schedule.tomorrow_slots:
            if slot.start > now:
                return slot
        
        return None

    def is_in_charging_slot(self, now: Optional[datetime] = None) -> bool:
        """Check if the current time is within a cheap charging slot."""
        now_local = (now or datetime.utcnow().replace(tzinfo=timezone.utc)).astimezone(self._tz)
        
        if not self._last_schedule:
            return False
        
        # Check today's slots
        for slot in self._last_schedule.today_slots:
            if slot.start <= now_local < slot.end:
                return True
        
        # Check tomorrow's slots (in case we're past midnight)
        for slot in self._last_schedule.tomorrow_slots:
            if slot.start <= now_local < slot.end:
                return True
        
        return False

    def get_current_slot_rank(self, now: Optional[datetime] = None) -> Optional[int]:
        """Get the rank of the current slot if we're in one."""
        now_local = (now or datetime.utcnow().replace(tzinfo=timezone.utc)).astimezone(self._tz)
        
        if not self._last_schedule:
            return None
        
        # Check today's slots
        for slot in self._last_schedule.today_slots:
            if slot.start <= now_local < slot.end:
                return slot.rank
        
        # Check tomorrow's slots
        for slot in self._last_schedule.tomorrow_slots:
            if slot.start <= now_local < slot.end:
                return slot.rank
        
        return None

    def _get_week_start(self, dt: datetime) -> datetime:
        """Get the start of the Charge Amps schedule week (Monday 00:00 local time).

        The API expects a stable startOfSchedule anchor for the week. Using Monday
        at midnight ensures:
        - Schedule persists across daily updates (same anchor all week)
        - All days Mon-Sun fit within the 7-day (604800s) window
        - Only needs refresh when we cross into a new week
        """
        local_dt = dt.astimezone(self._tz)
        # weekday(): Monday=0, Sunday=6
        days_since_monday = local_dt.weekday()
        monday_midnight_local = (
            local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=days_since_monday)
        )
        return monday_midnight_local.astimezone(timezone.utc)

    def _slot_to_week_seconds(self, slot: PriceSlot, week_start: datetime) -> tuple[int, int]:
        """Convert a price slot to seconds from start of week (from, to)."""
        slot_start_utc = slot.start.astimezone(timezone.utc)
        slot_end_utc = slot.end.astimezone(timezone.utc)
        
        from_seconds = int((slot_start_utc - week_start).total_seconds())
        to_seconds = int((slot_end_utc - week_start).total_seconds())
        
        return (from_seconds, to_seconds)

    def _slots_to_schedule_periods(
        self, 
        slots: List[PriceSlot], 
        week_start: datetime
    ) -> List[dict]:
        """Convert price slots to Charge Amps schedule periods, merging consecutive slots."""
        if not slots:
            return []
        
        # Convert all slots to (from, to) seconds and clamp to the current week window
        raw_periods = []
        for slot in slots:
            from_sec, to_sec = self._slot_to_week_seconds(slot, week_start)
            if from_sec < 0:
                continue

            if from_sec >= WEEK_SECONDS:
                logger.warning(
                    "Skipping slot starting at %s because it exceeds the current week window",
                    slot.start.isoformat(),
                )
                continue

            if to_sec > WEEK_SECONDS:
                to_sec = WEEK_SECONDS

            raw_periods.append({"from": from_sec, "to": to_sec})
        
        if not raw_periods:
            return []
        
        # Sort by start time
        raw_periods.sort(key=lambda p: p["from"])
        
        # Merge consecutive periods
        merged = []
        current = raw_periods[0].copy()
        
        for next_period in raw_periods[1:]:
            # If the next period starts exactly where current ends, merge them
            if next_period["from"] == current["to"]:
                current["to"] = next_period["to"]
            else:
                # Gap between periods - save current and start new
                merged.append(current)
                current = next_period.copy()
        
        # Don't forget the last period
        merged.append(current)
        
        return merged

    def push_schedule_to_charger(self, charge_point_id: str) -> bool:
        """Push the current schedule to the Charge Amps charger.
        
        Only pushes if the schedule has changed since last push.
        Returns True if schedule was pushed (or unchanged), False on error.
        """
        if not self._last_schedule:
            logger.warning("No schedule to push - run analyze_prices() first")
            return False
        
        # Combine today and tomorrow slots
        all_slots = self._last_schedule.today_slots + self._last_schedule.tomorrow_slots
        
        if not all_slots:
            logger.warning("No charging slots to push")
            return False
        
        # Get the week start for the schedule
        now = datetime.now(self._tz)
        week_start = self._get_week_start(now)
        
        # Convert slots to schedule periods
        periods = self._slots_to_schedule_periods(all_slots, week_start)
        
        if not periods:
            logger.warning("No valid schedule periods after conversion")
            return False
        
        # Check if schedule changed since last push
        if self._last_pushed_periods is not None and periods == self._last_pushed_periods:
            logger.debug("Schedule unchanged - skipping push (%d periods)", len(periods))
            return True  # Return True since schedule is already correct
        
        # Schedule changed - log and push
        logger.info("📤 Pushing schedule to charger: %d periods", len(periods))
        logger.debug("   Week start: %s", week_start.isoformat())
        
        # Log the periods being pushed
        for i, p in enumerate(periods[:5]):  # Log first 5
            slot_start = week_start + timedelta(seconds=p["from"])
            slot_end = week_start + timedelta(seconds=p["to"])
            logger.info("   Period %d: %s - %s", 
                       i + 1, 
                       slot_start.astimezone(self._tz).strftime("%a %H:%M"),
                       slot_end.astimezone(self._tz).strftime("%H:%M"))
        if len(periods) > 5:
            logger.info("   ... and %d more periods", len(periods) - 5)
        
        # Push to charger
        result = self._charger_api.upsert_schedule(
            charge_point_id=charge_point_id,
            connector_id=self._config.connector_id,
            start_of_schedule=week_start.isoformat().replace("+00:00", "Z"),
            schedule_periods=periods,
            max_current=float(self._config.max_current_per_phase),
            timezone_name=self._config.timezone,
        )
        
        if result:
            schedule_id = result.get("scheduleId")
            logger.info("✅ Schedule pushed successfully (ID: %s)", schedule_id)
            self._last_pushed_periods = periods  # Remember what we pushed
            return True
        else:
            logger.error("❌ Failed to push schedule to charger")
            return False