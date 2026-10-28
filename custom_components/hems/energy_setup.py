"""Fill in Home Assistant's Energy dashboard from HEMS: the solar and battery sources from HEMS's own kWh counters, and the
grid's import and export price from HEMS's price sensors.

Only adds what is missing and never removes or replaces anything the owner set: a solar or battery source that exists stays,
a grid tariff that already has a price keeps it. `plan_energy_setup` is pure; `async_setup_energy` reads, plans and (unless it
is a preview) saves through Home Assistant's energy manager.
"""
import copy
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.energy.data import async_get_manager
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

KEYS = {"solar": "solar_energy", "charged": "battery_charged_energy", "discharged": "battery_discharged_energy",
        "import_price": "import_price", "export_price": "export_price"}


@dataclass(frozen=True)
class EnergySetup:
    """What the setup would change: the new energy sources list and the changes in words."""
    energy_sources: list[dict[str, Any]]
    changes: list[str] = field(default_factory=list)


def _has_price(source: dict[str, Any], export: bool) -> bool:
    """True when a grid tariff already has a price (fixed, entity or cost statistic) for import, or for export."""
    keys = ("stat_compensation", "entity_energy_price_export", "number_energy_price_export") if export else \
        ("stat_cost", "entity_energy_price", "number_energy_price")
    return any(source.get(k) not in (None, "") for k in keys)


def plan_energy_setup(sources: list[dict[str, Any]], ids: dict[str, str | None]) -> EnergySetup:
    """The energy sources with HEMS's solar, battery and prices added where missing (`ids` maps KEYS to entity ids)."""
    out = copy.deepcopy(sources)
    changes: list[str] = []
    if ids.get("solar") and not any(s.get("type") == "solar" for s in out):
        out.append({"type": "solar", "stat_energy_from": ids["solar"], "config_entry_solar_forecast": None})
        changes.append(f"add solar: {ids['solar']}")
    if ids.get("charged") and ids.get("discharged") and not any(s.get("type") == "battery" for s in out):
        out.append({"type": "battery", "stat_energy_from": ids["discharged"], "stat_energy_to": ids["charged"]})
        changes.append(f"add battery: out {ids['discharged']}, in {ids['charged']}")
    for source in out:
        if source.get("type") != "grid":
            continue
        name = source.get("stat_energy_from") or "grid"
        if ids.get("import_price") and source.get("stat_energy_from") and not _has_price(source, export=False):
            source["entity_energy_price"] = ids["import_price"]
            changes.append(f"price {name}: {ids['import_price']}")
        if ids.get("export_price") and source.get("stat_energy_to") and not _has_price(source, export=True):
            source["entity_energy_price_export"] = ids["export_price"]
            changes.append(f"export price {source['stat_energy_to']}: {ids['export_price']}")
    return EnergySetup(out, changes)


def hems_entity_ids(hass: HomeAssistant, entry_id: str) -> dict[str, str | None]:
    """The entity ids of HEMS's counters and price sensors on this installation (the owner may have renamed them)."""
    registry = er.async_get(hass)
    return {name: registry.async_get_entity_id("sensor", DOMAIN, f"{entry_id}_{key}") for name, key in KEYS.items()}


async def async_setup_energy(hass: HomeAssistant, entry_id: str, preview: bool) -> dict[str, Any]:
    """Plan the Energy dashboard additions and save them unless `preview`; returns the changes (empty when nothing is missing)."""
    manager = await async_get_manager(hass)
    current = (manager.data or {}).get("energy_sources") or []
    setup = plan_energy_setup(list(current), hems_entity_ids(hass, entry_id))
    if setup.changes and not preview:
        await manager.async_update({"energy_sources": setup.energy_sources})
    return {"preview": preview, "changes": setup.changes, "saved": bool(setup.changes and not preview)}
