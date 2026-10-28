"""Websocket commands for the HEMS panel: the dashboard payload as a subscription, and the settings and roles in force.

Read-only: nothing here changes the plan or a device. The EV override stays an ordinary switch entity, so the panel
switches it with the normal `switch.turn_on` service and the change shows in the logbook like any other."""
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DEFAULT_OPTIONS, DOMAIN

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


@websocket_api.websocket_command({vol.Required("type"): "hems/settings"})
@callback
def ws_settings(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The options in force (defaults filled in), the entity roles and the config entry id (for the 'Configure' link)."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_found", "HEMS is not set up")
        return
    entry = entries[0]
    connection.send_result(msg["id"], {"entry_id": entry.entry_id, "options": {**DEFAULT_OPTIONS, **entry.options}, "roles": dict(entry.data),
                                       "loaded": entry.state is ConfigEntryState.LOADED})
