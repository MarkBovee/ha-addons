"""Constants for Water Heater Scheduler integration."""
from typing import Final

DOMAIN: Final = "water_heater_scheduler"

# Configuration keys
CONF_WATER_HEATER_ENTITY: Final = "water_heater_entity_id"
CONF_PRICE_SENSOR_ENTITY: Final = "price_sensor_entity_id"
CONF_AWAY_MODE_ENTITY: Final = "away_mode_entity_id"
CONF_BATH_MODE_ENTITY: Final = "bath_mode_entity_id"
CONF_EVALUATION_INTERVAL: Final = "evaluation_interval_minutes"
CONF_NIGHT_WINDOW_START: Final = "night_window_start"
CONF_NIGHT_WINDOW_END: Final = "night_window_end"
CONF_HEATING_DURATION: Final = "heating_duration_hours"
CONF_LEGIONELLA_DAY: Final = "legionella_day"
CONF_LEGIONELLA_DURATION: Final = "legionella_duration_hours"
CONF_BATH_AUTO_OFF_TEMP: Final = "bath_auto_off_temp"
CONF_TEMPERATURE_PRESET: Final = "temperature_preset"
CONF_MIN_CYCLE_GAP: Final = "min_cycle_gap_minutes"
CONF_DYNAMIC_WINDOW_MODE: Final = "dynamic_window_mode"

# Custom temperature overrides
CONF_NIGHT_PREHEAT_TEMP: Final = "night_preheat_temp"
CONF_NIGHT_MINIMAL_TEMP: Final = "night_minimal_temp"
CONF_DAY_PREHEAT_TEMP: Final = "day_preheat_temp"
CONF_DAY_MINIMAL_TEMP: Final = "day_minimal_temp"
CONF_LEGIONELLA_TEMP: Final = "legionella_temp"

# Default values
DEFAULT_PRICE_SENSOR: Final = "sensor.ep_price_import"
DEFAULT_EVALUATION_INTERVAL: Final = 5
DEFAULT_NIGHT_WINDOW_START: Final = "00:00"
DEFAULT_NIGHT_WINDOW_END: Final = "06:00"
DEFAULT_HEATING_DURATION: Final = 1
DEFAULT_LEGIONELLA_DAY: Final = "Saturday"
DEFAULT_LEGIONELLA_DURATION: Final = 3
DEFAULT_BATH_AUTO_OFF_TEMP: Final = 50
DEFAULT_TEMPERATURE_PRESET: Final = "comfort"
DEFAULT_MIN_CYCLE_GAP: Final = 50
DEFAULT_DYNAMIC_WINDOW_MODE: Final = False

# Temperature presets
PRESET_ECO: Final = "eco"
PRESET_COMFORT: Final = "comfort"
PRESET_PERFORMANCE: Final = "performance"
PRESET_CUSTOM: Final = "custom"

TEMPERATURE_PRESETS: Final = [PRESET_ECO, PRESET_COMFORT, PRESET_PERFORMANCE, PRESET_CUSTOM]

WEEKDAYS: Final = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Platforms
PLATFORMS: Final = ["sensor"]
