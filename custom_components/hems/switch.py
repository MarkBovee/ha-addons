"""The one control HEMS offers itself: the EV override. It changes the plan, never a device."""
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HemsConfigEntry
from .coordinator import HemsCoordinator
from .entity import HemsEntity


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """The override switch of the EV module."""
    async_add_entities([ForceChargeSwitch(entry.runtime_data, entry)])


class ForceChargeSwitch(HemsEntity, SwitchEntity):
    """On = plan the required EV energy as early and as hard as allowed, whatever the price.

    It ends by itself when the car leaves or the required target is reached, and after a restart it is off on purpose: an override
    that survives a restart could charge a car at a bad price long after the owner forgot it."""

    _attr_translation_key = "ev_force_charge"

    def __init__(self, coordinator: HemsCoordinator, entry: HemsConfigEntry) -> None:
        """Bind to the coordinator under the shared device."""
        super().__init__(coordinator, entry, "switch", "ev_force_charge")

    @property
    def is_on(self) -> bool:
        """Whether the override is active."""
        return self.coordinator.force_charge

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the override."""
        await self.coordinator.set_force_charge(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """End the override."""
        await self.coordinator.set_force_charge(False)
