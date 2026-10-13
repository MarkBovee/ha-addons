from datetime import datetime, timedelta, timezone

import pytest
from test_rolling import recorded_day

from hems.battery import BatteryConfig, Plan, Slot
from hems.contracts import BatteryCommand, Reading
from hems.executor import (AS_PLANNED, AT_FLOOR, AT_FULL, EXPIRED, LIMITED_FLOOR, LIMITED_FULL, NO_PLAN, NO_SOC, STALE_SOC, execute)
from hems.forecast import LOCAL_TZ
from hems.rolling import Decision, HorizonInputs, plan_next

START = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
CFG = BatteryConfig()                      # 25 kWh, reserve 30 %, hard minimum 5 %, round trip 0.82


def decision(power_w: float, slot: Slot | None = None) -> Decision:
    """A decision for the quarter starting at START with one command, without a real plan behind it."""
    return Decision(START, BatteryCommand(START, START + timedelta(minutes=15), power_w), Plan(), {}, (slot or Slot(0.30, 0.20),))


def live(soc_pct: float, seconds_ago: int = 5, at: datetime = START) -> Reading:
    """A SoC reading observed `seconds_ago` before `at`."""
    return Reading(soc_pct, at - timedelta(seconds=seconds_ago))


def test_an_idle_command_always_passes_even_without_a_soc():
    """Holding needs no SoC: nothing is moved, so there is nothing to check."""
    out = execute(decision(0), START, None, CFG)
    assert (out.power_w, out.code, out.overridden) == (0, AS_PLANNED, False)


def test_a_discharge_with_room_above_the_floor_passes_unchanged():
    """60 % with a 30 % floor holds 7.5 kWh: a quarter at 7 kW needs 1.9 kWh, so it runs as planned."""
    out = execute(decision(-7000), START, live(60), CFG)
    assert (out.power_w, out.planned_w, out.code, out.overridden) == (-7000, -7000, AS_PLANNED, False)


def test_a_discharge_is_refused_at_or_below_the_floor():
    """The planner may have been right a moment ago; with the live SoC on the reserve the executor holds."""
    at_floor, below = execute(decision(-7000), START, live(30.0), CFG), execute(decision(-7000), START, live(24.0), CFG)
    assert (at_floor.power_w, at_floor.code) == (0, AT_FLOOR) and (below.power_w, below.code) == (0, AT_FLOOR)
    assert at_floor.planned_w == -7000 and at_floor.overridden and "floor 30%" in at_floor.reason


def test_a_discharge_is_slowed_to_what_is_left_above_the_floor_for_the_rest_of_the_quarter():
    """0.5 % above the floor is 0.125 kWh in the cells, 0.113 kWh at the AC side: at the start of the quarter that is about 450 W."""
    out = execute(decision(-7000), START, live(30.5), CFG)
    assert out.code == LIMITED_FLOOR and -460 <= out.power_w <= -440 and out.planned_w == -7000
    later = execute(decision(-7000), START + timedelta(minutes=10), live(30.5, at=START + timedelta(minutes=10)), CFG)
    assert later.code == LIMITED_FLOOR and later.power_w < out.power_w < 0      # less time left, so a higher power fits (more negative)


def test_the_floor_is_the_reserve_or_the_hard_minimum_of_that_quarter():
    """A slot with a lower reserve allows a deeper discharge, but never below the hard minimum."""
    deep = Slot(0.30, 0.20, reserve_soc=0.0)                         # clamped to the 5 % hard minimum
    assert execute(decision(-7000, deep), START, live(20.0), CFG).code == AS_PLANNED
    assert execute(decision(-7000, deep), START, live(5.0), CFG).code == AT_FLOOR


def test_a_charge_is_refused_when_full_and_slowed_when_nearly_full():
    """100 % has no room; 99 % has 0.25 kWh of room, which at the AC side is 0.276 kWh, about 1.1 kW over a full quarter."""
    assert (execute(decision(7000), START, live(100.0), CFG).code, execute(decision(7000), START, live(100.0), CFG).power_w) == (AT_FULL, 0)
    nearly = execute(decision(7000), START, live(99.0), CFG)
    assert nearly.code == LIMITED_FULL and 1000 <= nearly.power_w <= 1200
    assert execute(decision(7000), START, live(40.0), CFG).code == AS_PLANNED


def test_a_command_is_held_without_a_trustworthy_soc():
    """No reading, or one that stopped updating, holds the battery instead of acting on a guess."""
    assert (execute(decision(-7000), START, None, CFG).code, execute(decision(-7000), START, None, CFG).power_w) == (NO_SOC, 0)
    stale = execute(decision(-7000), START, live(60, seconds_ago=20 * 60), CFG)
    assert (stale.code, stale.power_w) == (STALE_SOC, 0) and "1200 s" in stale.reason


def test_a_decision_for_another_quarter_is_not_executed():
    """When the replan fails the old decision must not keep running into the next quarter."""
    later = START + timedelta(minutes=17)
    assert execute(decision(-7000), later, live(60, at=later), CFG).code == EXPIRED
    assert execute(decision(-7000), START - timedelta(seconds=1), live(60), CFG).code == EXPIRED


def test_the_old_decision_survives_the_seconds_before_the_replan_arrives():
    """The planner runs 20 s past the quarter boundary: an SoC update in between must not flip the executor to expired every quarter."""
    boundary = START + timedelta(minutes=15)
    for seconds in (0, 20, 60, 89):
        now = boundary + timedelta(seconds=seconds)
        out = execute(decision(-7000), now, live(60, at=now), CFG)
        assert out.code == AS_PLANNED and out.power_w == -7000, seconds
    late = boundary + timedelta(seconds=91)
    assert execute(decision(-7000), late, live(60, at=late), CFG).code == EXPIRED
    at_floor = boundary + timedelta(seconds=30)
    assert execute(decision(-7000), at_floor, live(30.0, at=at_floor), CFG).code == AT_FLOOR      # the floor still holds in the grace seconds


def test_no_decision_sends_nothing():
    """The planner status (no SoC, no prices) is the reason; the executor only reports that there was nothing to run."""
    out = execute(None, START, live(60), CFG)
    assert (out.power_w, out.planned_w, out.code) == (0, 0, NO_PLAN)


@pytest.mark.parametrize("hour", [0, 3, 6, 9, 12, 15, 18, 21])
@pytest.mark.parametrize("soc_pct", [5, 30, 31, 50, 95, 100])
def test_the_planners_own_command_passes_the_executor_when_the_soc_is_what_it_planned_from(hour: int, soc_pct: int):
    """Planner and executor share the floor: a plan made from the live SoC is never refused, so only a change since then is."""
    now = datetime(2026, 10, 6, hour, 7, tzinfo=LOCAL_TZ)
    d = plan_next(HorizonInputs(now, soc_pct / 100 * CFG.capacity_kwh, recorded_day("2026-10-06"), {}, {}), CFG)
    out = execute(d, d.slot_start, Reading(soc_pct, d.slot_start), CFG)
    assert not out.overridden, (hour, soc_pct, out)
