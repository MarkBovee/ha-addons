"""Data models for Water Heater Scheduler add-on."""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, time
from enum import Enum
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ProgramType(Enum):
    """Types of heating programs."""
    IDLE = "Idle"
    NIGHT = "Night"
    DAY = "Day"
    LEGIONELLA = "Legionella"
    BATH = "Bath"
    AWAY = "Away"
    NEGATIVE_PRICE = "NegativePrice"


@dataclass
class TemperaturePreset:
    """Temperature settings for a preset profile."""
    name: str
    night_preheat: int
    night_minimal: int
    day_preheat: int
    day_minimal: int
    legionella: int
    
    # Fixed temperatures (same for all presets)
    negative_price: int = 70  # Maximum when energy is free
    bath: int = 58  # Comfortable bath temperature
    away: int = 35  # Safe minimum while absent
    idle: int = 35  # Standby temperature


# Predefined temperature presets
PRESETS: Dict[str, TemperaturePreset] = {
    "eco": TemperaturePreset(
        name="eco",
        night_preheat=52,
        night_minimal=48,
        day_preheat=55,
        day_minimal=35,
        legionella=60
    ),
    "comfort": TemperaturePreset(
        name="comfort",
        night_preheat=56,
        night_minimal=52,
        day_preheat=58,
        day_minimal=35,
        legionella=62
    ),
    "performance": TemperaturePreset(
        name="performance",
        night_preheat=60,
        night_minimal=56,
        day_preheat=60,
        day_minimal=45,
        legionella=66
    ),
}


@dataclass
class ScheduleConfig:
    """Configuration for water heater scheduling."""
    # Entity IDs
    water_heater_entity_id: str
    price_sensor_entity_id: str = "sensor.ep_price_import"
    away_mode_entity_id: Optional[str] = None
    bath_mode_entity_id: Optional[str] = None
    
    # Schedule settings
    evaluation_interval_minutes: int = 5
    night_window_start: str = "00:00"
    night_window_end: str = "06:00"
    heating_duration_hours: int = 1
    legionella_day: str = "Saturday"
    legionella_duration_hours: int = 3
    bath_auto_off_temp: int = 50
    
    # Temperature preset
    temperature_preset: str = "comfort"
    
    # Custom temperature overrides
    night_preheat_temp: Optional[int] = None
    night_minimal_temp: Optional[int] = None
    day_preheat_temp: Optional[int] = None
    day_minimal_temp: Optional[int] = None
    legionella_temp: Optional[int] = None
    
    # Advanced settings
    min_cycle_gap_minutes: int = 50
    log_level: str = "info"
    dynamic_window_mode: bool = False
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ScheduleConfig":
        """Create ScheduleConfig from addon configuration dict."""
        # Filter empty strings to None for optional fields
        def empty_to_none(value):
            return None if value == "" else value
        
        def to_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
        
        return cls(
            water_heater_entity_id=config.get("water_heater_entity_id", ""),
            price_sensor_entity_id=config.get("price_sensor_entity_id", "sensor.ep_price_import") or "sensor.ep_price_import",
            away_mode_entity_id=empty_to_none(config.get("away_mode_entity_id")),
            bath_mode_entity_id=empty_to_none(config.get("bath_mode_entity_id")),
            evaluation_interval_minutes=config.get("evaluation_interval_minutes", 5),
            night_window_start=config.get("night_window_start", "00:00"),
            night_window_end=config.get("night_window_end", "06:00"),
            heating_duration_hours=config.get("heating_duration_hours", 1),
            legionella_day=config.get("legionella_day", "Saturday"),
            legionella_duration_hours=config.get("legionella_duration_hours", 3),
            bath_auto_off_temp=config.get("bath_auto_off_temp", 50),
            temperature_preset=config.get("temperature_preset", "comfort"),
            night_preheat_temp=config.get("night_preheat_temp"),
            night_minimal_temp=config.get("night_minimal_temp"),
            day_preheat_temp=config.get("day_preheat_temp"),
            day_minimal_temp=config.get("day_minimal_temp"),
            legionella_temp=config.get("legionella_temp"),
            min_cycle_gap_minutes=config.get("min_cycle_gap_minutes", 50),
            log_level=config.get("log_level", "info"),
            dynamic_window_mode=to_bool(config.get("dynamic_window_mode", False)),
        )
    
    def get_preset(self) -> TemperaturePreset:
        """Get the temperature preset based on configuration."""
        if self.temperature_preset == "custom":
            return TemperaturePreset(
                name="custom",
                night_preheat=self.night_preheat_temp or 56,
                night_minimal=self.night_minimal_temp or 52,
                day_preheat=self.day_preheat_temp or 58,
                day_minimal=self.day_minimal_temp or 35,
                legionella=self.legionella_temp or 62,
            )
        return PRESETS.get(self.temperature_preset, PRESETS["comfort"])
    
    def get_night_window_start(self) -> time:
        """Parse night window start time."""
        parts = self.night_window_start.split(":")
        return time(int(parts[0]), int(parts[1]))
    
    def get_night_window_end(self) -> time:
        """Parse night window end time."""
        parts = self.night_window_end.split(":")
        return time(int(parts[0]), int(parts[1]))
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings."""
        warnings = []
        preset = self.get_preset()
        
        # Check required entity
        if not self.water_heater_entity_id:
            warnings.append("ERROR: water_heater_entity_id is required")
        
        # Validate legionella temperature
        if preset.legionella < 60:
            warnings.append(f"Legionella temp {preset.legionella}°C is below 60°C - may not be effective for sanitization")
        
        # Validate temperature ordering
        if preset.night_preheat < preset.night_minimal:
            warnings.append(f"night_preheat ({preset.night_preheat}°C) should be higher than night_minimal ({preset.night_minimal}°C)")
        
        if preset.day_preheat < preset.day_minimal:
            warnings.append(f"day_preheat ({preset.day_preheat}°C) should be higher than day_minimal ({preset.day_minimal}°C)")
        
        return warnings


@dataclass
class HeaterState:
    """Persistent state for water heater scheduler."""
    current_program: str = "Idle"
    target_temperature: int = 35
    last_cycle_end: Optional[str] = None  # ISO format datetime string
    last_legionella_protection: Optional[str] = None  # ISO format datetime string
    heater_on: bool = False
    wait_cycles: int = 0
    
    @classmethod
    def load(cls, state_path: str = "/data/state.json") -> "HeaterState":
        """Load state from JSON file."""
        path = Path(state_path)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                logger.info(
                    "Restored state: program=%s, temp=%d°C, last_legionella=%s",
                    data.get("current_program", "Idle"),
                    data.get("target_temperature", 35),
                    data.get("last_legionella_protection", "never"),
                )
                return cls(
                    current_program=data.get("current_program", "Idle"),
                    target_temperature=data.get("target_temperature", 35),
                    last_cycle_end=data.get("last_cycle_end"),
                    last_legionella_protection=data.get("last_legionella_protection"),
                    heater_on=data.get("heater_on", False),
                    wait_cycles=data.get("wait_cycles", 0),
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load state file: %s", e)
        return cls()
    
    def save(self, state_path: str = "/data/state.json") -> None:
        """Save state to JSON file."""
        path = Path(state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump(asdict(self), f, indent=2)
        except IOError as e:
            logger.error("Failed to save state file: %s", e)
    
    def get_last_cycle_end(self) -> Optional[datetime]:
        """Parse last_cycle_end as datetime."""
        if self.last_cycle_end:
            try:
                return datetime.fromisoformat(self.last_cycle_end)
            except ValueError:
                pass
        return None
    
    def set_last_cycle_end(self, dt: datetime) -> None:
        """Set last_cycle_end from datetime."""
        self.last_cycle_end = dt.isoformat()

    def get_last_legionella_protection(self) -> Optional[datetime]:
        """Parse last_legionella_protection as datetime."""
        if self.last_legionella_protection:
            try:
                return datetime.fromisoformat(self.last_legionella_protection)
            except ValueError:
                pass
        return None

    def set_last_legionella_protection(self, dt: datetime) -> None:
        """Set last_legionella_protection from datetime."""
        self.last_legionella_protection = dt.isoformat()

    def needs_legionella_protection(self, interval_days: int = 7) -> bool:
        """Check if legionella protection is needed based on last run."""
        last_run = self.get_last_legionella_protection()
        if last_run is None:
            return True  # Never run, need protection
        days_since = (datetime.now() - last_run).days
        return days_since >= interval_days
