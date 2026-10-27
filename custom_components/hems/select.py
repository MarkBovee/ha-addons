"""The owner's mode per module: dry_run (plan only) or advisory (plan and recommend). 'auto' comes with the first module that writes."""
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HemsConfigEntry
from .advice import MODES, MODULES
from .coordinator import HemsCoordinator
from .entity import HemsEntity


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """One mode select per module."""
    async_add_entities(ModeSelect(entry.runtime_data, entry, module) for module in MODULES)


class ModeSelect(HemsEntity, SelectEntity):
    """The mode is stored by HEMS itself (.storage), so it survives a restart."""

    _attr_options = list(MODES)

    def __init__(self, coordinator: HemsCoordinator, entry: HemsConfigEntry, module: str) -> None:
        super().__init__(coordinator, entry, "select", f"{module}_mode")
        self._module = module
        self._attr_translation_key = f"{module}_mode"

    @property
    def current_option(self) -> str:
        return self.coordinator.control.modes[self._module]

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(self._module, option)
