"""battery-api's SAJ write protocol as HEMS uses it: names, wanted inputs, ordered writes, verify, and the grid-follow step."""
from hems.saj_protocol import (DAILY, EMPTY, GRID_FOLLOW_SLOT, MODE_SELF_CONSUMPTION, MODE_TIME_OF_USE, InverterInputs, SlotInput,
                               adaptive_power, entity_names, mismatches, plan_writes, wanted_inputs)
from hems.saj_slots import SajSlot, Schedule

NAMES = entity_names()
SALE = SajSlot("discharge", "17:00", "19:00", 91, 14.5)
CHARGE = SajSlot("charge", "12:00", "13:00", 50, 4.0)


def test_entity_names_follow_battery_api():
    """Write entities as battery-api resolves them on this server (live-transition-plan §4.1)."""
    assert NAMES["charge1_start_input"] == "text.saj_charge1_start_time_time"
    assert NAMES["discharge7_power_input"] == "number.saj_discharge7_power_percent_input"
    assert NAMES["charge_enable_input"] == "number.saj_charge_time_enable_input" and NAMES["app_mode_input"] == "number.saj_app_mode_input"


def test_a_schedule_becomes_slots_masks_and_time_of_use():
    want = wanted_inputs(Schedule((CHARGE,), (SALE,)))
    assert want.charge[0] == SlotInput("12:00", "13:00", 50, DAILY) and want.charge[1] == EMPTY
    assert want.discharge[0] == SlotInput("17:00", "19:00", 91, DAILY) and want.discharge[GRID_FOLLOW_SLOT - 1] == EMPTY
    assert (want.charge_mask, want.discharge_mask, want.mode) == (1, 1, MODE_TIME_OF_USE)
    assert wanted_inputs(Schedule((), ())).mode == MODE_SELF_CONSUMPTION


def test_the_grid_follow_owns_discharge_slot_seven_and_sales_never_take_it():
    sales = tuple(SajSlot("discharge", f"{h:02d}:00", f"{h:02d}:15", 90, 1.0) for h in range(10, 18))     # 8 sales offered
    follow = SajSlot("discharge", "21:00", "21:15", 6, 0.1)
    want = wanted_inputs(Schedule((), sales), follow)
    assert want.discharge[5].start == "15:00" and want.discharge[6] == SlotInput("21:00", "21:15", 6, DAILY)
    assert want.discharge_mask == 0b1111111


def test_writes_go_fields_then_masks_then_mode_and_only_what_differs():
    plan = plan_writes(InverterInputs(), wanted_inputs(Schedule((CHARGE,), ())), NAMES)
    ids = [w.entity_id for w in plan.writes]
    assert ids == ["text.saj_charge1_start_time_time", "text.saj_charge1_end_time_time", "number.saj_charge1_power_percent_input",
                   "number.saj_charge1_day_mask_input", "number.saj_charge_time_enable_input", "number.saj_app_mode_input"]
    assert plan_writes(plan.target, plan.target, NAMES).writes == (), "idempotent"


def test_a_slot_that_ends_is_cleared_to_battery_apis_empty_values():
    have = wanted_inputs(Schedule((CHARGE,), ()))
    plan = plan_writes(have, wanted_inputs(Schedule((), ())), NAMES)
    assert [(w.entity_id, w.value) for w in plan.writes] == [
        ("text.saj_charge1_start_time_time", "00:00"), ("text.saj_charge1_end_time_time", "00:00"),
        ("number.saj_charge1_power_percent_input", 0), ("number.saj_charge1_day_mask_input", 0),
        ("number.saj_charge_time_enable_input", 0), ("number.saj_app_mode_input", MODE_SELF_CONSUMPTION)]


def test_mismatches_name_what_the_inverter_did_not_take():
    want = wanted_inputs(Schedule((CHARGE,), ()))
    assert mismatches(want, want) == []
    assert mismatches(InverterInputs(), want)[0].startswith("charge 1: have 00:00-00:00 0% mask 0, want 12:00-13:00 50%")


def test_the_grid_follow_step_is_battery_managers():
    """battery-manager `_calculate_adaptive_power`: within 50 W nothing, round to 100 W, under 100 W change nothing, never above the maximum."""
    assert adaptive_power(None, 500) is None and adaptive_power(40, 500) is None
    assert adaptive_power(520, 0) == 500, "the SAJ sits about 500 W off: the meter says 520 W import, so discharge 500 W"
    assert adaptive_power(-480, 1000) == 500 and adaptive_power(120, 500) == 600 and adaptive_power(-60, 500) == 400 and adaptive_power(70, 530) is None
    assert adaptive_power(-900, 500) == 0, "export: stop discharging, PV may charge"
    assert adaptive_power(9000, 1000) == 8000
