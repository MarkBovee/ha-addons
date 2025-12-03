"""Config flow for Charge Amps Monitor integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChargeAmpsApi, ChargeAmpsAuthError, ChargeAmpsConnectionError
from .const import (
    CONF_BASE_URL,
    CONF_HOST_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_HOST_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ChargeAmpsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Charge Amps Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._email: str | None = None
        self._password: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            # Test credentials
            session = async_get_clientsession(self.hass)
            api = ChargeAmpsApi(
                email=self._email,
                password=self._password,
                base_url=DEFAULT_BASE_URL,
                session=session,
            )

            try:
                if await api.validate_credentials():
                    # Check if already configured
                    await self.async_set_unique_id(self._email.lower())
                    self._abort_if_unique_id_configured()

                    # Move to advanced settings
                    return await self.async_step_advanced()
                else:
                    errors["base"] = "invalid_auth"
            except ChargeAmpsAuthError:
                errors["base"] = "invalid_auth"
            except ChargeAmpsConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle advanced settings step."""
        if user_input is not None:
            # Create the config entry
            return self.async_create_entry(
                title=f"Charge Amps ({self._email})",
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_HOST_NAME: user_input.get(CONF_HOST_NAME, DEFAULT_HOST_NAME),
                    CONF_BASE_URL: user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL),
                    CONF_UPDATE_INTERVAL: user_input.get(
                        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                    ),
                },
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HOST_NAME, default=DEFAULT_HOST_NAME): str,
                    vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ChargeAmpsOptionsFlow:
        """Get the options flow handler."""
        return ChargeAmpsOptionsFlow(config_entry)


class ChargeAmpsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Charge Amps Monitor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.data.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
        )
