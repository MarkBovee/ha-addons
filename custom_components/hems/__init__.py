"""HEMS: modular home energy management for Home Assistant. This version plans in dry-run only (no device writes)."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event, async_track_utc_time_change

from .const import CONF_SOC, PLATFORMS
from .coordinator import HemsCoordinator

type HemsConfigEntry = ConfigEntry[HemsCoordinator]

PLAN_SECONDS = 20          # a few seconds past the quarter so sensors that update on the boundary are already fresh


def _show_info_logs() -> None:
    """Make the integration's INFO lines visible unless the user's logger configuration already names it.

    Home Assistant's usual `logger: default: warning` hides every INFO line of a custom integration, and the decision
    log is the point of HEMS. A level set in configuration.yaml (or by the logger.set_level service) is left alone."""
    package = logging.getLogger(__package__)
    if package.level == logging.NOTSET:
        package.setLevel(logging.INFO)


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry) -> bool:
    """Create the coordinator, plan once now, then every quarter."""
    _show_info_logs()
    coordinator = HemsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    async def _on_quarter(_now) -> None:
        """Quarter boundary: replan."""
        await coordinator.async_request_refresh()

    async def _on_soc_update(_event) -> None:
        """The SoC moved inside the quarter: let the executor check the plan's command against it."""
        await coordinator.async_recheck_execution()

    entry.async_on_unload(async_track_utc_time_change(hass, _on_quarter, minute=(0, 15, 30, 45), second=PLAN_SECONDS))
    entry.async_on_unload(async_track_state_change_event(hass, [entry.data[CONF_SOC]], _on_soc_update))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HemsConfigEntry) -> bool:
    """Unload the sensors; the quarter listener goes with the entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
