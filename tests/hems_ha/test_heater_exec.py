"""The water heater executor in Home Assistant: advisory sensor, the phase lock, and the writer against a fake water heater."""
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.hems.const import CONF_AWAY, CONF_BATH, CONF_WATER_HEATER
from custom_components.hems.engine.heater_control import HeaterCommand

from test_integration import ROLES, set_states, setup_entry

HEATER_ROLES = {**ROLES, CONF_WATER_HEATER: "water_heater.boiler", CONF_AWAY: "switch.away", CONF_BATH: "input_boolean.bath"}


def fake_heater(hass: HomeAssistant) -> list[tuple[str, str, dict]]:
    """A water heater, the away and bath toggles, and services that record every call."""
    hass.states.async_set("water_heater.boiler", "Manual", {"current_temperature": 45, "temperature": 35})
    hass.states.async_set("switch.away", "off")
    hass.states.async_set("input_boolean.bath", "on")
    calls: list[tuple[str, str, dict]] = []

    async def record(call: ServiceCall) -> None:
        calls.append((call.domain, call.service, dict(call.data)))
    for domain, service in (("water_heater", "set_operation_mode"), ("water_heater", "set_temperature"), ("input_boolean", "turn_off")):
        hass.services.async_register(domain, service, record)
    return calls


async def test_the_advisory_sensor_shows_the_target_and_the_lock_writes_nothing(hass: HomeAssistant, freezer, aioclient_mock):
    """Bath is on and the tank is at 45 °C: HEMS would set 58 °C for the bath. With the module forced to auto and armed the lock holds."""
    set_states(hass)
    calls = fake_heater(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock, roles=HEATER_ROLES, options={"water_heater_enabled": True})
    coordinator = entry.runtime_data
    coordinator.control.modes["water_heater"] = "auto"
    coordinator.control.armed = True
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.hems_water_heater_target")
    assert float(state.state) == 58 and state.attributes["program"] == "bath"
    assert calls == []


async def test_the_writer_sets_manual_then_the_temperature_and_switches_the_bath_off(hass: HomeAssistant, freezer, aioclient_mock):
    """What the writer does once phase 4 opens the lock: the add-on's two calls, only when the target differs, and the bath toggle off."""
    set_states(hass)
    calls = fake_heater(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock, roles=HEATER_ROLES, options={"water_heater_enabled": True})
    await entry.runtime_data._write_heater(HeaterCommand(58, "bath", False, None, "bath", bath_off=True))
    assert [(d, s) for d, s, _ in calls] == [("water_heater", "set_operation_mode"), ("water_heater", "set_temperature"), ("input_boolean", "turn_off")]
    assert calls[1][2]["temperature"] == 58 and calls[0][2]["operation_mode"] == "Manual"
    calls.clear()
    hass.states.async_set("water_heater.boiler", "Manual", {"current_temperature": 50, "temperature": 58})
    await entry.runtime_data._write_heater(HeaterCommand(58, "bath", False, None, "bath"))
    assert calls == [], "the same target is not written again"
