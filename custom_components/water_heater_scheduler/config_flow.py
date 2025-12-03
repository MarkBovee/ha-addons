"""Config flow for Water Heater Scheduler integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
    TEMPERATURE_PRESETS,
    WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)


def get_basic_schema(hass: HomeAssistant) -> vol.Schema:
    """Return schema for basic configuration step."""
    return vol.Schema(
        {
            vol.Required(CONF_WATER_HEATER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=WATER_HEATER_DOMAIN)
            ),
            vol.Optional(
                CONF_PRICE_SENSOR_ENTITY, default=DEFAULT_PRICE_SENSOR
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(
                CONF_TEMPERATURE_PRESET, default=DEFAULT_TEMPERATURE_PRESET
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TEMPERATURE_PRESETS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="temperature_preset",
                )
            ),
            vol.Optional(
                CONF_DYNAMIC_WINDOW_MODE, default=DEFAULT_DYNAMIC_WINDOW_MODE
            ): selector.BooleanSelector(),
        }
    )


def get_advanced_schema(hass: HomeAssistant) -> vol.Schema:
    """Return schema for advanced configuration step."""
    return vol.Schema(
        {
            vol.Optional(CONF_AWAY_MODE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["switch", "input_boolean"],
                )
            ),
            vol.Optional(CONF_BATH_MODE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["switch", "input_boolean"],
                )
            ),
            vol.Optional(
                CONF_NIGHT_WINDOW_START, default=DEFAULT_NIGHT_WINDOW_START
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_NIGHT_WINDOW_END, default=DEFAULT_NIGHT_WINDOW_END
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_HEATING_DURATION, default=DEFAULT_HEATING_DURATION
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=4, step=1, unit_of_measurement="hours"
                )
            ),
            vol.Optional(
                CONF_LEGIONELLA_DAY, default=DEFAULT_LEGIONELLA_DAY
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=WEEKDAYS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_LEGIONELLA_DURATION, default=DEFAULT_LEGIONELLA_DURATION
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=6, step=1, unit_of_measurement="hours"
                )
            ),
            vol.Optional(
                CONF_BATH_AUTO_OFF_TEMP, default=DEFAULT_BATH_AUTO_OFF_TEMP
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=40, max=60, step=1, unit_of_measurement="°C"
                )
            ),
            vol.Optional(
                CONF_MIN_CYCLE_GAP, default=DEFAULT_MIN_CYCLE_GAP
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10, max=180, step=5, unit_of_measurement="minutes"
                )
            ),
            vol.Optional(
                CONF_EVALUATION_INTERVAL, default=DEFAULT_EVALUATION_INTERVAL
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=60, step=1, unit_of_measurement="minutes"
                )
            ),
        }
    )


def get_custom_temps_schema() -> vol.Schema:
    """Return schema for custom temperature overrides."""
    return vol.Schema(
        {
            vol.Optional(CONF_NIGHT_PREHEAT_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=45, max=65, step=1, unit_of_measurement="°C"
                )
            ),
            vol.Optional(CONF_NIGHT_MINIMAL_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=40, max=60, step=1, unit_of_measurement="°C"
                )
            ),
            vol.Optional(CONF_DAY_PREHEAT_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=50, max=70, step=1, unit_of_measurement="°C"
                )
            ),
            vol.Optional(CONF_DAY_MINIMAL_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=30, max=50, step=1, unit_of_measurement="°C"
                )
            ),
            vol.Optional(CONF_LEGIONELLA_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=60, max=70, step=1, unit_of_measurement="°C"
                )
            ),
        }
    )


class WaterHeaterSchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Water Heater Scheduler."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - basic configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if already configured
            water_heater = user_input[CONF_WATER_HEATER_ENTITY]
            await self.async_set_unique_id(water_heater)
            self._abort_if_unique_id_configured()

            # Validate water heater exists
            if not self.hass.states.get(water_heater):
                errors[CONF_WATER_HEATER_ENTITY] = "invalid_water_heater"
            
            # Validate price sensor if provided
            price_sensor = user_input.get(CONF_PRICE_SENSOR_ENTITY)
            if price_sensor and not self.hass.states.get(price_sensor):
                errors[CONF_PRICE_SENSOR_ENTITY] = "invalid_price_sensor"

            if not errors:
                self._data.update(user_input)
                return await self.async_step_advanced()

        return self.async_show_form(
            step_id="user",
            data_schema=get_basic_schema(self.hass),
            errors=errors,
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle advanced configuration step."""
        if user_input is not None:
            self._data.update(user_input)
            
            # Check if custom preset - show custom temps step
            if self._data.get(CONF_TEMPERATURE_PRESET) == "custom":
                return await self.async_step_custom_temps()
            
            return self._create_entry()

        return self.async_show_form(
            step_id="advanced",
            data_schema=get_advanced_schema(self.hass),
        )

    async def async_step_custom_temps(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle custom temperature configuration step."""
        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        return self.async_show_form(
            step_id="custom_temps",
            data_schema=get_custom_temps_schema(),
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        water_heater = self._data[CONF_WATER_HEATER_ENTITY]
        # Use friendly name if available
        state = self.hass.states.get(water_heater)
        title = state.name if state else water_heater
        
        return self.async_create_entry(
            title=title,
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WaterHeaterSchedulerOptionsFlow(config_entry)


class WaterHeaterSchedulerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Water Heater Scheduler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - basic settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_advanced()

        # Pre-fill with existing options/data
        current = {**self._config_entry.data, **self._config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PRICE_SENSOR_ENTITY,
                        default=current.get(CONF_PRICE_SENSOR_ENTITY, DEFAULT_PRICE_SENSOR),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                    ),
                    vol.Optional(
                        CONF_TEMPERATURE_PRESET,
                        default=current.get(CONF_TEMPERATURE_PRESET, DEFAULT_TEMPERATURE_PRESET),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=TEMPERATURE_PRESETS,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_DYNAMIC_WINDOW_MODE,
                        default=current.get(CONF_DYNAMIC_WINDOW_MODE, DEFAULT_DYNAMIC_WINDOW_MODE),
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage advanced options."""
        if user_input is not None:
            self._data.update(user_input)
            
            # Check if custom preset
            if self._data.get(CONF_TEMPERATURE_PRESET) == "custom":
                return await self.async_step_custom_temps()
            
            return self.async_create_entry(title="", data=self._data)

        current = {**self._config_entry.data, **self._config_entry.options}

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_AWAY_MODE_ENTITY,
                        description={"suggested_value": current.get(CONF_AWAY_MODE_ENTITY)},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                    ),
                    vol.Optional(
                        CONF_BATH_MODE_ENTITY,
                        description={"suggested_value": current.get(CONF_BATH_MODE_ENTITY)},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                    ),
                    vol.Optional(
                        CONF_NIGHT_WINDOW_START,
                        default=current.get(CONF_NIGHT_WINDOW_START, DEFAULT_NIGHT_WINDOW_START),
                    ): selector.TimeSelector(),
                    vol.Optional(
                        CONF_NIGHT_WINDOW_END,
                        default=current.get(CONF_NIGHT_WINDOW_END, DEFAULT_NIGHT_WINDOW_END),
                    ): selector.TimeSelector(),
                    vol.Optional(
                        CONF_HEATING_DURATION,
                        default=current.get(CONF_HEATING_DURATION, DEFAULT_HEATING_DURATION),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=4, step=1, unit_of_measurement="hours")
                    ),
                    vol.Optional(
                        CONF_LEGIONELLA_DAY,
                        default=current.get(CONF_LEGIONELLA_DAY, DEFAULT_LEGIONELLA_DAY),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=WEEKDAYS, mode=selector.SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Optional(
                        CONF_LEGIONELLA_DURATION,
                        default=current.get(CONF_LEGIONELLA_DURATION, DEFAULT_LEGIONELLA_DURATION),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=6, step=1, unit_of_measurement="hours")
                    ),
                    vol.Optional(
                        CONF_BATH_AUTO_OFF_TEMP,
                        default=current.get(CONF_BATH_AUTO_OFF_TEMP, DEFAULT_BATH_AUTO_OFF_TEMP),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=40, max=60, step=1, unit_of_measurement="°C")
                    ),
                    vol.Optional(
                        CONF_MIN_CYCLE_GAP,
                        default=current.get(CONF_MIN_CYCLE_GAP, DEFAULT_MIN_CYCLE_GAP),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=10, max=180, step=5, unit_of_measurement="minutes")
                    ),
                    vol.Optional(
                        CONF_EVALUATION_INTERVAL,
                        default=current.get(CONF_EVALUATION_INTERVAL, DEFAULT_EVALUATION_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="minutes")
                    ),
                }
            ),
        )

    async def async_step_custom_temps(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage custom temperature options."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)

        current = {**self._config_entry.data, **self._config_entry.options}

        return self.async_show_form(
            step_id="custom_temps",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NIGHT_PREHEAT_TEMP,
                        description={"suggested_value": current.get(CONF_NIGHT_PREHEAT_TEMP)},
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=45, max=65, step=1, unit_of_measurement="°C")
                    ),
                    vol.Optional(
                        CONF_NIGHT_MINIMAL_TEMP,
                        description={"suggested_value": current.get(CONF_NIGHT_MINIMAL_TEMP)},
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=40, max=60, step=1, unit_of_measurement="°C")
                    ),
                    vol.Optional(
                        CONF_DAY_PREHEAT_TEMP,
                        description={"suggested_value": current.get(CONF_DAY_PREHEAT_TEMP)},
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=50, max=70, step=1, unit_of_measurement="°C")
                    ),
                    vol.Optional(
                        CONF_DAY_MINIMAL_TEMP,
                        description={"suggested_value": current.get(CONF_DAY_MINIMAL_TEMP)},
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=30, max=50, step=1, unit_of_measurement="°C")
                    ),
                    vol.Optional(
                        CONF_LEGIONELLA_TEMP,
                        description={"suggested_value": current.get(CONF_LEGIONELLA_TEMP)},
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=60, max=70, step=1, unit_of_measurement="°C")
                    ),
                }
            ),
        )
