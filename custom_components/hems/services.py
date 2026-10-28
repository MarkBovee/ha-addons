"""Services for the dashboard's controls: apply or dismiss a recommendation, and put everything back to dry-run."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .energy_setup import async_setup_energy


def _coordinator(hass: HomeAssistant):
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return entry.runtime_data
    raise ServiceValidationError("HEMS is not loaded", translation_domain=DOMAIN, translation_key="not_loaded")


def async_register_services(hass: HomeAssistant) -> None:
    """Register once per run (from async_setup)."""

    async def apply(call: ServiceCall):
        try:
            rec = await _coordinator(hass).async_apply(call.data["id"])
        except KeyError as err:
            raise ServiceValidationError("No open recommendation with this id (the plan may have changed)", translation_domain=DOMAIN,
                                         translation_key="unknown_recommendation") from err
        return {"recommendation": rec}

    async def dismiss(call: ServiceCall) -> None:
        await _coordinator(hass).async_dismiss(call.data["id"])

    async def disarm_all(call: ServiceCall) -> None:
        await _coordinator(hass).async_disarm_all()

    hass.services.async_register(DOMAIN, "apply_recommendation", apply, vol.Schema({vol.Required("id"): str}), supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "dismiss_recommendation", dismiss, vol.Schema({vol.Required("id"): str}))
    async def setup_energy_dashboard(call: ServiceCall):
        """Add HEMS's solar, battery and prices to the Energy dashboard where missing; with preview, only say what would change."""
        coordinator = _coordinator(hass)
        return await async_setup_energy(hass, coordinator.config_entry.entry_id, call.data.get("preview", False))

    hass.services.async_register(DOMAIN, "disarm_all", disarm_all, vol.Schema({}))
    hass.services.async_register(DOMAIN, "setup_energy_dashboard", setup_energy_dashboard, vol.Schema({vol.Optional("preview", default=False): bool}),
                                 supports_response=SupportsResponse.OPTIONAL)
