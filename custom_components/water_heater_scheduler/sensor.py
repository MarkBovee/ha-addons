"""Sensor platform for Water Heater Scheduler."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_WATER_HEATER_ENTITY
from .coordinator import WaterHeaterSchedulerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: WaterHeaterSchedulerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ProgramSensor(coordinator, entry),
        TargetTempSensor(coordinator, entry),
        StatusSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class WaterHeaterSchedulerSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Water Heater Scheduler sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WaterHeaterSchedulerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._water_heater = entry.data.get(CONF_WATER_HEATER_ENTITY, "")

        # Device info - group all sensors under one device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Water Heater Scheduler ({entry.title})",
            manufacturer="Home Assistant Community",
            model="Water Heater Scheduler",
            sw_version="1.0.0",
        )


class ProgramSensor(WaterHeaterSchedulerSensorBase):
    """Sensor showing current heating program."""

    _attr_name = "Current Program"
    _attr_icon = "mdi:water-boiler"

    def __init__(
        self,
        coordinator: WaterHeaterSchedulerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_program"

    @property
    def native_value(self) -> str:
        """Return the current program."""
        return self.coordinator.current_program


class TargetTempSensor(WaterHeaterSchedulerSensorBase):
    """Sensor showing target temperature."""

    _attr_name = "Target Temperature"
    _attr_icon = "mdi:thermometer"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: WaterHeaterSchedulerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_target_temp"

    @property
    def native_value(self) -> int:
        """Return the target temperature."""
        return self.coordinator.target_temperature


class StatusSensor(WaterHeaterSchedulerSensorBase):
    """Sensor showing current status text."""

    _attr_name = "Status"
    _attr_icon = "mdi:information-outline"

    def __init__(
        self,
        coordinator: WaterHeaterSchedulerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        """Return the status text."""
        return self.coordinator.status
