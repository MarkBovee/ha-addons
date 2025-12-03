"""Sensor platform for Charge Amps Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ChargePoint, Connector
from .const import DOMAIN
from .coordinator import ChargeAmpsCoordinator, ChargeAmpsData

_LOGGER = logging.getLogger(__name__)


CONNECTOR_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="total_consumption",
        name="Total Consumption",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="voltage_l1",
        name="Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="voltage_l2",
        name="Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="voltage_l3",
        name="Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current_l1",
        name="Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current_l2",
        name="Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current_l3",
        name="Current L3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="connector_status",
        name="Connector Status",
        icon="mdi:ev-plug-type2",
    ),
)

CHARGER_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="charger_status",
        name="Charger Status",
        icon="mdi:ev-station",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Charge Amps sensors based on a config entry."""
    coordinator: ChargeAmpsCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    for charge_point in coordinator.data.charge_points:
        # Add charger-level sensors
        for description in CHARGER_SENSOR_DESCRIPTIONS:
            entities.append(
                ChargeAmpsChargerSensor(
                    coordinator=coordinator,
                    charge_point=charge_point,
                    description=description,
                )
            )

        # Add connector-level sensors
        for connector in charge_point.connectors:
            for description in CONNECTOR_SENSOR_DESCRIPTIONS:
                entities.append(
                    ChargeAmpsConnectorSensor(
                        coordinator=coordinator,
                        charge_point=charge_point,
                        connector=connector,
                        description=description,
                    )
                )

    async_add_entities(entities)


class ChargeAmpsChargerSensor(
    CoordinatorEntity[ChargeAmpsCoordinator], SensorEntity
):
    """Representation of a Charge Amps charger sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        charge_point: ChargePoint,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
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
    def native_value(self) -> str | None:
        """Return the sensor value."""
        if self._charge_point is None:
            return None

        if self.entity_description.key == "charger_status":
            return self._charge_point.status_name

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self._charge_point is None:
            return {}

        return {
            "serial_number": self._charge_point.serial_number,
            "product_name": self._charge_point.product_name,
            "status_code": self._charge_point.charge_point_status,
        }


class ChargeAmpsConnectorSensor(
    CoordinatorEntity[ChargeAmpsCoordinator], SensorEntity
):
    """Representation of a Charge Amps connector sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        charge_point: ChargePoint,
        connector: Connector,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
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
    def native_value(self) -> float | str | None:
        """Return the sensor value."""
        connector = self._connector
        if connector is None:
            return None

        key = self.entity_description.key
        if key == "power":
            return round(connector.current_power_w, 1)
        elif key == "total_consumption":
            return round(connector.total_consumption_kwh, 3)
        elif key == "voltage_l1":
            return round(connector.voltage1, 1)
        elif key == "voltage_l2":
            return round(connector.voltage2, 1)
        elif key == "voltage_l3":
            return round(connector.voltage3, 1)
        elif key == "current_l1":
            return round(connector.current1, 2)
        elif key == "current_l2":
            return round(connector.current2, 2)
        elif key == "current_l3":
            return round(connector.current3, 2)
        elif key == "connector_status":
            return connector.ocpp_status_name

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        connector = self._connector
        if connector is None:
            return {}

        attrs: dict[str, Any] = {
            "connector_id": connector.connector_id,
        }

        if self.entity_description.key == "connector_status":
            attrs["ocpp_status_code"] = connector.ocpp_status

        return attrs
