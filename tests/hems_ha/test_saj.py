"""The SAJ write layer against a fake inverter: `text.set_value` and `number.set_value` services that update the entities, one
that fails, one the inverter ignores. The coordinator writes only with the battery's lock open, in auto and armed (phase 4), and
clears the slots it wrote when it lets go."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.hems.engine.saj_protocol import InverterInputs, entity_names, plan_writes, wanted_inputs
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


@pytest.fixture
def battery_unlocked(monkeypatch):
    """The battery's write lock open, as at the handover."""
    from custom_components.hems import advice, coordinator
    monkeypatch.setattr(advice, "WRITE_UNLOCKED_MODULES", frozenset({"battery"}))
    monkeypatch.setattr(coordinator, "WRITE_UNLOCKED_MODULES", frozenset({"battery"}))


async def _writing_entry(hass: HomeAssistant, freezer, aioclient_mock):
    """HEMS with the battery in auto and armed, after two cycles (the first never writes)."""
    set_states(hass)
    saj = FakeSaj(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    coordinator = entry.runtime_data
    await coordinator.async_set_mode("battery", "auto")
    await coordinator.async_set_armed(True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    return saj, coordinator


async def test_auto_writes_and_the_master_off_clears_the_slots(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """Unlocked, in auto and armed: a cycle writes the schedule. Master off: masks and mode first, then every slot back to empty."""
    saj, coordinator = await _writing_entry(hass, freezer, aioclient_mock)
    assert saj.calls and coordinator.saj_owned and read_inputs(hass, NAMES).mode == 1
    assert coordinator._stored()["saj_owned"] is True
    written = len(saj.calls)
    await coordinator.async_set_armed(False)
    cleared = saj.calls[written:]
    assert cleared[0][0] in ("number.saj_charge_time_enable_input", "number.saj_discharge_time_enable_input")
    assert read_inputs(hass, NAMES) == InverterInputs() and not coordinator.saj_owned
    await coordinator.async_refresh()
    assert len(saj.calls) == written + len(cleared), "not armed: nothing more is written"


@pytest.mark.parametrize("leave", ["advisory", "disarm_all"])
async def test_leaving_auto_clears_the_slots(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked, leave):
    saj, coordinator = await _writing_entry(hass, freezer, aioclient_mock)
    assert coordinator.saj_owned
    if leave == "disarm_all":
        await coordinator.async_disarm_all()
    else:
        await coordinator.async_set_mode("battery", leave)
    assert read_inputs(hass, NAMES) == InverterInputs() and not coordinator.saj_owned


async def test_slots_left_before_a_restart_are_cleared_and_battery_managers_are_not(hass: HomeAssistant, freezer, aioclient_mock):
    """After a restart the master is off: slots HEMS still owned go on the first cycle. Slots HEMS never wrote stay."""
    set_states(hass)
    saj = FakeSaj(hass)
    hass.states.async_set("number.saj_charge_time_enable_input", "1")       # someone else's schedule (battery-manager)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    assert saj.calls == [] and read_inputs(hass, NAMES).charge_mask == 1
    coordinator.saj_owned = True                                           # as restored from .storage
    await coordinator.async_refresh()
    assert read_inputs(hass, NAMES) == InverterInputs() and not coordinator.saj_owned


async def test_a_failing_release_keeps_the_slots_owned_for_the_next_cycle(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    saj, coordinator = await _writing_entry(hass, freezer, aioclient_mock)
    saj.fail = "number.saj_charge_time_enable_input"
    assert not await coordinator.async_release_saj("test") and coordinator.saj_owned
    saj.fail = None
    assert await coordinator.async_release_saj("test") and not coordinator.saj_owned


async def test_an_exception_in_the_write_round_does_not_stop_the_cycle(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked, monkeypatch):
    from custom_components.hems import coordinator as module

    async def boom(*args, **kwargs):
        raise RuntimeError("integration gone")
    set_states(hass)
    FakeSaj(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    coordinator = entry.runtime_data
    await coordinator.async_set_mode("battery", "auto")
    await coordinator.async_set_armed(True)
    monkeypatch.setattr(module, "async_apply", boom)
    await coordinator.async_refresh()
    assert coordinator.last_update_success and coordinator.data.saj is not None


async def test_auto_cannot_be_chosen_while_the_lock_is_closed(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """Only the battery's lock is open: its select offers auto, the others do not, and setting auto on them is refused."""
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    assert "auto" in hass.states.get("select.hems_battery_mode").attributes["options"]
    assert "auto" not in hass.states.get("select.hems_water_heater_mode").attributes["options"]
    with pytest.raises(ValueError):
        await entry.runtime_data.async_set_mode("water_heater", "auto")


async def test_locked_never_writes_even_in_auto_and_armed(hass: HomeAssistant, freezer, aioclient_mock):
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



async def test_the_legionella_role_can_be_set_while_the_add_ons_sensor_is_missing(hass: HomeAssistant, freezer, aioclient_mock):
    """After a restart sensor.wh_last_legionella is gone until the add-on posts it; the reconfigure form still takes the role."""
    from custom_components.hems.const import CONF_LEGIONELLA_LAST
    from homeassistant.data_entry_flow import FlowResultType
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    form = await entry.start_reconfigure_flow(hass)
    done = await hass.config_entries.flow.async_configure(form["flow_id"], {CONF_LEGIONELLA_LAST: "sensor.wh_last_legionella"})
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "reconfigure_successful"
    assert entry.data[CONF_LEGIONELLA_LAST] == "sensor.wh_last_legionella"


async def test_unavailable_inputs_keep_the_slots_owned(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """Audit P1: after a restart the SAJ inputs are unavailable for a while and read as empty; HEMS must not take that as cleared."""
    saj, coordinator = await _writing_entry(hass, freezer, aioclient_mock)
    await coordinator.async_set_mode("battery", "advisory")
    coordinator.saj_owned = True
    for eid in NAMES.values():
        hass.states.async_set(eid, "unavailable")
    assert not await coordinator.async_release_saj("test") and coordinator.saj_owned


async def test_a_release_waits_for_a_running_write_round(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """Audit P1: master off in the middle of a write round. The release runs after the round, so nothing of HEMS is left."""
    import asyncio
    set_states(hass)
    saj = FakeSaj(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    coordinator = entry.runtime_data
    await coordinator.async_set_mode("battery", "auto")
    await coordinator.async_set_armed(True)
    gate, started = asyncio.Event(), asyncio.Event()
    original = saj._set

    async def slow(call):
        started.set()
        await gate.wait()
        await original(call)
    for domain in ("text", "number"):
        hass.services.async_register(domain, "set_value", slow)
    cycle = hass.async_create_task(coordinator.async_refresh())
    await started.wait()
    release = hass.async_create_task(coordinator.async_set_armed(False))
    await asyncio.sleep(0)
    gate.set()
    await cycle
    await release
    assert read_inputs(hass, NAMES) == InverterInputs() and not coordinator.saj_owned


async def test_ownership_is_stored_at_once(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """Audit P1: the flag goes to .storage straight away, not after the 30 s delayed save."""
    saj, coordinator = await _writing_entry(hass, freezer, aioclient_mock)
    data = await coordinator._store.async_load()
    assert data["saj_owned"] is True


def _with_schedule(coordinator, schedule: Schedule) -> None:
    """Pin the planned slots the grid-follow keeps out of."""
    from dataclasses import replace
    coordinator.data = replace(coordinator.data, saj=replace(coordinator.data.saj, schedule=schedule))


async def _follow_entry(hass: HomeAssistant, freezer, aioclient_mock, schedule: Schedule = Schedule((), ())):
    saj, coordinator = await _writing_entry(hass, freezer, aioclient_mock)
    _with_schedule(coordinator, schedule)
    return saj, coordinator


async def test_the_grid_follow_steps_slot_7_on_the_meter_outside_the_planned_slots(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """House draws 1200 W, nothing planned now: slot 7 gets 1200 W over the running and the next quarter; the meter at 0 writes nothing."""
    saj, coordinator = await _follow_entry(hass, freezer, aioclient_mock)
    hass.states.async_set("sensor.grid_power", "1200")
    now = datetime.now(timezone.utc)
    await coordinator.async_follow_step(now)
    slot = read_inputs(hass, NAMES).discharge[6]
    local = now.astimezone(ZoneInfo(hass.config.time_zone))
    assert coordinator.follow.power_w == 1200 and slot.day_mask and slot.power_pct == 15
    assert slot.start == f"{local.hour:02d}:{local.minute - local.minute % 15:02d}"
    calls = len(saj.calls)
    hass.states.async_set("sensor.grid_power", "20")
    await coordinator.async_follow_step(now)
    assert len(saj.calls) == calls


async def test_the_grid_follow_moves_on_per_quarter_and_clears_in_a_planned_slot(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    saj, coordinator = await _follow_entry(hass, freezer, aioclient_mock)
    tz = ZoneInfo(hass.config.time_zone)
    hass.states.async_set("sensor.grid_power", "1200")
    now = datetime.now(timezone.utc)
    await coordinator.async_follow_step(now)
    first = read_inputs(hass, NAMES).discharge[6].start
    hass.states.async_set("sensor.grid_power", "0")
    later = now + timedelta(minutes=15)
    await coordinator.async_follow_step(later)
    moved = read_inputs(hass, NAMES).discharge[6]
    assert moved.start != first and moved.power_pct == 15, "same power, next quarter"
    q = later.astimezone(tz)
    start = f"{q.hour:02d}:{q.minute - q.minute % 15:02d}"
    _with_schedule(coordinator, Schedule((SajSlot("charge", start, "23:59", 50, 4.0),), ()))
    await coordinator.async_follow_step(later)
    assert read_inputs(hass, NAMES).discharge[6].day_mask == 0 and coordinator.follow.power_w == 0


async def test_the_grid_follow_stays_off_at_the_soc_floor_and_when_not_writing(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    saj, coordinator = await _follow_entry(hass, freezer, aioclient_mock)
    hass.states.async_set("sensor.grid_power", "1200")
    soc = "sensor.soc"
    hass.states.async_set(soc, "5")
    calls = len(saj.calls)
    await coordinator.async_follow_step(datetime.now(timezone.utc))
    assert len(saj.calls) == calls and coordinator.follow.power_w == 0
    hass.states.async_set(soc, "60")
    await coordinator.async_set_mode("battery", "advisory")
    calls = len(saj.calls)
    await coordinator.async_follow_step(datetime.now(timezone.utc))
    assert len(saj.calls) == calls


async def test_after_unload_starts_nothing_is_written_any_more(hass: HomeAssistant, freezer, aioclient_mock, battery_unlocked):
    """Audit P1: a follow step queued behind the unload's release must not write slot 7 again."""
    saj, coordinator = await _follow_entry(hass, freezer, aioclient_mock)
    hass.states.async_set("sensor.grid_power", "1200")
    coordinator.closing = True
    assert await coordinator.async_release_saj("unload")
    calls = len(saj.calls)
    await coordinator.async_follow_step(datetime.now(timezone.utc))
    assert len(saj.calls) == calls and not coordinator.saj_owned
