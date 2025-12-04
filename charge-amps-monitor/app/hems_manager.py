"""HEMS Schedule Manager - handles external schedule commands via MQTT.

This module provides the bridge between an external HEMS (Home Energy Management System)
and the charge-amps-monitor add-on. When operation_mode is 'hems', this manager:

1. Subscribes to MQTT topics for schedule commands
2. Validates and converts incoming schedule payloads
3. Pushes schedules to the Charge Amps API
4. Publishes status updates back to HEMS

MQTT Topics:
- hems/charge-amps/{connector_id}/schedule/set - Receive schedule from HEMS
- hems/charge-amps/{connector_id}/schedule/clear - Clear current schedule
- hems/charge-amps/{connector_id}/status - Publish status to HEMS
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from shared.ha_mqtt_discovery import MqttDiscovery

logger = logging.getLogger(__name__)


@dataclass
class HEMSPeriod:
    """A charging period from HEMS.
    
    Attributes:
        start: ISO format datetime string for period start
        end: ISO format datetime string for period end
        max_current: Optional max current in amps (uses config default if not set)
    """
    start: str
    end: str
    max_current: Optional[float] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional['HEMSPeriod']:
        """Parse a period from HEMS JSON payload."""
        if not isinstance(data, dict):
            return None
        start = data.get('start')
        end = data.get('end')
        if not start or not end:
            return None
        return cls(
            start=start,
            end=end,
            max_current=data.get('max_current'),
        )


@dataclass
class HEMSSchedule:
    """A complete schedule from HEMS.
    
    Attributes:
        periods: List of charging periods
        expires_at: Optional ISO datetime when schedule expires
        source_id: Optional identifier of the HEMS system
    """
    periods: List[HEMSPeriod]
    expires_at: Optional[str] = None
    source_id: Optional[str] = None
    received_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @classmethod
    def from_json(cls, payload: str) -> Optional['HEMSSchedule']:
        """Parse a schedule from HEMS JSON payload.
        
        Expected format:
        {
            "periods": [
                {"start": "2025-01-15T02:00:00", "end": "2025-01-15T04:00:00"},
                {"start": "2025-01-15T14:00:00", "end": "2025-01-15T15:30:00", "max_current": 10}
            ],
            "expires_at": "2025-01-15T23:59:59",  // optional
            "source_id": "battery-optimizer"       // optional
        }
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in HEMS schedule payload: %s", e)
            return None
        
        if not isinstance(data, dict):
            logger.error("HEMS schedule payload must be a JSON object")
            return None
        
        periods_data = data.get('periods')
        if not isinstance(periods_data, list):
            logger.error("HEMS schedule must contain 'periods' array")
            return None
        
        periods = []
        for i, p in enumerate(periods_data):
            period = HEMSPeriod.from_dict(p)
            if period:
                periods.append(period)
            else:
                logger.warning("Skipping invalid period at index %d: %s", i, p)
        
        if not periods:
            logger.error("HEMS schedule contains no valid periods")
            return None
        
        return cls(
            periods=periods,
            expires_at=data.get('expires_at'),
            source_id=data.get('source_id'),
        )
    
    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Check if the schedule has expired."""
        if not self.expires_at:
            return False
        now = now or datetime.now()
        try:
            expires = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            # Make now timezone-aware if expires is
            if expires.tzinfo and not now.tzinfo:
                now = now.replace(tzinfo=expires.tzinfo)
            return now > expires
        except ValueError:
            logger.warning("Invalid expires_at format: %s", self.expires_at)
            return False


@dataclass
class HEMSStatus:
    """Status published to HEMS."""
    schedule_source: str  # 'standalone', 'hems', or 'none'
    charger_state: str  # 'online', 'offline', 'charging', etc.
    ready_for_schedule: bool
    current_schedule_id: Optional[str] = None
    last_command_at: Optional[str] = None
    last_command_result: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'schedule_source': self.schedule_source,
            'charger_state': self.charger_state,
            'ready_for_schedule': self.ready_for_schedule,
            'current_schedule_id': self.current_schedule_id,
            'last_command_at': self.last_command_at,
            'last_command_result': self.last_command_result,
            'error': self.error,
            'timestamp': datetime.now().isoformat(),
        }


class HEMSScheduleManager:
    """Manages HEMS schedule reception and status publishing.
    
    This class handles:
    - MQTT subscription for schedule commands
    - Schedule validation and conversion
    - Status publishing back to HEMS
    - Schedule expiration checking
    """
    
    TOPIC_PREFIX = "hems/charge-amps"
    
    def __init__(
        self,
        mqtt_client: 'MqttDiscovery',
        connector_id: int,
        timezone_name: str,
        default_max_current: float,
        on_schedule_received: Optional[Callable[[List[Dict[str, Any]]], bool]] = None,
        on_schedule_cleared: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Initialize the HEMS manager.
        
        Args:
            mqtt_client: Connected MQTT client for pub/sub
            connector_id: Charge Amps connector ID
            timezone_name: Timezone for schedule conversion
            default_max_current: Default max current if not specified in schedule
            on_schedule_received: Callback when valid schedule received, returns success
            on_schedule_cleared: Callback when clear command received, returns success
        """
        self._mqtt = mqtt_client
        self._connector_id = connector_id
        self._tz = ZoneInfo(timezone_name)
        self._default_max_current = default_max_current
        self._on_schedule_received = on_schedule_received
        self._on_schedule_cleared = on_schedule_cleared
        
        self._current_schedule: Optional[HEMSSchedule] = None
        self._last_command_at: Optional[str] = None
        self._last_command_result: Optional[str] = None
        self._last_error: Optional[str] = None
        self._subscribed = False
    
    @property
    def schedule_topic_set(self) -> str:
        """MQTT topic for receiving schedules."""
        return f"{self.TOPIC_PREFIX}/{self._connector_id}/schedule/set"
    
    @property
    def schedule_topic_clear(self) -> str:
        """MQTT topic for clearing schedules."""
        return f"{self.TOPIC_PREFIX}/{self._connector_id}/schedule/clear"
    
    @property
    def status_topic(self) -> str:
        """MQTT topic for publishing status."""
        return f"{self.TOPIC_PREFIX}/{self._connector_id}/status"
    
    @property
    def has_active_schedule(self) -> bool:
        """Check if there's an active HEMS schedule."""
        if not self._current_schedule:
            return False
        return not self._current_schedule.is_expired()
    
    @property
    def last_command_at(self) -> Optional[str]:
        """Timestamp of last HEMS command."""
        return self._last_command_at
    
    @property
    def current_source_id(self) -> Optional[str]:
        """Source ID of current schedule, if any."""
        if self._current_schedule:
            return self._current_schedule.source_id
        return None
    
    def subscribe(self) -> bool:
        """Subscribe to HEMS command topics.
        
        Returns:
            True if subscriptions successful
        """
        if self._subscribed:
            logger.debug("Already subscribed to HEMS topics")
            return True
        
        if not self._mqtt or not self._mqtt.is_connected():
            logger.error("Cannot subscribe to HEMS topics: MQTT not connected")
            return False
        
        # Subscribe to schedule/set
        if not self._mqtt.subscribe(self.schedule_topic_set, self._handle_schedule_set):
            logger.error("Failed to subscribe to %s", self.schedule_topic_set)
            return False
        
        # Subscribe to schedule/clear
        if not self._mqtt.subscribe(self.schedule_topic_clear, self._handle_schedule_clear):
            logger.error("Failed to subscribe to %s", self.schedule_topic_clear)
            return False
        
        self._subscribed = True
        logger.info("🔔 HEMS mode: subscribed to schedule topics for connector %d", self._connector_id)
        logger.info("   Set topic: %s", self.schedule_topic_set)
        logger.info("   Clear topic: %s", self.schedule_topic_clear)
        return True
    
    def _handle_schedule_set(self, payload: str) -> None:
        """Handle incoming schedule/set message."""
        self._last_command_at = datetime.now().isoformat()
        logger.info("📥 Received HEMS schedule command (%d bytes)", len(payload))
        
        # Parse the schedule
        schedule = HEMSSchedule.from_json(payload)
        if not schedule:
            self._last_command_result = "error"
            self._last_error = "Invalid schedule payload"
            self.publish_status("error", ready=True)
            return
        
        # Check if expired
        if schedule.is_expired():
            logger.warning("Received already-expired schedule (expires_at: %s)", schedule.expires_at)
            self._last_command_result = "error"
            self._last_error = "Schedule already expired"
            self.publish_status("error", ready=True)
            return
        
        # Convert to Charge Amps format
        try:
            periods = self._convert_to_charger_periods(schedule)
        except Exception as e:
            logger.error("Failed to convert HEMS schedule: %s", e)
            self._last_command_result = "error"
            self._last_error = str(e)
            self.publish_status("error", ready=True)
            return
        
        if not periods:
            logger.warning("HEMS schedule converted to 0 valid periods")
            self._last_command_result = "error"
            self._last_error = "No valid periods after conversion"
            self.publish_status("error", ready=True)
            return
        
        # Call the schedule callback if set
        if self._on_schedule_received:
            success = self._on_schedule_received(periods)
            if success:
                self._current_schedule = schedule
                self._last_command_result = "success"
                self._last_error = None
                logger.info("✅ HEMS schedule applied: %d periods", len(periods))
                self.publish_status("active", ready=True)
            else:
                self._last_command_result = "error"
                self._last_error = "Failed to apply schedule to charger"
                self.publish_status("error", ready=True)
        else:
            # No callback - just store the schedule
            self._current_schedule = schedule
            self._last_command_result = "success"
            self._last_error = None
            logger.info("📋 HEMS schedule stored (no apply callback): %d periods", len(periods))
    
    def _handle_schedule_clear(self, payload: str) -> None:
        """Handle incoming schedule/clear message."""
        self._last_command_at = datetime.now().isoformat()
        logger.info("🗑️ Received HEMS clear schedule command")
        
        if self._on_schedule_cleared:
            success = self._on_schedule_cleared()
            if success:
                self._current_schedule = None
                self._last_command_result = "cleared"
                self._last_error = None
                logger.info("✅ HEMS schedule cleared")
                self.publish_status("idle", ready=True)
            else:
                self._last_command_result = "error"
                self._last_error = "Failed to clear schedule"
                self.publish_status("error", ready=True)
        else:
            # No callback - just clear stored schedule
            self._current_schedule = None
            self._last_command_result = "cleared"
            self._last_error = None
    
    def _convert_to_charger_periods(self, schedule: HEMSSchedule) -> List[Dict[str, Any]]:
        """Convert HEMS schedule to Charge Amps format.
        
        HEMS format: {start: ISO datetime, end: ISO datetime, max_current: optional}
        Charger format: {from: seconds from week start, to: seconds from week start}
        
        Returns:
            List of period dicts in Charge Amps format
        """
        # Get the week start for conversion (Monday 00:00 UTC)
        now = datetime.now(self._tz)
        week_start = self._get_week_start(now)
        
        periods = []
        for hems_period in schedule.periods:
            try:
                # Parse ISO datetimes
                start_dt = datetime.fromisoformat(hems_period.start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(hems_period.end.replace('Z', '+00:00'))
                
                # Ensure timezone-aware
                if not start_dt.tzinfo:
                    start_dt = start_dt.replace(tzinfo=self._tz)
                if not end_dt.tzinfo:
                    end_dt = end_dt.replace(tzinfo=self._tz)
                
                # Skip periods in the past
                if end_dt <= now:
                    logger.debug("Skipping past period: %s - %s", hems_period.start, hems_period.end)
                    continue
                
                # Convert to seconds from week start
                start_seconds = int((start_dt - week_start).total_seconds())
                end_seconds = int((end_dt - week_start).total_seconds())
                
                # Handle negative (periods before week start) by adding a week
                if start_seconds < 0:
                    start_seconds += 7 * 24 * 3600
                    end_seconds += 7 * 24 * 3600
                
                # Cap at one week
                max_seconds = 7 * 24 * 3600
                if start_seconds >= max_seconds:
                    continue
                if end_seconds > max_seconds:
                    end_seconds = max_seconds
                
                periods.append({
                    "from": start_seconds,
                    "to": end_seconds,
                })
                
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse period %s - %s: %s", 
                             hems_period.start, hems_period.end, e)
                continue
        
        # Sort by start time and merge overlapping
        periods.sort(key=lambda p: p["from"])
        return self._merge_overlapping_periods(periods)
    
    def _get_week_start(self, dt: datetime) -> datetime:
        """Get the Monday 00:00 UTC of the week containing dt."""
        # Convert to UTC for calculation
        dt_utc = dt.astimezone(ZoneInfo("UTC"))
        days_since_monday = dt_utc.weekday()
        week_start = dt_utc - timedelta(days=days_since_monday)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return week_start
    
    def _merge_overlapping_periods(self, periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge overlapping or adjacent periods."""
        if not periods:
            return []
        
        merged = [periods[0].copy()]
        for period in periods[1:]:
            last = merged[-1]
            # If periods overlap or are adjacent (within 1 second), merge them
            if period["from"] <= last["to"] + 1:
                last["to"] = max(last["to"], period["to"])
            else:
                merged.append(period.copy())
        
        return merged
    
    def publish_status(
        self,
        charger_state: str,
        ready: bool = True,
        schedule_id: Optional[str] = None,
    ) -> bool:
        """Publish status to HEMS.
        
        Args:
            charger_state: Current charger state
            ready: Whether charger is ready for schedule commands
            schedule_id: Optional schedule ID if one is active
            
        Returns:
            True if published successfully
        """
        if not self._mqtt or not self._mqtt.is_connected():
            logger.debug("Cannot publish HEMS status: MQTT not connected")
            return False
        
        schedule_source = "hems" if self._current_schedule else "none"
        
        status = HEMSStatus(
            schedule_source=schedule_source,
            charger_state=charger_state,
            ready_for_schedule=ready,
            current_schedule_id=schedule_id,
            last_command_at=self._last_command_at,
            last_command_result=self._last_command_result,
            error=self._last_error,
        )
        
        return self._mqtt.publish_raw(self.status_topic, status.to_dict(), retain=True)
    
    def check_expiration(self) -> bool:
        """Check if current schedule has expired and clear if so.
        
        Returns:
            True if schedule was expired and cleared
        """
        if not self._current_schedule:
            return False
        
        if self._current_schedule.is_expired():
            logger.info("HEMS schedule expired (expires_at: %s)", 
                       self._current_schedule.expires_at)
            
            # Clear the schedule
            if self._on_schedule_cleared:
                self._on_schedule_cleared()
            
            self._current_schedule = None
            self._last_command_result = "expired"
            self.publish_status("idle", ready=True)
            return True
        
        return False
    
    def get_status_attributes(self) -> Dict[str, Any]:
        """Get status attributes for Home Assistant sensors."""
        return {
            "hems_connected": self._mqtt.is_connected() if self._mqtt else False,
            "hems_subscribed": self._subscribed,
            "hems_last_command_at": self._last_command_at,
            "hems_last_command_result": self._last_command_result,
            "hems_schedule_active": self.has_active_schedule,
            "hems_schedule_source_id": self.current_source_id,
            "hems_last_error": self._last_error,
        }
