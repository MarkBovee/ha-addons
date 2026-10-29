"""Config flow: pick the Home Assistant entities per role, then tune settings in the options flow."""
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_EV, CONF_EV_CHARGING, CONF_EV_CURRENTS, CONF_EV_LIMIT,
                    CONF_EV_PLUGGED, CONF_EV_PROBLEM, CONF_EV_SOC, CONF_GRID, CONF_INVERTER, CONF_METER_CURRENTS, CONF_METER_EXPORTS,
                    CONF_PRICE_CURVE, CONF_PV, CONF_PV_EXTRA, CONF_SOC, DEFAULT_OPTIONS, DOMAIN,
                    CONF_COMPARE_ACTION, CONF_LEGIONELLA_LAST, CONF_WATER_HEATER, CONF_AWAY, CONF_BATH)

_ROLES_REQUIRED = (CONF_SOC, CONF_BATTERY_POWER, CONF_PV, CONF_GRID)
_ROLES_INITIAL = (CONF_INVERTER, CONF_EV, CONF_PRICE_CURVE)         # the optional roles the first setup form asks for
_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_BINARY = selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor"))
_NUMBER = selector.EntitySelector(selector.EntitySelectorConfig(domain="number"))
_SENSORS = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True))
# Every optional role and the picker for it, in the order of the reconfigure form. A role left empty means it is not used.
ROLE_SELECTORS: dict[str, Any] = {
    CONF_INVERTER: _SENSOR, CONF_EV: _SENSOR, CONF_PRICE_CURVE: _SENSOR, CONF_PV_EXTRA: _SENSORS,
    CONF_EV_PLUGGED: _BINARY, CONF_EV_CHARGING: _BINARY, CONF_EV_PROBLEM: _BINARY, CONF_EV_SOC: _SENSOR, CONF_EV_LIMIT: _NUMBER,
    **{role: _SENSOR for role in (*CONF_EV_CURRENTS, *CONF_METER_CURRENTS, *CONF_METER_EXPORTS)},
    CONF_WATER_HEATER: selector.EntitySelector(selector.EntitySelectorConfig(domain=["water_heater", "sensor"])),
    CONF_AWAY: selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "input_boolean", "binary_sensor"])),
    CONF_BATH: selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_boolean", "switch"])),
    CONF_LEGIONELLA_LAST: _SENSOR, CONF_COMPARE_ACTION: _SENSOR}
_ROLES_OPTIONAL = tuple(ROLE_SELECTORS)
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_OPTIONAL_DATE = selector.TextSelector()          # an ISO date (2027-01-01) or empty; a date picker cannot be left empty
_WEEKDAY = selector.SelectSelector(selector.SelectSelectorConfig(
    options=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], mode=selector.SelectSelectorMode.DROPDOWN, translation_key="weekday"))


def _as_list(value: Any) -> list[str]:
    """A role value as a list of entity ids: one id, several ids or nothing."""
    return [] if not value else [value] if isinstance(value, str) else list(value)


def _optional_roles_schema(defaults: dict[str, Any]) -> dict[Any, Any]:
    """Entity pickers for the optional roles only; a cleared picker means the role is not used."""
    return {vol.Optional(role, description={"suggested_value": defaults.get(role)}): picker for role, picker in ROLE_SELECTORS.items()}


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Entity pickers for every role; optional roles stay optional, sign convention is a plain switch."""
    fields: dict[Any, Any] = {}
    for role in _ROLES_REQUIRED:
        fields[vol.Required(role, default=defaults.get(role, vol.UNDEFINED))] = _SENSOR
    fields[vol.Required(CONF_BATTERY_POSITIVE_DISCHARGING, default=defaults.get(CONF_BATTERY_POSITIVE_DISCHARGING, True))] = bool
    for role in _ROLES_INITIAL:
        fields[vol.Optional(role, description={"suggested_value": defaults.get(role)})] = ROLE_SELECTORS[role]
    return vol.Schema(fields)


MIN_SELECTOR_STEP = 0.001         # Home Assistant refuses a smaller step and the whole form fails to open


def _number(minimum: float, maximum: float, step: float) -> selector.NumberSelector:
    """A boxed number input with unit-less bounds; units are explained in the translations.

    A step finer than Home Assistant allows becomes "any": prices and taxes need five decimals, and a rejected step
    makes the settings form raise instead of open."""
    return selector.NumberSelector(selector.NumberSelectorConfig(min=minimum, max=maximum, step=step if step >= MIN_SELECTOR_STEP else "any",
                                                                 mode=selector.NumberSelectorMode.BOX))


# The settings form, in the parts of the HEMS plan: the modules (battery, water heater, later EV) and the base components every module shares
# (prices, forecasts). Each part is a collapsible section in this order on screen; a module with an on/off switch has it as its first setting.
# The battery is open, the rest is folded away.
SECTIONS: dict[str, tuple[str, ...]] = {
    "module_battery": ("capacity_kwh", "max_power_kw", "hard_min_soc_pct", "reserve_soc_pct", "reserve_max_soc_pct", "reserve_load_factor", "round_trip_eff", "min_profit_margin", "hold_cost_kwh_h"),
    "module_water_heater": ("water_heater_enabled", "water_heater_energy_kwh", "water_heater_hours", "water_heater_night_energy_kwh",
                     "water_heater_legionella_energy_kwh", "water_heater_legionella_hours", "water_heater_legionella_weekday",
                     "water_heater_legionella_temp_c", "water_heater_legionella_min_c",
                     "water_heater_night_preheat_c", "water_heater_night_minimal_c", "water_heater_day_preheat_c", "water_heater_idle_c", "water_heater_low_price_c", "water_heater_negative_price_c", "water_heater_bath_c", "water_heater_away_c", "water_heater_bath_off_c", "water_heater_cycle_gap_min"),
    "module_ev": ("ev_enabled", "ev_capacity_kwh", "ev_charge_efficiency", "ev_target_required_pct", "ev_target_max_pct", "ev_max_price", "ev_solar_only",
                  "ev_min_current_a", "ev_max_current_a", "ev_min_on_minutes", "ev_min_off_minutes", "ev_deadline_monday", "ev_deadline_tuesday",
                  "ev_deadline_wednesday", "ev_deadline_thursday", "ev_deadline_friday", "ev_deadline_saturday", "ev_deadline_sunday"),
    "base_prices": ("nordpool_enabled", "delivery_area", "import_vat_multiplier", "import_markup", "import_energy_tax", "export_vat_multiplier",
               "export_bonus_pct", "export_fixed_bonus", "export_energy_tax", "salderen", "salderen_until", "bonus_only_daylight", "bonus_only_positive_price"),
    "base_forecast": ("weather_enabled", "pv_gain_w_per_wm2", "pv_max_ac_w"),
    "base_grid": ("grid_limit_a", "grid_margin_a"),
    "logging": ("trace_full_plan",),
}
OPEN_SECTIONS = ("module_battery",)
NUMBERS = {"capacity_kwh": (1, 100, 0.1), "max_power_kw": (0.5, 30, 0.1), "hard_min_soc_pct": (0, 50, 1), "reserve_soc_pct": (0, 100, 1), "reserve_max_soc_pct": (0, 100, 1), "reserve_load_factor": (1, 3, 0.05),
           "round_trip_eff": (0.5, 1.0, 0.01), "min_profit_margin": (0, 1, 0.01), "hold_cost_kwh_h": (0, 0.05, 0.0005), "pv_gain_w_per_wm2": (0, 30, 0.1),
           "pv_max_ac_w": (0, 30000, 100), "import_vat_multiplier": (1, 2, 0.01), "import_markup": (-0.5, 0.5, 0.0001), "import_energy_tax": (0, 1, 0.00001),
           "export_vat_multiplier": (1, 2, 0.01), "export_bonus_pct": (0, 1, 0.01), "export_fixed_bonus": (-0.5, 0.5, 0.0001),
           "export_energy_tax": (0, 1, 0.00001), "water_heater_energy_kwh": (0, 15, 0.1), "water_heater_hours": (1, 6, 1),
           "water_heater_night_energy_kwh": (0, 15, 0.1), "water_heater_legionella_energy_kwh": (0, 15, 0.1), "water_heater_legionella_hours": (1, 6, 1),
           "water_heater_legionella_temp_c": (55, 75, 1), "water_heater_legionella_min_c": (50, 70, 1),
           "water_heater_night_preheat_c": (30, 75, 1), "water_heater_night_minimal_c": (30, 75, 1), "water_heater_day_preheat_c": (30, 75, 1), "water_heater_idle_c": (30, 75, 1), "water_heater_low_price_c": (30, 75, 1), "water_heater_negative_price_c": (30, 75, 1), "water_heater_bath_c": (30, 75, 1), "water_heater_away_c": (30, 75, 1), "water_heater_bath_off_c": (30, 75, 1), "water_heater_cycle_gap_min": (10, 180, 5),
           "ev_capacity_kwh": (10, 200, 0.1), "ev_charge_efficiency": (0.5, 1, 0.01), "ev_target_required_pct": (0, 100, 1), "ev_target_max_pct": (0, 100, 1),
           "ev_max_price": (-1, 2, 0.01), "ev_min_current_a": (1, 32, 1), "ev_max_current_a": (6, 32, 1), "ev_min_on_minutes": (0, 120, 1),
           "ev_min_off_minutes": (0, 120, 1), "grid_limit_a": (6, 80, 1), "grid_margin_a": (0, 10, 0.5)}


def _field(key: str) -> Any:
    """The input for one setting: a number box, the weekday choice, the area text, or a switch."""
    if key in NUMBERS:
        return _number(*NUMBERS[key])
    return {"water_heater_legionella_weekday": _WEEKDAY, "delivery_area": str, "salderen_until": _OPTIONAL_DATE, **{f"ev_deadline_{d}": str for d in _DAYS}}.get(key, bool)


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    """The settings form: one collapsible section per part. Every setting has its current value as default (the server fills a field left out) and
    as suggested value (what the screen shows: Home Assistant's screen starts a section from an empty object when the section itself has a default,
    and does not apply the defaults of the fields inside it)."""
    return vol.Schema({vol.Optional(name): section(vol.Schema({vol.Required(key, default=current[key]): _field(key) for key in keys}),
                                                   {"collapsed": name not in OPEN_SECTIONS})
                       for name, keys in SECTIONS.items()})


def suggested_by_section(current: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The current settings grouped like the form, in the shape Home Assistant wants suggested values for sections."""
    return {name: {key: current[key] for key in keys} for name, keys in SECTIONS.items()}


def flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """The options as stored (flat): the settings of every section, side by side."""
    return {key: value for part in user_input.values() for key, value in part.items()}


class HemsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One HEMS instance per Home Assistant."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose the entities; every chosen entity must exist right now."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            missing = [r for r in (*_ROLES_REQUIRED, *(r for r in _ROLES_INITIAL if user_input.get(r))) if self.hass.states.get(user_input[r]) is None]
            if not missing:
                return self.async_create_entry(title="HEMS", data=user_input, options=dict(DEFAULT_OPTIONS))
            errors["base"] = "entity_not_found"
        return self.async_show_form(step_id="user", data_schema=_user_schema(user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the optional roles (inverter output, EV power, price curve) of the existing entry; the required roles stay as they are.

        The entry is saved and reloaded in one go; a role left empty is removed, so the EV or inverter can be switched off again."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if all(self.hass.states.get(entity) is not None for role in _ROLES_OPTIONAL for entity in _as_list(user_input.get(role))):
                kept = {key: value for key, value in entry.data.items() if key not in _ROLES_OPTIONAL}
                return self.async_update_reload_and_abort(entry, data={**kept, **{r: user_input[r] for r in _ROLES_OPTIONAL if user_input.get(r)}})
            errors["base"] = "entity_not_found"
        schema = vol.Schema(_optional_roles_schema(user_input or dict(entry.data)))
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """Settings form; saving reloads the entry so the planner picks them up."""
        return HemsOptionsFlow()


class HemsOptionsFlow(OptionsFlowWithReload):
    """Edit battery, forecast and price-component settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the current settings; store what was submitted on top of what was set (a section that is not submitted keeps its values)."""
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **flatten_sections(user_input)})
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(_options_schema(current), suggested_by_section(current)))
