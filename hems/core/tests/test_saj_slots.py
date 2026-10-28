"""The SAJ slot builder on the plans HEMS really made (afternoon plans of 26 and 28 Oct 2026) and on small made-up plans."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from hems.saj_slots import PlannedQuarter, SlotRules, build_schedule

TZ = ZoneInfo("Europe/Amsterdam")
FIXTURE = Path(__file__).parent / "fixtures" / "plans_afternoon_2026_10_26_28.json"
LETTER = {"c": "charge", "d": "discharge", "i": "idle"}


def logged(day: str) -> list[PlannedQuarter]:
    """A logged afternoon plan as builder input."""
    plan = json.loads(FIXTURE.read_text())[day]
    start = datetime.fromisoformat(plan["start"])
    return [PlannedQuarter(start + k * timedelta(minutes=15), LETTER[a], w / 4000, g, i, e)
            for k, (a, w, g, i, e) in enumerate(zip(plan["a"], plan["w"], plan["grid"], plan["imp"], plan["exp"]))]


def made_up(actions: str, power_w: float = 8000, start: datetime = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)) -> list[PlannedQuarter]:
    """A plan from action letters at one power, flat prices."""
    sign = {"c": 1, "d": -1, "i": 0}
    return [PlannedQuarter(start + k * timedelta(minutes=15), LETTER[a], sign[a] * power_w / 4000, -sign[a] * power_w / 4000, 0.30, 0.30)
            for k, a in enumerate(actions)]


def test_the_plan_of_28_oct_fits_with_cheap_merges_and_never_more_than_the_slots():
    """28 Oct 14:00: the planner charged in single quarters (6 charge and 4 discharge pieces). The builder fills the short gaps it can for
    little money and stays within 7 charge and 6 sell slots; nothing is dropped."""
    schedule = build_schedule(logged("1028"), TZ)
    assert len(schedule.charge) <= 7 and len(schedule.discharge) <= 6 and not schedule.dropped
    assert schedule.merge_cost_eur < 0.5 and all(m.cost_eur < 0.05 for m in schedule.merges if not m.forced)
    assert all(0 < s.power_pct <= 100 for s in schedule.charge + schedule.discharge)


def test_the_plan_of_26_oct_with_seven_charge_pieces_leaves_room():
    """26 Oct 14:00 needed 7 charge slots as planned; after the cheap merges it needs fewer."""
    schedule = build_schedule(logged("1026"), TZ)
    assert len(schedule.charge) < 7 and not schedule.dropped


def test_a_one_quarter_pause_in_a_sale_is_filled_at_flat_prices():
    """Flat prices: filling a pause costs nothing, so a sale with one idle quarter becomes one slot at the average power."""
    schedule = build_schedule(made_up("ddddiddd"), TZ)
    slot, = schedule.discharge
    assert (slot.start, slot.end) == ("16:00", "18:00") and slot.power_pct == round(7 / 8 * 100)
    assert schedule.merges[0].cost_eur == 0


def test_too_many_pieces_are_merged_cheapest_first_down_to_the_limit():
    """Eight sale pieces with long gaps: the builder must merge (forced) until six remain for sales, one slot stays for the grid-follow."""
    schedule = build_schedule(made_up("diii" * 8), TZ, SlotRules(max_gap_quarters=0))
    assert len(schedule.discharge) == 6 and any(m.forced for m in schedule.merges) and not schedule.dropped


def test_a_piece_over_midnight_is_split_in_two_slots():
    """22:30 to 01:30 local: two slots, the first ends at 23:59 (an end before the start is not known to be accepted)."""
    start = datetime(2026, 10, 28, 22, 30, tzinfo=TZ).astimezone(timezone.utc)
    schedule = build_schedule(made_up("cccccccccccc", 4000, start), TZ)
    assert [(s.start, s.end) for s in schedule.charge] == [("22:30", "23:59"), ("00:00", "01:30")]
    assert all(s.power_pct == 50 for s in schedule.charge)


def test_an_opposite_action_in_the_gap_is_never_merged_over():
    """A charge between two sales: the sales stay two slots, the charge one."""
    schedule = build_schedule(made_up("ddicidd"), TZ)
    assert len(schedule.discharge) == 2 and len(schedule.charge) == 1


def test_only_the_coming_24_hours_become_slots():
    """Slots repeat daily: a sale 25 h ahead is not written now."""
    schedule = build_schedule(made_up("i" * 100 + "dd"), TZ)
    assert schedule.discharge == ()


def test_the_audit_case_never_becomes_a_charge_slot_while_the_battery_discharges():
    """Audit 28 Oct 2026: two expensive quarters with a big house load, then two cheaper ones, SoC 3.75 kWh. Before the fix the plan
    labelled a partial cover 'charge' and the builder made a 34 % charge slot of it; now the battery covers the house and no slot runs backwards."""
    from hems.battery import BatteryConfig, Slot, plan
    slots = [Slot(0.40, 0.40, 2.0, 0.0)] * 2 + [Slot(0.45, 0.45, 0.5, 0.0)] * 2
    result = plan(slots, 3.75, BatteryConfig())
    start = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
    quarters = [PlannedQuarter(start + k * timedelta(minutes=15), p.action, p.battery_kwh, p.grid_kwh, s.import_price, s.export_price)
                for k, (p, s) in enumerate(zip(result.slots, slots))]
    charging = {q.start.astimezone(TZ).strftime("%H:%M") for q in quarters if q.battery_kwh > 0}
    assert all(s.start in charging for s in build_schedule(quarters, TZ).charge), "a charge slot only where the battery charges"
    assert quarters[0].battery_kwh < 0 and "12:00" not in charging
    mislabelled = [PlannedQuarter(start, "charge", -1.358, 0.6, 0.40, 0.40)]
    assert build_schedule(mislabelled, TZ).charge == (), "the builder's own guard: a charge slot only for a charging quarter"
