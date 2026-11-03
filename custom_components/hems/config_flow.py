"""Config flow: pick the Home Assistant entities per role, then tune settings in the options flow."""
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .settings_schema import CHOICES, EMPTYABLE, HA_SECTIONS, NUMBERS, OPEN_SECTIONS, kind
from .const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_EV, CONF_EV_CHARGING, CONF_EV_CURRENTS, CONF_EV_LIMIT,
                    CONF_EV_PLUGGED, CONF_EV_PROBLEM, CONF_EV_SOC, CONF_GRID, CONF_INVERTER, CONF_METER_CURRENTS, CONF_METER_EXPORTS,
                    CONF_PRICE_CURVE, CONF_PV, CONF_PV_EXTRA, CONF_SOC, DEFAULT_OPTIONS, DOMAIN, sell_quarters,
                    CONF_COMPARE_ACTION, CONF_LEGIONELLA_LAST, CONF_WATER_HEATER, CONF_AWAY, CONF_BATH, CONF_SPA, CONF_SPA_POWER, CONF_WATER_HEATER_ENERGY)

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
    CONF_WATER_HEATER_ENERGY: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
    CONF_AWAY: selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "input_boolean", "binary_sensor"])),
    CONF_BATH: selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_boolean", "switch"])),
    CONF_SPA: selector.EntitySelector(selector.EntitySelectorConfig(domain="climate")), CONF_SPA_POWER: _SENSOR,
    CONF_LEGIONELLA_LAST: _SENSOR, CONF_COMPARE_ACTION: _SENSOR}
_ROLES_OPTIONAL = tuple(ROLE_SELECTORS)
# The add-on's sensor.wh_last_legionella is a REST state: after every Home Assistant restart it is missing until the add-on posts it
# again, so this role is not refused for a missing entity (HEMS keeps its own record and only takes a later run from it).
_ROLES_CHECKED = tuple(r for r in _ROLES_OPTIONAL if r != CONF_LEGIONELLA_LAST)
_OPTIONAL_DATE = selector.TextSelector()          # an ISO date (2027-01-01) or empty; a date picker cannot be left empty
# The translation key of each choice's dropdown labels (strings.json `selector`).
_CHOICE_TRANSLATIONS = {"water_heater_legionella_weekday": "weekday", "spa_phase": "phase", "spa_control": "spa_control"}


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


def _field(key: str) -> Any:
    """The input for one setting: a number box, the weekday choice, the area text, or a switch."""
    match kind(key):
        case "number":
            return _number(*NUMBERS[key])
        case "choice":
            return selector.SelectSelector(selector.SelectSelectorConfig(options=list(CHOICES[key]), mode=selector.SelectSelectorMode.DROPDOWN,
                                                                         translation_key=_CHOICE_TRANSLATIONS[key]))
        case "date":
            return _OPTIONAL_DATE
        case "time" | "text":
            return str
        case _:
            return bool


def _key(key: str, current: dict[str, Any]) -> vol.Marker:
    """The form key for one setting: required with its current value as default, or optional for a setting that may be empty."""
    return vol.Optional(key) if key in EMPTYABLE else vol.Required(key, default=current[key])


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    """The settings form: one collapsible section per part. Every setting has its current value as default (the server fills a field left out) and
    as suggested value (what the screen shows: Home Assistant's screen starts a section from an empty object when the section itself has a default,
    and does not apply the defaults of the fields inside it)."""
    return vol.Schema({vol.Optional(name): section(vol.Schema({_key(key, current): _field(key) for key in keys}),
                                                   {"collapsed": name not in OPEN_SECTIONS})
                       for name, keys in HA_SECTIONS.items()})


def suggested_by_section(current: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The current settings grouped like the form, in the shape Home Assistant wants suggested values for sections."""
    return {name: {key: current[key] for key in keys} for name, keys in HA_SECTIONS.items()}


def flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """The options as stored (flat): the settings of every section, side by side. An emptyable setting missing from a submitted section is stored empty."""
    flat: dict[str, Any] = {}
    for name, part in user_input.items():
        flat.update({key: "" for key in HA_SECTIONS.get(name, ()) if key in EMPTYABLE})
        flat.update(part)
    return flat


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
            if all(self.hass.states.get(entity) is not None for role in _ROLES_CHECKED for entity in _as_list(user_input.get(role))):
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
        current = {**DEFAULT_OPTIONS, **self.config_entry.options, "max_sell_quarters": sell_quarters(self.config_entry.options)}
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **flatten_sections(user_input)})
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(_options_schema(current), suggested_by_section(current)))
