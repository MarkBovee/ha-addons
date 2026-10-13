"""Config flow: pick the Home Assistant entities per role, then tune settings in the options flow."""
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_EV, CONF_GRID, CONF_INVERTER, CONF_PRICE_CURVE,
                    CONF_PV, CONF_SOC, DEFAULT_OPTIONS, DOMAIN)

_ROLES_REQUIRED = (CONF_SOC, CONF_BATTERY_POWER, CONF_PV, CONF_GRID)
_ROLES_OPTIONAL = (CONF_INVERTER, CONF_EV, CONF_PRICE_CURVE)
_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Entity pickers for every role; optional roles stay optional, sign convention is a plain switch."""
    fields: dict[Any, Any] = {}
    for role in _ROLES_REQUIRED:
        fields[vol.Required(role, default=defaults.get(role, vol.UNDEFINED))] = _SENSOR
    fields[vol.Required(CONF_BATTERY_POSITIVE_DISCHARGING, default=defaults.get(CONF_BATTERY_POSITIVE_DISCHARGING, True))] = bool
    for role in _ROLES_OPTIONAL:
        fields[vol.Optional(role, description={"suggested_value": defaults.get(role)})] = _SENSOR
    return vol.Schema(fields)


def _number(minimum: float, maximum: float, step: float) -> selector.NumberSelector:
    """A boxed number input with unit-less bounds; units are explained in the translations."""
    return selector.NumberSelector(selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX))


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    """All settings with their current values; the bonus switches and netting are plain booleans."""
    numbers = {"capacity_kwh": (1, 100, 0.1), "max_power_kw": (0.5, 30, 0.1), "hard_min_soc_pct": (0, 50, 1), "reserve_soc_pct": (0, 100, 1),
               "round_trip_eff": (0.5, 1.0, 0.01), "min_profit_margin": (0, 1, 0.01), "hold_cost_kwh_h": (0, 0.05, 0.0005), "pv_gain_w_per_wm2": (0, 30, 0.1), "pv_max_ac_w": (0, 30000, 100),
               "import_vat_multiplier": (1, 2, 0.01), "import_markup": (-0.5, 0.5, 0.0001), "import_energy_tax": (0, 1, 0.00001),
               "export_vat_multiplier": (1, 2, 0.01), "export_bonus_pct": (0, 1, 0.01), "export_fixed_bonus": (-0.5, 0.5, 0.0001),
               "export_energy_tax": (0, 1, 0.00001)}
    fields: dict[Any, Any] = {vol.Required(k, default=current[k]): _number(*bounds) for k, bounds in numbers.items()}
    fields[vol.Required("delivery_area", default=current["delivery_area"])] = str
    for flag in ("weather_enabled", "nordpool_enabled", "trace_full_plan", "salderen", "bonus_only_daylight", "bonus_only_positive_price"):
        fields[vol.Required(flag, default=current[flag])] = bool
    return vol.Schema(fields)


class HemsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One HEMS instance per Home Assistant."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose the entities; every chosen entity must exist right now."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            missing = [r for r in (*_ROLES_REQUIRED, *(r for r in _ROLES_OPTIONAL if user_input.get(r))) if self.hass.states.get(user_input[r]) is None]
            if not missing:
                return self.async_create_entry(title="HEMS", data=user_input, options=dict(DEFAULT_OPTIONS))
            errors["base"] = "entity_not_found"
        return self.async_show_form(step_id="user", data_schema=_user_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """Settings form; saving reloads the entry so the planner picks them up."""
        return HemsOptionsFlow()


class HemsOptionsFlow(OptionsFlowWithReload):
    """Edit battery, forecast and price-component settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the current settings; store them as given."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_options_schema({**DEFAULT_OPTIONS, **self.config_entry.options}))
