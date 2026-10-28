"""The SAJ write layer against a fake inverter: `text.set_value` and `number.set_value` services that update the entities, one
that fails, one the inverter ignores. Phase 3: the coordinator never writes, even with the battery set to auto and armed."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.hems.engine.saj_protocol import entity_names, plan_writes, wanted_inputs
from custom_components.hems.engine.saj_slots import SajSlot, Schedule
from custom_components.hems.saj import GridFollow, async_apply, missing_entities, read_inputs

from test_integration import set_states, setup_entry

NAMES = entity_names()
TZ = ZoneInfo("Europe/Amsterdam")
SCHEDULE = Schedule((SajSlot("charge", "12:00", "13:00", 50, 4.0),), (SajSlot("discharge", "17:00", "19:00", 91, 14.5),))


class FakeSaj:
    """The saj_h2_modbus input entities and their set_value services; `ignore` names entities the inverter does not take."""

    def __init__(self, hass: HomeAssistant, fail: str | None = None, ignore: set[str] | None = None) -> None:
        self.hass, self.fail, self.ignore, self.calls = hass, fail, ignore or set(), []
        for key, eid in NAMES.items():
            hass.states.async_set(eid, "00:00" if eid.startswith("text.") else "0")
        for domain in ("text", "number"):
            hass.services.async_register(domain, "set_value", self._set)

    async def _set(self, call: ServiceCall) -> None:
        """Record the call and update the entity, unless it is the failing or an ignored one."""
        eid, value = call.data["entity_id"], call.data["value"]
        self.calls.append((eid, value))
        if eid == self.fail:
            raise RuntimeError("modbus timeout")
        if eid not in self.ignore:
            self.hass.states.async_set(eid, str(value))


async def test_a_write_round_sets_the_inverter_and_a_second_round_writes_nothing(hass: HomeAssistant):
    saj = FakeSaj(hass)
    assert missing_entities(hass, NAMES) == ()
    plan = plan_writes(read_inputs(hass, NAMES), wanted_inputs(SCHEDULE), NAMES)
    result = await async_apply(hass, plan, NAMES, delay_s=0)
    assert result.ok and result.written == len(plan.writes) == 11
    assert read_inputs(hass, NAMES) == plan.target and saj.calls[-1] == ("number.saj_app_mode_input", 1)
    again = plan_writes(read_inputs(hass, NAMES), wanted_inputs(SCHEDULE), NAMES)
    assert again.writes == ()


async def test_a_failing_call_stops_the_round_before_the_masks_and_the_mode(hass: HomeAssistant):
    saj = FakeSaj(hass, fail="number.saj_charge1_power_percent_input")
    result = await async_apply(hass, plan_writes(read_inputs(hass, NAMES), wanted_inputs(SCHEDULE), NAMES), NAMES, delay_s=0, rounds=1)
    assert not result.ok and "modbus timeout" in result.error and result.written == 2
    assert ("number.saj_app_mode_input", 1) not in saj.calls


async def test_a_dropped_write_is_retried_and_only_what_still_differs_is_written_again(hass: HomeAssistant):
    """The first write of the sale's power is lost (as Modbus does now and then); the next round writes that one field again."""
    saj = FakeSaj(hass, ignore={"number.saj_discharge1_power_percent_input"})
    saj.drop_once = True
    original = saj._set

    async def flaky(call):
        if call.data["entity_id"] == "number.saj_discharge1_power_percent_input" and not saj.drop_once:
            hass.states.async_set(call.data["entity_id"], str(call.data["value"]))
        saj.drop_once = False if call.data["entity_id"] == "number.saj_discharge1_power_percent_input" else saj.drop_once
        await original(call)
    hass.services.async_register("number", "set_value", flaky)
    result = await async_apply(hass, plan_writes(read_inputs(hass, NAMES), wanted_inputs(SCHEDULE), NAMES), NAMES, attempts=1, delay_s=0)
    assert result.ok and result.written == 12 and read_inputs(hass, NAMES) == wanted_inputs(SCHEDULE)


async def test_a_value_the_inverter_does_not_take_is_a_verify_mismatch(hass: HomeAssistant):
    FakeSaj(hass, ignore={"number.saj_discharge1_power_percent_input"})
    result = await async_apply(hass, plan_writes(read_inputs(hass, NAMES), wanted_inputs(SCHEDULE), NAMES), NAMES, attempts=2, delay_s=0)
    assert not result.ok and result.error == "verify mismatch" and result.mismatches[0].startswith("discharge 1:")


async def test_missing_entities_are_named(hass: HomeAssistant):
    FakeSaj(hass)
    hass.states.async_remove("number.saj_discharge7_power_percent_input")
    assert missing_entities(hass, NAMES) == ("number.saj_discharge7_power_percent_input",)


async def test_the_grid_follow_brings_the_meter_to_zero_on_an_inverter_that_sits_500_w_off(hass: HomeAssistant):
    """House 1200 W, the SAJ delivers 500 W less than its slot asks (Mark: it sits about 500 W off). The grid-follow steps on the meter
    until it is within 50 W, then leaves the slot alone on small noise; a PV surplus clears the slot."""
    saj = FakeSaj(hass)
    follow = GridFollow()
    now = datetime(2026, 10, 28, 20, 7, tzinfo=timezone.utc)
    meter = lambda: 1200 - max(0, follow.power_w - 500)
    for _ in range(4):
        slot = follow.next_slot(now, meter(), TZ)
        if slot is None:
            break
        assert (await async_apply(hass, follow.plan(read_inputs(hass, NAMES), slot, NAMES), NAMES, delay_s=0)).ok
    assert abs(meter()) <= 50 and follow.power_w == 1700
    have = read_inputs(hass, NAMES)
    assert have.discharge[6].start == "21:00" and have.discharge[6].end == "21:15" and have.discharge_mask == 0b1000000 and have.mode == 1
    calls = len(saj.calls)
    assert follow.next_slot(now, 30, TZ) is None and len(saj.calls) == calls, "noise within 50 W writes nothing"
    clear = follow.next_slot(now, -2000, TZ)                          # surplus beyond the discharge: straight to 0
    await async_apply(hass, follow.plan(read_inputs(hass, NAMES), clear, NAMES), NAMES, delay_s=0)
    have = read_inputs(hass, NAMES)
    assert follow.power_w == 0 and have.discharge_mask == 0 and have.mode == 0


async def test_phase_3_never_writes_even_in_auto_and_armed(hass: HomeAssistant, freezer, aioclient_mock):
    """The phase lock: with the battery forced to auto and the master switch on, a cycle shows the schedule but makes no call."""
    set_states(hass)
    saj = FakeSaj(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    coordinator = entry.runtime_data
    coordinator.control.modes["battery"] = "auto"
    coordinator.control.armed = True
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert saj.calls == []
    assert not coordinator.may_write(coordinator.data.output)
    state = hass.states.get("sensor.hems_battery_schedule")
    assert state is not None and state.state.endswith("slots") and state.attributes["writes"] > 0


async def test_hems_keeps_its_own_legionella_record_from_the_tank_and_survives_a_restart(hass: HomeAssistant, freezer, aioclient_mock):
    """The tank reaches 62 °C: HEMS stamps that moment, stores it, and its sensor shows it with the due day a week later; the add-on's
    sensor is not needed (it goes)."""
    from custom_components.hems.const import CONF_WATER_HEATER
    from test_integration import ROLES
    set_states(hass)
    hass.states.async_set("water_heater.boiler", "eco", {"current_temperature": 55})
    entry = await setup_entry(hass, freezer, aioclient_mock, roles={**ROLES, CONF_WATER_HEATER: "water_heater.boiler"})
    coordinator = entry.runtime_data
    coordinator.async_sample(datetime.now(timezone.utc))
    assert coordinator.legionella_seen is None
    hass.states.async_set("water_heater.boiler", "performance", {"current_temperature": 62})
    now = datetime.now(timezone.utc)
    coordinator.async_sample(now)
    assert coordinator.legionella_seen == now and coordinator._stored()["legionella_seen"] == now.isoformat()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.hems_last_legionella")
    assert state.attributes["source"] == "tank" and state.attributes["due"] == (now.astimezone(TZ).date() + timedelta(days=7)).isoformat()



async def test_the_add_ons_last_run_is_adopted_and_kept_when_its_sensor_is_gone(hass: HomeAssistant, freezer, aioclient_mock):
    """The add-on's sensor.wh_last_legionella is a REST state that vanishes on a restart; HEMS stores the run it read from it."""
    from custom_components.hems.const import CONF_LEGIONELLA_LAST
    from test_integration import ROLES
    set_states(hass)
    hass.states.async_set("sensor.wh_last_legionella", "2026-10-17 18:30")
    entry = await setup_entry(hass, freezer, aioclient_mock, roles={**ROLES, CONF_LEGIONELLA_LAST: "sensor.wh_last_legionella"})
    coordinator = entry.runtime_data
    adopted = coordinator.legionella_last()
    from homeassistant.util import dt as dt_util
    assert adopted == datetime(2026, 10, 17, 18, 30, tzinfo=dt_util.get_default_time_zone()) and coordinator._stored()["legionella_seen"] == adopted.isoformat()
    hass.states.async_remove("sensor.wh_last_legionella")
    assert coordinator.legionella_last() == adopted and coordinator._legionella_source() == "tank"
