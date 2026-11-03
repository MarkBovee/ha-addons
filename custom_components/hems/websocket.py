"""Websocket commands for the HEMS panel: the dashboard payload as a subscription, and the settings and roles in force.

Only `hems/settings/update` writes, and only HEMS's own planning settings (the panel's share in settings_schema), never a device. The EV override stays an ordinary switch entity, so the panel
switches it with the normal `switch.turn_on` service and the change shows in the logbook like any other."""
import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DEFAULT_OPTIONS, DOMAIN, sell_quarters
from .settings_schema import LEARNED_KEYS, panel_sections, validate_panel_changes

_LOGGER = logging.getLogger(__name__)
_LABELS_KEY = f"{DOMAIN}_setting_labels"

SIGNAL_UPDATE = f"{DOMAIN}_dashboard_update"


def _coordinator(hass: HomeAssistant):
    """The coordinator of the loaded HEMS entry (HEMS allows one), or None."""
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return entry.runtime_data
    return None


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the commands once per Home Assistant run."""
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_settings)
    websocket_api.async_register_command(hass, ws_settings_update)


@websocket_api.websocket_command({vol.Required("type"): "hems/subscribe"})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Send the payload now and after every cycle, SoC re-check or override change; an empty payload means HEMS is not loaded."""

    @callback
    def send() -> None:
        coordinator = _coordinator(hass)
        payload = coordinator.dashboard_payload() if coordinator else None
        connection.send_message(websocket_api.event_message(msg["id"], {"loaded": coordinator is not None, "payload": payload}))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL_UPDATE, send)
    connection.send_result(msg["id"])
    send()


def _read_labels() -> dict[str, Any]:
    """Section names and setting labels from the English translation, the same words the Home Assistant form shows."""
    data = json.loads(Path(__file__).with_name("translations").joinpath("en.json").read_text(encoding="utf-8"))
    sections = data["options"]["step"]["init"]["sections"]
    return {"sections": {name: part.get("name", name) for name, part in sections.items()},
            "settings": {key: label for part in sections.values() for key, label in part.get("data", {}).items()}}


async def _labels(hass: HomeAssistant) -> dict[str, Any]:
    """The labels, read once per run (a file read off the event loop)."""
    if _LABELS_KEY not in hass.data:
        hass.data[_LABELS_KEY] = await hass.async_add_executor_job(_read_labels)
    return hass.data[_LABELS_KEY]


def _options_in_force(entry) -> dict[str, Any]:
    """The stored options with defaults filled in (and the old sell-hours key read as quarters)."""
    return {**DEFAULT_OPTIONS, **entry.options, "max_sell_quarters": sell_quarters(entry.options)}


def _learned(hass: HomeAssistant) -> dict[str, Any]:
    """The learned values the panel shows next to their configured value (read-only), from the latest cycle."""
    coordinator = _coordinator(hass)
    snap = coordinator and coordinator.data
    learned = (snap and snap.output.trace.get("learned")) or {}
    return {key: learned[key] for key in LEARNED_KEYS if key in learned}


@websocket_api.websocket_command({vol.Required("type"): "hems/settings"})
@websocket_api.async_response
async def ws_settings(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The options in force (defaults filled in), the entity roles, the config entry id (for the 'Configure' link), the panel's editable
    settings with labels, and the learned values."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_found", "HEMS is not set up")
        return
    entry = entries[0]
    connection.send_result(msg["id"], {"entry_id": entry.entry_id, "options": _options_in_force(entry), "roles": dict(entry.data),
                                       "loaded": entry.state is ConfigEntryState.LOADED, "editable": panel_sections(),
                                       "labels": await _labels(hass), "learned": _learned(hass)})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "hems/settings/update", vol.Required("changes"): {str: vol.Any(bool, int, float, str)}})
@websocket_api.async_response
async def ws_settings_update(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Store planning settings from the panel and replan at once, without a reload (decided 3 Nov 2026).

    Every value is checked against its bounds and the rules between settings; with any error nothing is stored and the errors come back
    per key, so the panel can show them next to the input. Settings are read fresh every cycle, so the refresh below is all it takes."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_found", "HEMS is not set up")
        return
    entry = entries[0]
    current = _options_in_force(entry)
    converted, errors = validate_panel_changes(current, msg["changes"])
    if errors:
        connection.send_result(msg["id"], {"ok": False, "errors": errors})
        return
    changed = {key: value for key, value in converted.items() if current.get(key) != value}
    if changed:
        hass.config_entries.async_update_entry(entry, options={**entry.options, **changed})
        _LOGGER.info("HEMS settings changed in the panel: %s", ", ".join(f"{k}={v}" for k, v in sorted(changed.items())))
        coordinator = _coordinator(hass)
        if coordinator:
            await coordinator.async_refresh()           # replan now; the settings event logs the new hash
    connection.send_result(msg["id"], {"ok": True, "changed": sorted(changed), "options": _options_in_force(entry)})
