"""Binary sensor platform for Charge Amps Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ChargePoint, Connector
from .const import DOMAIN
from .coordinator import ChargeAmpsCoordinator

_LOGGER = logging.getLogger(__name__)


CHARGER_BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="online",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)

CONNECTOR_BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Charge Amps binary sensors based on a config entry."""
    coordinator: ChargeAmpsCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []

    for charge_point in coordinator.data.charge_points:
        # Add charger-level binary sensors
        for description in CHARGER_BINARY_SENSOR_DESCRIPTIONS:
            entities.append(
                ChargeAmpsChargerBinarySensor(
                    coordinator=coordinator,
                    charge_point=charge_point,
                    description=description,
                )
            )

        # Add connector-level binary sensors
        for connector in charge_point.connectors:
            for description in CONNECTOR_BINARY_SENSOR_DESCRIPTIONS:
                entities.append(
                    ChargeAmpsConnectorBinarySensor(
                        coordinator=coordinator,
                        charge_point=charge_point,
                        connector=connector,
                        description=description,
                    )
                )

    async_add_entities(entities)


class ChargeAmpsChargerBinarySensor(
    CoordinatorEntity[ChargeAmpsCoordinator], BinarySensorEntity
):
    """Representation of a Charge Amps charger binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        charge_point: ChargePoint,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._charge_point_id = charge_point.id
        self._attr_unique_id = f"{charge_point.id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, charge_point.id)},
            name=charge_point.name,
            manufacturer="Charge Amps",
            model=charge_point.product_name,
            serial_number=charge_point.serial_number,
        )

    @property
    def _charge_point(self) -> ChargePoint | None:
        """Get the current charge point data."""
        return self.coordinator.data.get_charge_point(self._charge_point_id)

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self._charge_point is None:
            return None

        if self.entity_description.key == "online":
            return self._charge_point.is_online

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self._charge_point is None:
            return {}

        return {
            "status": self._charge_point.status_name,
            "status_code": self._charge_point.charge_point_status,
        }


class ChargeAmpsConnectorBinarySensor(
    CoordinatorEntity[ChargeAmpsCoordinator], BinarySensorEntity
):
    """Representation of a Charge Amps connector binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        charge_point: ChargePoint,
        connector: Connector,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._charge_point_id = charge_point.id
        self._connector_id = connector.connector_id

        # Create unique ID with connector number
        connector_suffix = f"_c{connector.connector_id}" if len(charge_point.connectors) > 1 else ""
        self._attr_unique_id = f"{charge_point.id}{connector_suffix}_{description.key}"

        # Add connector number to name if multiple connectors
        if len(charge_point.connectors) > 1:
            self._attr_name = f"{description.name} (Connector {connector.connector_id})"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, charge_point.id)},
            name=charge_point.name,
            manufacturer="Charge Amps",
            model=charge_point.product_name,
            serial_number=charge_point.serial_number,
        )

    @property
    def _connector(self) -> Connector | None:
        """Get the current connector data."""
        charge_point = self.coordinator.data.get_charge_point(self._charge_point_id)
        if charge_point is None:
            return None
        for conn in charge_point.connectors:
            if conn.connector_id == self._connector_id:
                return conn
        return None

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        connector = self._connector
        if connector is None:
            return None

        if self.entity_description.key == "charging":
            return connector.is_charging

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        connector = self._connector
        if connector is None:
            return {}

        return {
            "connector_id": connector.connector_id,
            "ocpp_status": connector.ocpp_status_name,
            "ocpp_status_code": connector.ocpp_status,
        }
