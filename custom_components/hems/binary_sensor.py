"""Binary sensors: whether tomorrow's prices are known (HEMS fetches the day-ahead prices itself)."""
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HemsConfigEntry
from .entity import HemsEntity


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """One binary sensor: tomorrow's prices available."""
    async_add_entities([TomorrowPricesAvailable(entry.runtime_data, entry),
                        *(AlertSensor(entry.runtime_data, entry, key) for key in ("data", "deadline", "not_executed", "legionella"))])


class TomorrowPricesAvailable(HemsEntity, BinarySensorEntity):
    """On once any price of tomorrow's delivery day is known, from the market source or the price sensor."""

    _attr_translation_key = "tomorrow_prices_available"

    def __init__(self, coordinator, entry: HemsConfigEntry) -> None:
        """Register as 'tomorrow_prices_available'."""
        super().__init__(coordinator, entry, "binary_sensor", "tomorrow_prices_available")

    @property
    def is_on(self) -> bool:
        """True when at least one quarter of tomorrow is known."""
        return self.coordinator.data.tomorrow_quarters > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """How many quarters of tomorrow are known, until when prices are known, and which source delivered them."""
        data = self.coordinator.data
        return {"tomorrow_intervals": data.tomorrow_quarters, "prices_until": data.prices_until.isoformat() if data.prices_until else None,
                "price_source": data.output.trace.get("price_source")}


class AlertSensor(HemsEntity, BinarySensorEntity):
    """A condition worth a notification (see coordinator.alerts); the reason is an attribute. The notify blueprint listens to these."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry: HemsConfigEntry, key: str) -> None:
        super().__init__(coordinator, entry, "binary_sensor", f"alert_{key}")
        self._key = key
        self._attr_translation_key = f"alert_{key}"

    def _alert(self) -> dict[str, Any]:
        return self.coordinator.alerts().get(self._key, {})

    @property
    def is_on(self) -> bool:
        return bool(self._alert().get("on"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {k: v for k, v in self._alert().items() if k != "on"}
