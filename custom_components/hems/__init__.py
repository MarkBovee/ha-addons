"""HEMS: modular home energy management for Home Assistant. This version plans in dry-run only (no device writes)."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_utc_time_change

from .const import PLATFORMS
from .coordinator import HemsCoordinator

type HemsConfigEntry = ConfigEntry[HemsCoordinator]

PLAN_SECONDS = 20          # a few seconds past the quarter so sensors that update on the boundary are already fresh


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry) -> bool:
    """Create the coordinator, plan once now, then every quarter."""
    coordinator = HemsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    async def _on_quarter(_now) -> None:
        """Quarter boundary: replan."""
        await coordinator.async_request_refresh()

    entry.async_on_unload(async_track_utc_time_change(hass, _on_quarter, minute=(0, 15, 30, 45), second=PLAN_SECONDS))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HemsConfigEntry) -> bool:
    """Unload the sensors; the quarter listener goes with the entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
