"""Sensors that publish the dry-run plan; nothing here controls a device."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import CURRENCY_EURO, UnitOfElectricCurrent, UnitOfEnergy, UnitOfIrradiance, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HemsConfigEntry
from .coordinator import HemsCoordinator, HemsSnapshot
from .engine import ev as ev_module, executor
from .engine.outlook import cheapest_block, first_window, forecast_series, hour_mean, hour_total, price_curve, window_total
from .engine.windows import record
from .entity import HemsEntity

QUARTER = timedelta(minutes=15)
EV_STATUSES = [ev_module.STATUS_OFF, ev_module.STATUS_NOT_PLUGGED, ev_module.STATUS_NO_SOC, ev_module.STATUS_PROBLEM, ev_module.STATUS_IDLE,
               ev_module.STATUS_PLANNED, ev_module.STATUS_AT_RISK, ev_module.STATUS_FORCED]
PLAN_PREVIEW_SLOTS = 48                       # 12 hours of quarters in the plan attribute


@dataclass(frozen=True, kw_only=True)
class HemsSensorDescription(SensorEntityDescription):
    """A sensor whose state and attributes come straight from the latest snapshot."""
    value: Callable[[HemsSnapshot], Any]
    attributes: Callable[[HemsSnapshot], dict[str, Any]] | None = None


def _heating_start(snap: HemsSnapshot):
    """Start of the next planned water heater run (a run that is going on counts); None when the module is off or no day has a complete price curve."""
    runs = snap.output.heating_runs
    return runs[0].start if runs else None


def _heating_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """Every planned heating run in local time: kind, start, end, expected kWh and mean price; the module is switched on in the settings."""
    tz = dt_util.get_default_time_zone()
    return {"windows": [{"kind": r.kind, "start": r.start.astimezone(tz).isoformat(timespec="minutes"), "end": r.end.astimezone(tz).isoformat(timespec="minutes"),
                         "energy_kwh": round(r.energy_kwh, 2), "avg_price_eur_kwh": round(r.avg_price, 4)} for r in snap.output.heating_runs]}


def _ev_start(snap: HemsSnapshot):
    """Start of the first planned charge quarter of the EV module; None when the module is off or nothing is planned."""
    plan = snap.output.ev_plan
    return plan.quarters[0].start if plan and plan.quarters else None


def _ev_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """The EV plan in local time: status and reason, the deadline, the energy still needed, and the coming quarters with current, price, surplus and tier."""
    plan = snap.output.ev_plan
    if plan is None:
        return {}
    tz = dt_util.get_default_time_zone()
    return {"status": plan.status, "reason": plan.reason, "deadline": plan.deadline.astimezone(tz).isoformat(timespec="minutes") if plan.deadline else None,
            "required_kwh": round(plan.required_kwh, 2), "optional_kwh": round(plan.optional_kwh, 2), "planned_kwh": round(plan.planned_kwh(), 2),
            "shortfall_kwh": round(plan.shortfall_kwh, 2),
            "quarters": [{"start": q.start.astimezone(tz).isoformat(timespec="minutes"), "current_a": q.current_a, "kwh": round(q.kwh, 2),
                          "price_eur_kwh": round(q.price, 4), "surplus_kwh": round(q.surplus_kwh, 2), "tier": q.tier} for q in plan.quarters[:PLAN_PREVIEW_SLOTS]]}


def _ev_setpoint_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """Why the setpoint is what it is: the plan's current, the grid headroom, and the rule that held or limited it."""
    point = snap.ev_setpoint
    return {} if point is None else {"planned_a": point.planned_a, "code": point.code, "reason": point.reason, "allowed_a": snap.ev_allowed_a}


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
    """The plan for a dashboard: the windows, the number of planned quarters, and the next quarters one by one (local times)."""
    d = snap.output.decision
    if not d:
        return {"status": snap.output.status}
    tz = dt_util.get_default_time_zone()
    slots = d.plan.slots[:PLAN_PREVIEW_SLOTS]
    return {"status": snap.output.status, "markdown": snap.plan_table, "windows": list(snap.plan_windows), "quarters": len(d.plan.slots),
            "pv_gain_w_per_wm2": round(snap.pv_gain_w_per_wm2, 2), "history_hours": snap.history_hours,
            "slots": [{"start": (d.slot_start + i * QUARTER).astimezone(tz).isoformat(), "action": s.action, "power_w": round(s.battery_kwh * 4000),
                       "soc_kwh": round(s.soc_kwh, 2), "reason": s.reason} for i, s in enumerate(slots)]}


def _sell_window_start(snap: HemsSnapshot):
    """Start of the next sell window as the plan sells it (the band's start when the plan sells nothing in it); None without a window."""
    analysis = snap.output.decision.analysis if snap.output.decision else None
    return (analysis.reports[0].sold_from or analysis.reports[0].window.start) if analysis and analysis.reports else None


def _sell_window_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """All sell windows of the horizon in local time with their thresholds, status and the charges that feed them."""
    analysis = snap.output.decision.analysis if snap.output.decision else None
    if not analysis:
        return {}
    tz = dt_util.get_default_time_zone()
    return {"status": analysis.reports[0].status if analysis.reports else None, "outside_kwh": analysis.outside_kwh,
            "windows": [record(r, tz) for r in analysis.reports]}


def _execution_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """The executor's view: what the planner wanted, what may be sent after the live SoC check, and why they differ."""
    e = snap.execution
    return {"planned_w": e.planned_w, "power_w": e.power_w, "overridden": e.overridden, "reason": e.reason, "soc_pct": e.soc_pct}


def _decision_attrs(snap: HemsSnapshot) -> dict[str, Any]:
    """Why this action: the trace of the decision, minus bulky fields."""
    return {k: v for k, v in snap.output.trace.items() if k not in ("status",)} | {"status": snap.output.status}


def _start(snap: HemsSnapshot):
    """Start of the current quarter, the reference for every 'coming hour' and curve; None without a decision."""
    return snap.output.decision.slot_start if snap.output.decision else None


def _hour_total(snap: HemsSnapshot, series) -> float | None:
    """The coming hour of an energy forecast (kWh), or None when the forecast does not cover the whole hour."""
    start = _start(snap)
    return hour_total(series, start) if start and series else None


def _hour_mean(snap: HemsSnapshot, series) -> float | None:
    """The coming hour of a rate forecast (irradiance, temperature) as its mean, or None when it does not cover the whole hour."""
    start = _start(snap)
    return hour_mean(series, start) if start and series else None


def _forecast_attrs(snap: HemsSnapshot, series, key: str) -> dict[str, Any]:
    """The next 24 hours of a forecast, per quarter in local time, for a dashboard chart."""
    start = _start(snap)
    return {"forecast": forecast_series(series, start, dt_util.get_default_time_zone(), key)} if start and series else {}


def _weather_series(snap: HemsSnapshot, field: str):
    """One series of the weather forecast ('ghi_w_m2' or 'temperature_c'), or an empty one without weather."""
    return getattr(snap.weather, field) if snap.weather else {}


def _price_attrs(snap: HemsSnapshot, field: str) -> dict[str, Any]:
    """Every known price from this quarter on (today and, once published, tomorrow), in local time."""
    start, prices = _start(snap), snap.output.prices
    return {"curve": price_curve(prices, field, start, dt_util.get_default_time_zone())} if start and prices else {}


def _cheapest_charge(snap: HemsSnapshot) -> dict | None:
    """The cheapest three-hour block of import prices from this quarter on, or None without prices or a quarter to start from."""
    start, prices = _start(snap), snap.output.prices
    return cheapest_block(prices, start) if start and prices else None


def _window_start(snap: HemsSnapshot, action: str):
    """Start of the first planned run of `action` (it may be going on now); for a charge the plan does not plan, the start of the cheapest price block."""
    window = first_window(snap.output.trace.get("segments") or [], action)
    if window:
        return window["begin"]
    block = _cheapest_charge(snap) if action == "charge" else None
    return block["begin"] if block else None


def _window_attrs(snap: HemsSnapshot, action: str) -> dict[str, Any]:
    """The first window of `action` in numbers: end, energy, power, price, SoC at both ends, and the PV and house load expected inside it.

    `planned` says whether the plan does it; a charge window the plan does not have shows the cheapest price block instead (`planned` False)."""
    window = first_window(snap.output.trace.get("segments") or [], action)
    if not window:
        block = _cheapest_charge(snap) if action == "charge" else None
        return {"planned": False, "end": block["end"].astimezone(dt_util.get_default_time_zone()).isoformat(), "avg_price_eur_kwh": block["avg_price"],
                "note": "The plan charges nothing now; this is the cheapest three-hour block of import prices."} if block else {"planned": False}
    begin, end = window["begin"], window["end"]
    return {"planned": True, "end": end.astimezone(dt_util.get_default_time_zone()).isoformat(), "kwh": window["kwh"], "power_w": window["avg_w"],
            "avg_price_eur_kwh": window["avg_price"], "soc_from_pct": window["soc_from_pct"], "soc_to_pct": window["soc_to_pct"],
            "pv_kwh": window_total(snap.output.pv_kwh, begin, end), "load_kwh": window_total(snap.output.load_kwh, begin, end)}


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
                          state_class=SensorStateClass.MEASUREMENT, value=lambda s: _first_price(s, "import_eur_kwh"),
                          attributes=lambda s: _price_attrs(s, "import")),
    HemsSensorDescription(key="export_price", translation_key="export_price", native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
                          state_class=SensorStateClass.MEASUREMENT, value=lambda s: _first_price(s, "export_eur_kwh"),
                          attributes=lambda s: _price_attrs(s, "export")),
    HemsSensorDescription(key="pv_forecast_next_hour", translation_key="pv_forecast_next_hour", device_class=SensorDeviceClass.ENERGY,
                          native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, value=lambda s: _hour_total(s, s.output.pv_kwh),
                          attributes=lambda s: _forecast_attrs(s, s.output.pv_kwh, "kwh")),
    HemsSensorDescription(key="load_forecast_next_hour", translation_key="load_forecast_next_hour", device_class=SensorDeviceClass.ENERGY,
                          native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, value=lambda s: _hour_total(s, s.output.load_kwh),
                          attributes=lambda s: _forecast_attrs(s, s.output.load_kwh, "kwh")),
    HemsSensorDescription(key="irradiance_forecast", translation_key="irradiance_forecast", device_class=SensorDeviceClass.IRRADIANCE,
                          native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
                          value=lambda s: _hour_mean(s, _weather_series(s, "ghi_w_m2")),
                          attributes=lambda s: _forecast_attrs(s, _weather_series(s, "ghi_w_m2"), "w_m2")),
    HemsSensorDescription(key="temperature_forecast", translation_key="temperature_forecast", device_class=SensorDeviceClass.TEMPERATURE,
                          native_unit_of_measurement=UnitOfTemperature.CELSIUS, value=lambda s: _hour_mean(s, _weather_series(s, "temperature_c")),
                          attributes=lambda s: _forecast_attrs(s, _weather_series(s, "temperature_c"), "celsius")),
    HemsSensorDescription(key="sell_window", translation_key="sell_window", device_class=SensorDeviceClass.TIMESTAMP,
                          value=_sell_window_start, attributes=_sell_window_attrs),
    HemsSensorDescription(key="charge_window", translation_key="charge_window", device_class=SensorDeviceClass.TIMESTAMP,
                          value=lambda s: _window_start(s, "charge"), attributes=lambda s: _window_attrs(s, "charge")),
    HemsSensorDescription(key="discharge_window", translation_key="discharge_window", device_class=SensorDeviceClass.TIMESTAMP,
                          value=lambda s: _window_start(s, "discharge"), attributes=lambda s: _window_attrs(s, "discharge")),
    HemsSensorDescription(key="water_heater_plan", translation_key="water_heater_plan", device_class=SensorDeviceClass.TIMESTAMP,
                          value=_heating_start, attributes=_heating_attrs),
    HemsSensorDescription(key="ev_plan", translation_key="ev_plan", device_class=SensorDeviceClass.TIMESTAMP, value=_ev_start, attributes=_ev_attrs),
    HemsSensorDescription(key="ev_status", translation_key="ev_status", device_class=SensorDeviceClass.ENUM, options=EV_STATUSES,
                          value=lambda s: s.output.ev_plan.status if s.output.ev_plan else None),
    HemsSensorDescription(key="ev_setpoint", translation_key="ev_setpoint", device_class=SensorDeviceClass.CURRENT, native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                          value=lambda s: s.ev_setpoint.current_a if s.ev_setpoint else None, attributes=_ev_setpoint_attrs),
    HemsSensorDescription(key="pv_forecast_24h", translation_key="pv_forecast_24h", device_class=SensorDeviceClass.ENERGY,
                          native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                          value=lambda s: round(sum(v for t, v in s.output.pv_kwh.items() if s.output.decision and
                                                    s.output.decision.slot_start <= t < s.output.decision.slot_start + 96 * QUARTER), 1) if s.output.pv_kwh else None),
    HemsSensorDescription(key="plan", translation_key="plan", value=lambda s: s.plan_text or None, attributes=_plan_preview),
)


async def async_setup_entry(hass: HomeAssistant, entry: HemsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """One entity per description, all under a single HEMS service device."""
    async_add_entities(HemsSensor(entry.runtime_data, entry, d) for d in SENSORS)


class HemsSensor(HemsEntity, SensorEntity):
    """A read-only view of one aspect of the latest dry-run cycle."""

    entity_description: HemsSensorDescription

    # Series of up to a few thousand characters change every quarter and say nothing in history: keep them out of the recorder.
    _unrecorded_attributes = frozenset({"slots", "curve", "forecast", "windows", "markdown", "quarters"})

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
