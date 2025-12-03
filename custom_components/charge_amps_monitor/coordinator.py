"""DataUpdateCoordinator for Charge Amps Monitor."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChargeAmpsApi, ChargeAmpsApiError, ChargePoint
from .const import (
    CONF_BASE_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ChargeAmpsData:
    """Container for Charge Amps data."""

    def __init__(self, charge_points: list[ChargePoint]) -> None:
        """Initialize the data container."""
        self.charge_points = charge_points

    def get_charge_point(self, charge_point_id: str) -> ChargePoint | None:
        """Get a charge point by ID."""
        for cp in self.charge_points:
            if cp.id == charge_point_id:
                return cp
        return None


class ChargeAmpsCoordinator(DataUpdateCoordinator[ChargeAmpsData]):
    """Coordinator to manage Charge Amps data updates."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.config_entry = config_entry
        self._api: ChargeAmpsApi | None = None

        update_interval = config_entry.data.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_setup(self) -> None:
        """Set up the API client."""
        session = async_get_clientsession(self.hass)
        self._api = ChargeAmpsApi(
            email=self.config_entry.data[CONF_EMAIL],
            password=self.config_entry.data[CONF_PASSWORD],
            base_url=self.config_entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            session=session,
        )

    async def _async_update_data(self) -> ChargeAmpsData:
        """Fetch data from Charge Amps API."""
        if self._api is None:
            await self._async_setup()

        try:
            charge_points = await self._api.get_charge_points()
            return ChargeAmpsData(charge_points=charge_points)
        except ChargeAmpsApiError as err:
            raise UpdateFailed(f"Error communicating with Charge Amps API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close API session."""
        if self._api:
            await self._api.close()
