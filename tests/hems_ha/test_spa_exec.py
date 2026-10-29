"""The spa module in Home Assistant: advisory target, giving way on a full phase, the phase lock and the writer."""
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.hems.const import CONF_EV_CURRENTS, CONF_METER_CURRENTS, CONF_METER_EXPORTS, CONF_SPA
from custom_components.hems.engine.spa import SpaTarget

from test_integration import ROLES, set_states, setup_entry

METER = {**{r: f"sensor.meter_l{i + 1}" for i, r in enumerate(CONF_METER_CURRENTS)},
         **{r: f"sensor.export_l{i + 1}" for i, r in enumerate(CONF_METER_EXPORTS)},
         **{r: f"sensor.car_l{i + 1}" for i, r in enumerate(CONF_EV_CURRENTS)}}
SPA_ROLES = {**ROLES, CONF_SPA: "climate.spa", **METER}
SPA_ON = {"spa_enabled": True, "spa_phase": "l2"}


def fake_spa(hass: HomeAssistant, water: float = 36.0, l2_a: float = 5.0) -> list[dict]:
    """A Balboa-like climate below its band, per-phase meter readings, and a recorded climate.set_temperature."""
    hass.states.async_set("climate.spa", "heat", {"current_temperature": water, "temperature": 38.0, "hvac_action": "idle"})
    for i, amps in enumerate((5.0, l2_a, 5.0)):
        hass.states.async_set(f"sensor.meter_l{i + 1}", str(amps))
        hass.states.async_set(f"sensor.export_l{i + 1}", "0")
        hass.states.async_set(f"sensor.car_l{i + 1}", "0")
    calls: list[dict] = []

    async def record(call: ServiceCall) -> None:
        calls.append(dict(call.data))
    hass.services.async_register("climate", "set_temperature", record)
    return calls


async def test_a_cold_spa_gets_the_top_of_the_band_and_the_lock_writes_nothing(hass: HomeAssistant, freezer, aioclient_mock):
    set_states(hass)
    calls = fake_spa(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock, roles=SPA_ROLES, options=SPA_ON)
    coordinator = entry.runtime_data
    coordinator.control.modes["spa"] = "auto"
    coordinator.control.armed = True
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.hems_spa_target")
    assert float(state.state) == 38.5 and state.attributes["heat"] is True and "below the band" in state.attributes["reason"]
    assert calls == []


async def test_the_spa_gives_way_when_its_phase_is_full(hass: HomeAssistant, freezer, aioclient_mock):
    """L2 already draws 20 A of a 24 A ceiling (25 A minus 1 A margin): the 13 A heater does not fit, the spa pauses at the bottom of the band."""
    set_states(hass)
    fake_spa(hass, l2_a=20.0)
    entry = await setup_entry(hass, freezer, aioclient_mock, roles=SPA_ROLES, options=SPA_ON)
    assert not entry.runtime_data.spa_allowed(entry.runtime_data._settings, 0.0)
    state = hass.states.get("sensor.hems_spa_target")
    assert float(state.state) == 37.0 and "phase is full" in state.attributes["reason"]


async def test_the_writer_sets_only_the_temperature_and_only_when_it_differs(hass: HomeAssistant, freezer, aioclient_mock):
    set_states(hass)
    calls = fake_spa(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock, roles=SPA_ROLES, options=SPA_ON)
    await entry.runtime_data._write_spa(SpaTarget(38.5, True, "test"))
    await entry.runtime_data._write_spa(SpaTarget(38.0, False, "same as now"))
    assert calls == [{"entity_id": "climate.spa", "temperature": 38.5}]
