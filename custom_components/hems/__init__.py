"""HEMS: modular home energy management for Home Assistant. This version plans in dry-run only (no device writes)."""
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval, async_track_utc_time_change
from datetime import timedelta
from homeassistant.helpers.typing import ConfigType

from .const import BUILD_FILE, CONF_SOC, DOMAIN, PLATFORMS, SAMPLE_SECONDS
from .services import async_register_services
from .coordinator import HemsCoordinator
from .panel import async_register_panel, async_unregister_panel
from .websocket import SIGNAL_UPDATE, async_register_commands

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type HemsConfigEntry = ConfigEntry[HemsCoordinator]

_LOGGER = logging.getLogger(__name__)
PLAN_SECONDS = 20          # a few seconds past the quarter so sensors that update on the boundary are already fresh


def _show_info_logs() -> None:
    """Make the integration's INFO lines visible unless the user's logger configuration already names it.

    Home Assistant's usual `logger: default: warning` hides every INFO line of a custom integration, and the decision
    log is the point of HEMS. A level set in configuration.yaml (or by the logger.set_level service) is left alone."""
    package = logging.getLogger(__package__)
    if package.level == logging.NOTSET:
        package.setLevel(logging.INFO)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the panel's websocket commands once per run."""
    async_register_commands(hass)
    async_register_services(hass)
    return True


def read_build() -> str:
    """The commit this code was deployed from (hems/deploy.py writes it next to the code); 'unknown' for a copy that was not deployed by it."""
    try:
        return (Path(__file__).with_name(BUILD_FILE)).read_text().strip() or "unknown"
    except OSError:
        return "unknown"


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry) -> bool:
    """Create the coordinator, plan once now, then every quarter."""
    _show_info_logs()
    coordinator = HemsCoordinator(hass, entry)
    coordinator.build = await hass.async_add_executor_job(read_build)
    await coordinator.async_load_state()
    _LOGGER.info("HEMS build %s", coordinator.build)
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
    entry.async_on_unload(async_track_time_interval(hass, coordinator.async_sample, timedelta(seconds=SAMPLE_SECONDS)))
    entry.async_on_unload(coordinator.async_add_listener(lambda: async_dispatcher_send(hass, SIGNAL_UPDATE)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_panel(hass)
    async_dispatcher_send(hass, SIGNAL_UPDATE)      # a panel that was open during a reload gets the new entry's data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HemsConfigEntry) -> bool:
    """Unload the sensors; the quarter listener goes with the entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_now()
        async_unregister_panel(hass)
    return unloaded
