"""Data update coordinator for Water Heater Scheduler."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_WATER_HEATER_ENTITY,
    CONF_PRICE_SENSOR_ENTITY,
    CONF_AWAY_MODE_ENTITY,
    CONF_BATH_MODE_ENTITY,
    CONF_EVALUATION_INTERVAL,
    CONF_NIGHT_WINDOW_START,
    CONF_NIGHT_WINDOW_END,
    CONF_HEATING_DURATION,
    CONF_LEGIONELLA_DAY,
    CONF_LEGIONELLA_DURATION,
    CONF_BATH_AUTO_OFF_TEMP,
    CONF_TEMPERATURE_PRESET,
    CONF_MIN_CYCLE_GAP,
    CONF_DYNAMIC_WINDOW_MODE,
    CONF_NIGHT_PREHEAT_TEMP,
    CONF_NIGHT_MINIMAL_TEMP,
    CONF_DAY_PREHEAT_TEMP,
    CONF_DAY_MINIMAL_TEMP,
    CONF_LEGIONELLA_TEMP,
    DEFAULT_PRICE_SENSOR,
    DEFAULT_EVALUATION_INTERVAL,
    DEFAULT_NIGHT_WINDOW_START,
    DEFAULT_NIGHT_WINDOW_END,
    DEFAULT_HEATING_DURATION,
    DEFAULT_LEGIONELLA_DAY,
    DEFAULT_LEGIONELLA_DURATION,
    DEFAULT_BATH_AUTO_OFF_TEMP,
    DEFAULT_TEMPERATURE_PRESET,
    DEFAULT_MIN_CYCLE_GAP,
    DEFAULT_DYNAMIC_WINDOW_MODE,
    PRESET_ECO,
    PRESET_COMFORT,
    PRESET_PERFORMANCE,
    PRESET_CUSTOM,
)

_LOGGER = logging.getLogger(__name__)


# Temperature presets
PRESETS = {
    PRESET_ECO: {
        "night_preheat": 52,
        "night_minimal": 48,
        "day_preheat": 55,
        "day_minimal": 35,
        "legionella": 60,
    },
    PRESET_COMFORT: {
        "night_preheat": 56,
        "night_minimal": 52,
        "day_preheat": 58,
        "day_minimal": 35,
        "legionella": 62,
    },
    PRESET_PERFORMANCE: {
        "night_preheat": 60,
        "night_minimal": 56,
        "day_preheat": 60,
        "day_minimal": 45,
        "legionella": 66,
    },
}

# Fixed temperatures
TEMP_NEGATIVE_PRICE = 70
TEMP_BATH = 58
TEMP_AWAY = 35
TEMP_IDLE = 35


class WaterHeaterSchedulerCoordinator(DataUpdateCoordinator):
    """Coordinator for Water Heater Scheduler."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._config = self._build_config()
        
        # State tracking
        self._last_cycle_end: Optional[datetime] = None
        self._current_program = "Idle"
        self._target_temp = TEMP_IDLE
        self._status = "Initializing"
        self._next_heating: Optional[datetime] = None

        interval = timedelta(
            minutes=self._config.get("evaluation_interval", DEFAULT_EVALUATION_INTERVAL)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=interval,
        )

    def _build_config(self) -> dict[str, Any]:
        """Build configuration from entry data and options."""
        # Merge data and options (options take precedence)
        config = {**self.entry.data, **self.entry.options}
        return config

    @property
    def water_heater_entity(self) -> str:
        """Return the water heater entity ID."""
        return self._config.get(CONF_WATER_HEATER_ENTITY, "")

    @property
    def price_sensor_entity(self) -> str:
        """Return the price sensor entity ID."""
        return self._config.get(CONF_PRICE_SENSOR_ENTITY, DEFAULT_PRICE_SENSOR)

    def _get_preset_temps(self) -> dict[str, int]:
        """Get temperatures based on preset or custom values."""
        preset = self._config.get(CONF_TEMPERATURE_PRESET, DEFAULT_TEMPERATURE_PRESET)
        
        if preset == PRESET_CUSTOM:
            return {
                "night_preheat": self._config.get(CONF_NIGHT_PREHEAT_TEMP) or 56,
                "night_minimal": self._config.get(CONF_NIGHT_MINIMAL_TEMP) or 52,
                "day_preheat": self._config.get(CONF_DAY_PREHEAT_TEMP) or 58,
                "day_minimal": self._config.get(CONF_DAY_MINIMAL_TEMP) or 35,
                "legionella": self._config.get(CONF_LEGIONELLA_TEMP) or 62,
            }
        
        return PRESETS.get(preset, PRESETS[PRESET_COMFORT])

    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)

    def _is_in_night_window(self, now: datetime) -> bool:
        """Check if current time is in night window."""
        current_time = now.time()
        start = self._parse_time(
            self._config.get(CONF_NIGHT_WINDOW_START, DEFAULT_NIGHT_WINDOW_START)
        )
        end = self._parse_time(
            self._config.get(CONF_NIGHT_WINDOW_END, DEFAULT_NIGHT_WINDOW_END)
        )
        
        # Handle overnight windows (e.g., 22:00 - 06:00)
        if start > end:
            return current_time >= start or current_time < end
        return start <= current_time < end

    def _is_legionella_day(self, now: datetime) -> bool:
        """Check if today is legionella day."""
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6,
        }
        target = day_map.get(
            self._config.get(CONF_LEGIONELLA_DAY, DEFAULT_LEGIONELLA_DAY), 5
        )
        return now.weekday() == target

    def _can_start_program(self, now: datetime) -> bool:
        """Check if enough time has passed since last cycle."""
        if self._last_cycle_end is None:
            return True
        
        gap_minutes = self._config.get(CONF_MIN_CYCLE_GAP, DEFAULT_MIN_CYCLE_GAP)
        elapsed = now - self._last_cycle_end
        return elapsed.total_seconds() >= gap_minutes * 60

    def _get_current_price(self) -> Optional[float]:
        """Get current electricity price from sensor."""
        state = self.hass.states.get(self.price_sensor_entity)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _is_away_mode(self) -> bool:
        """Check if away mode is active."""
        entity_id = self._config.get(CONF_AWAY_MODE_ENTITY)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _is_bath_mode(self) -> bool:
        """Check if bath mode is active."""
        entity_id = self._config.get(CONF_BATH_MODE_ENTITY)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and determine heating program."""
        now = datetime.now()
        temps = self._get_preset_temps()
        price = self._get_current_price()

        # Decision tree for program selection
        program = "Idle"
        target_temp = TEMP_IDLE
        status = "Standing by"

        # Priority 1: Away mode
        if self._is_away_mode():
            program = "Away"
            target_temp = TEMP_AWAY
            status = "Away mode active"

        # Priority 2: Negative price (free energy)
        elif price is not None and price <= 0:
            program = "NegativePrice"
            target_temp = TEMP_NEGATIVE_PRICE
            status = f"Free energy! Price: {price:.2f}"

        # Priority 3: Bath mode
        elif self._is_bath_mode():
            program = "Bath"
            target_temp = TEMP_BATH
            status = "Bath boost active"

        # Priority 4: Legionella protection
        elif self._is_legionella_day(now) and self._is_in_night_window(now):
            program = "Legionella"
            target_temp = temps["legionella"]
            status = "Legionella protection cycle"

        # Priority 5: Night window
        elif self._is_in_night_window(now):
            if self._can_start_program(now):
                program = "Night"
                target_temp = temps["night_preheat"]
                status = f"Night heating (price: {price:.2f})" if price else "Night heating"
            else:
                program = "Idle"
                target_temp = temps["night_minimal"]
                status = "Cycle gap - maintaining minimum"

        # Priority 6: Day window
        else:
            program = "Day"
            target_temp = temps["day_minimal"]
            status = "Day mode - conserving energy"

        # Apply temperature if changed
        if target_temp != self._target_temp:
            await self._set_temperature(target_temp)

        # Update state
        self._current_program = program
        self._target_temp = target_temp
        self._status = status

        return {
            "program": program,
            "target_temp": target_temp,
            "status": status,
            "price": price,
            "next_heating": self._next_heating,
        }

    async def _set_temperature(self, temperature: int) -> None:
        """Set water heater temperature."""
        try:
            await self.hass.services.async_call(
                "water_heater",
                "set_temperature",
                {
                    "entity_id": self.water_heater_entity,
                    "temperature": temperature,
                },
                blocking=True,
            )
            _LOGGER.info("Set water heater to %d°C", temperature)
        except Exception as err:
            _LOGGER.error("Failed to set temperature: %s", err)

    @property
    def current_program(self) -> str:
        """Return current heating program."""
        return self._current_program

    @property
    def target_temperature(self) -> int:
        """Return target temperature."""
        return self._target_temp

    @property
    def status(self) -> str:
        """Return current status text."""
        return self._status
