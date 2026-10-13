"""Binary sensors: whether tomorrow's prices are known (HEMS fetches the day-ahead prices itself)."""
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HemsConfigEntry
from .entity import HemsEntity


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """One binary sensor: tomorrow's prices available."""
    async_add_entities([TomorrowPricesAvailable(entry.runtime_data, entry)])


class TomorrowPricesAvailable(HemsEntity, BinarySensorEntity):
    """On once any price of tomorrow's delivery day is known, from the market source or the price sensor."""

    _attr_translation_key = "tomorrow_prices_available"

    def __init__(self, coordinator, entry: HemsConfigEntry) -> None:
        """Register as 'tomorrow_prices_available'."""
        super().__init__(coordinator, entry, "tomorrow_prices_available")

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
