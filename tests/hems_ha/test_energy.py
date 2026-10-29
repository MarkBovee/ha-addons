"""HEMS's kWh counters and the Energy dashboard setup: adds solar, battery and prices where missing, never replaces what is set."""
from datetime import datetime, timedelta, timezone

from homeassistant.components.energy.data import async_get_manager
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.hems.energy_setup import plan_energy_setup
from custom_components.hems.realised import EnergyCounters

from test_integration import set_states, setup_entry

IDS = {"solar": "sensor.hems_solar_energy", "charged": "sensor.hems_battery_charged_energy", "discharged": "sensor.hems_battery_discharged_energy",
       "import_price": "sensor.hems_import_price", "export_price": "sensor.hems_export_price"}
GRID = {"type": "grid", "stat_energy_from": "sensor.meter_t1", "stat_energy_to": "sensor.meter_t1_out", "stat_cost": None, "entity_energy_price": None,
        "number_energy_price": None, "stat_compensation": None, "entity_energy_price_export": None, "number_energy_price_export": None,
        "cost_adjustment_day": 0}


def test_counters_integrate_power_and_skip_a_gap():
    c = EnergyCounters()
    t = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    c.sample(t, 4000, 2000)
    c.sample(t + timedelta(seconds=90), 4000, -3000)          # 90 s at 4 kW solar, 2 kW charging
    c.sample(t + timedelta(seconds=180), 0, 0)                # 90 s discharging at 3 kW
    c.sample(t + timedelta(minutes=30), 0, 0)                 # a 30-minute gap: not integrated
    assert round(c.solar_kwh, 4) == 0.2 and round(c.charged_kwh, 4) == 0.05 and round(c.discharged_kwh, 4) == 0.075
    again = EnergyCounters()
    again.restore(c.state())
    assert again.state() == c.state()
    again.restore({"solar_kwh": 0.0})
    assert again.solar_kwh == c.state()["solar_kwh"], "a counter never goes back"


def test_the_setup_adds_what_is_missing_and_keeps_what_is_set():
    setup = plan_energy_setup([GRID, {**GRID, "stat_energy_from": "sensor.meter_t2", "number_energy_price": 0.25}], IDS)
    types = [s["type"] for s in setup.energy_sources]
    assert types == ["grid", "grid", "solar", "battery"]
    assert setup.energy_sources[0]["entity_energy_price"] == "sensor.hems_import_price"
    assert setup.energy_sources[1].get("entity_energy_price") is None and setup.energy_sources[1]["number_energy_price"] == 0.25, "a set price stays"
    assert setup.energy_sources[3] == {"type": "battery", "stat_energy_from": IDS["discharged"], "stat_energy_to": IDS["charged"]}
    again = plan_energy_setup(setup.energy_sources, IDS)
    assert again.changes == [] and again.energy_sources == setup.energy_sources, "idempotent"
    own_solar = plan_energy_setup([{"type": "solar", "stat_energy_from": "sensor.my_pv"}], IDS)
    assert [s["stat_energy_from"] for s in own_solar.energy_sources if s["type"] == "solar"] == ["sensor.my_pv"]


async def test_the_service_previews_then_saves_to_home_assistants_energy_prefs(hass: HomeAssistant, freezer, aioclient_mock):
    set_states(hass)
    assert await async_setup_component(hass, "energy", {})
    entry = await setup_entry(hass, freezer, aioclient_mock)
    manager = await async_get_manager(hass)
    await manager.async_update({"energy_sources": [GRID]})
    preview = await hass.services.async_call("hems", "setup_energy_dashboard", {"preview": True}, blocking=True, return_response=True)
    assert preview["saved"] is False and len(preview["changes"]) == 4 and len(manager.data["energy_sources"]) == 1
    done = await hass.services.async_call("hems", "setup_energy_dashboard", {}, blocking=True, return_response=True)
    assert done["saved"] and [s["type"] for s in manager.data["energy_sources"]] == ["grid", "solar", "battery"]
    assert manager.data["energy_sources"][1]["stat_energy_from"] == "sensor.hems_solar_energy"
    assert hass.states.get("sensor.hems_solar_energy").attributes["state_class"] == "total_increasing"
    assert entry.runtime_data.energy.solar_kwh == 0
