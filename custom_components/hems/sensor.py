"""Sensors that publish the dry-run plan; nothing here controls a device."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HemsConfigEntry
from .coordinator import HemsCoordinator, HemsSnapshot
from .engine import executor
from .entity import HemsEntity

QUARTER = timedelta(minutes=15)
PLAN_PREVIEW_SLOTS = 48                       # 12 hours of quarters in the plan attribute


@dataclass(frozen=True, kw_only=True)
class HemsSensorDescription(SensorEntityDescription):
    """A sensor whose state and attributes come straight from the latest snapshot."""
    value: Callable[[HemsSnapshot], Any]
    attributes: Callable[[HemsSnapshot], dict[str, Any]] | None = None


def _decision(snap: HemsSnapshot):
    """The battery decision of this cycle, or None."""
    return snap.output.decision


def _first_price(snap: HemsSnapshot, series_name: str) -> float | None:
    """Price of the current quarter from the engine's price series."""
    prices, decision = snap.output.prices, snap.output.decision
    if not prices or not decision or decision.slot_start not in prices.starts:
        return None
    i = prices.starts.index(decision.slot_start)
    return round(getattr(prices, series_name)[i], 4)


def _plan_preview(snap: HemsSnapshot) -> dict[str, Any]:
    """Compact attribute with the next quarters of the plan: start, action, AC watts, SoC after."""
    d = snap.output.decision
    if not d:
        return {"status": snap.output.status}
    slots = d.plan.slots[:PLAN_PREVIEW_SLOTS]
    return {"status": snap.output.status, "pv_gain_w_per_wm2": round(snap.pv_gain_w_per_wm2, 2), "history_hours": snap.history_hours,
            "slots": [{"t": (d.slot_start + i * QUARTER).isoformat(), "a": s.action, "w": round(s.battery_kwh * 4000), "soc_kwh": round(s.soc_kwh, 2),
                       "why": s.reason} for i, s in enumerate(slots)]}


def _execution_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """The executor's view: what the planner wanted, what may be sent after the live SoC check, and why they differ."""
    e = snap.execution
    return {"planned_w": e.planned_w, "power_w": e.power_w, "overridden": e.overridden, "reason": e.reason, "soc_pct": e.soc_pct}


def _decision_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """Why this action: the trace of the decision, minus bulky fields."""
    return {k: v for k, v in snap.output.trace.items() if k not in ("status",)} | {"status": snap.output.status}


SENSORS: tuple[HemsSensorDescription, ...] = (
    HemsSensorDescription(key="battery_action", translation_key="battery_action", device_class=SensorDeviceClass.ENUM,
                          options=["charge", "discharge", "idle"],
                          value=lambda s: s.output.decision.plan.slots[0].action if s.output.decision else None, attributes=_decision_attrs),
    HemsSensorDescription(key="battery_setpoint", translation_key="battery_setpoint", device_class=SensorDeviceClass.POWER,
                          native_unit_of_measurement=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT,
                          value=lambda s: s.execution.power_w if s.output.decision else None, attributes=_execution_attrs),
    HemsSensorDescription(key="executor", translation_key="executor", device_class=SensorDeviceClass.ENUM,
                          options=[executor.AS_PLANNED, executor.NO_PLAN, executor.EXPIRED, executor.NO_SOC, executor.STALE_SOC, executor.AT_FLOOR,
                                   executor.LIMITED_FLOOR, executor.AT_FULL, executor.LIMITED_FULL],
                          value=lambda s: s.execution.code, attributes=_execution_attrs),
    HemsSensorDescription(key="expected_saving", translation_key="expected_saving", device_class=SensorDeviceClass.MONETARY,
                          native_unit_of_measurement=CURRENCY_EURO,
                          value=lambda s: round(s.output.decision.plan.saving, 2) if s.output.decision else None),
    HemsSensorDescription(key="status", translation_key="status", device_class=SensorDeviceClass.ENUM,
                          options=["ok", "no_soc", "stale_soc", "no_prices", "no_price_for_now"], value=lambda s: s.output.status,
                          attributes=lambda s: {"price_source": s.output.trace.get("price_source"), "weather_age_min": None if s.weather_age_min is None else round(s.weather_age_min),
                                                "history_hours": s.history_hours}),
    HemsSensorDescription(key="import_price", translation_key="import_price", native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
                          state_class=SensorStateClass.MEASUREMENT, value=lambda s: _first_price(s, "import_eur_kwh")),
    HemsSensorDescription(key="export_price", translation_key="export_price", native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
                          state_class=SensorStateClass.MEASUREMENT, value=lambda s: _first_price(s, "export_eur_kwh")),
    HemsSensorDescription(key="pv_forecast_24h", translation_key="pv_forecast_24h", device_class=SensorDeviceClass.ENERGY,
                          native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                          value=lambda s: round(sum(v for t, v in s.output.pv_kwh.items() if s.output.decision and
                                                    s.output.decision.slot_start <= t < s.output.decision.slot_start + 96 * QUARTER), 1) if s.output.pv_kwh else None),
    HemsSensorDescription(key="plan", translation_key="plan",
                          value=lambda s: len(s.output.decision.plan.slots) if s.output.decision else 0, attributes=_plan_preview),
)


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """One entity per description, all under a single HEMS service device."""
    async_add_entities(HemsSensor(entry.runtime_data, entry, d) for d in SENSORS)


class HemsSensor(HemsEntity, SensorEntity):
    """A read-only view of one aspect of the latest dry-run cycle."""

    entity_description: HemsSensorDescription

    def __init__(self, coordinator: HemsCoordinator, entry: HemsConfigEntry, description: HemsSensorDescription) -> None:
        """Bind to the coordinator under the shared device."""
        super().__init__(coordinator, entry, "sensor", description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """State from the latest snapshot."""
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributes from the latest snapshot, when the sensor defines any."""
        fn = self.entity_description.attributes
        return fn(self.coordinator.data) if fn else None
