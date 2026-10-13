"""Shared base for HEMS entities: one device, one coordinator, stable unique ids."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HemsConfigEntry
from .const import DOMAIN
from .coordinator import HemsCoordinator


class HemsEntity(CoordinatorEntity[HemsCoordinator]):
    """Entities named after their role, grouped under the 'HEMS' service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HemsCoordinator, entry: HemsConfigEntry, domain: str, key: str) -> None:
        """Bind to the coordinator and register under the shared device.

        The entity id is set from the key, not derived from the translated name: Home Assistant builds ids from the
        instance language (a Dutch install would get sensor.hems_batterij_actie), and docs, dashboards and tests
        need ids that stay the same everywhere."""
        super().__init__(coordinator)
        self.entity_id = f"{domain}.hems_{key}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="HEMS", manufacturer="HEMS", model="Dry-run planner")
