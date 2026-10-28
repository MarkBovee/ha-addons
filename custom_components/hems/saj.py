"""The SAJ write layer on the Home Assistant side: read the inverter's input entities, write the protocol's ordered changes
through `text.set_value` and `number.set_value`, verify by reading them back, and step the own grid-follow.

What to write comes from the engine (`saj_slots`, `saj_protocol`); this module only talks to Home Assistant. Nothing here
decides whether writing is allowed: the coordinator calls `async_apply` only in auto mode (locked in phase 3).
"""
import asyncio
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, tzinfo

from homeassistant.core import HomeAssistant

from .engine.dryrun import EngineOutput
from .engine.saj_protocol import (DAILY, EMPTY, GRID_FOLLOW_SLOT, InverterInputs, SlotInput, WritePlan, adaptive_power, mismatches,
                                  plan_writes, wanted_inputs)
from .engine.saj_slots import CHARGE, DISCHARGE, SAJ_SLOTS, PlannedQuarter, SajSlot, Schedule, SlotRules, build_schedule

_LOGGER = logging.getLogger(__name__)
VERIFY_ATTEMPTS = 6               # battery-api SCHEDULE_INPUT_VERIFY_ATTEMPTS
VERIFY_DELAY_S = 0.25             # battery-api SCHEDULE_INPUT_VERIFY_DELAY_SECONDS
WRITE_ROUNDS = 3                  # a round that does not verify is written again for what still differs (Modbus drops a write now and then)
QUARTER = timedelta(minutes=15)


@dataclass(frozen=True)
class ApplyResult:
    """What one write round did."""
    written: int
    ok: bool
    mismatches: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class SajAdvice:
    """What HEMS would write now: the schedule, the writes from the inverter's present inputs, and what is missing to write at all."""
    schedule: Schedule
    target: InverterInputs
    pending: tuple[str, ...]          # readable differences between the inverter now and the target
    writes: int                       # number of service calls a write round would make
    missing: tuple[str, ...] = field(default_factory=tuple)   # entity ids that do not exist: no write is possible


def planned_quarters(output: EngineOutput) -> list[PlannedQuarter]:
    """The plan of this cycle as slot-builder input (start, action, flows and prices per quarter)."""
    decision = output.decision
    if decision is None:
        return []
    return [PlannedQuarter(decision.slot_start + i * QUARTER, p.action, p.battery_kwh, p.grid_kwh, s.import_price, s.export_price)
            for i, (p, s) in enumerate(zip(decision.plan.slots, decision.slots))]


def _state(hass: HomeAssistant, entity_id: str) -> str | None:
    """An entity's state, None when it does not exist or has no usable value."""
    state = hass.states.get(entity_id)
    return None if state is None or state.state in ("unknown", "unavailable") else state.state


def _int(value: str | None) -> int:
    """A number entity's state as an int (the SAJ inputs are whole numbers); 0 when missing."""
    try:
        return int(float(value)) if value is not None else 0
    except ValueError:
        return 0


def _hhmm(value: str | None) -> str:
    """A text input's time as HH:MM (the integration may show seconds); 00:00 when missing."""
    return value[:5] if value and len(value) >= 5 else "00:00"


def missing_entities(hass: HomeAssistant, names: dict[str, str]) -> tuple[str, ...]:
    """The input entities that do not exist on this installation or have no value now."""
    # an entity that exists but is unavailable reads as empty: writing against that would rewrite every slot, so it counts as missing
    return tuple(sorted(eid for key, eid in names.items() if key != "app_mode" and _state(hass, eid) is None))


def read_inputs(hass: HomeAssistant, names: dict[str, str]) -> InverterInputs:
    """The inverter's present input state, as Home Assistant shows it."""
    def slots(kind: str) -> tuple[SlotInput, ...]:
        return tuple(SlotInput(_hhmm(_state(hass, names[f"{kind}{n}_start_input"])), _hhmm(_state(hass, names[f"{kind}{n}_end_input"])),
                               _int(_state(hass, names[f"{kind}{n}_power_input"])), _int(_state(hass, names[f"{kind}{n}_mask_input"])))
                     for n in range(1, SAJ_SLOTS + 1))
    return InverterInputs(slots(CHARGE), slots(DISCHARGE), _int(_state(hass, names["charge_enable_input"])),
                          _int(_state(hass, names["discharge_enable_input"])), _int(_state(hass, names["app_mode_input"])))


def advise(hass: HomeAssistant, output: EngineOutput, names: dict[str, str], tz: tzinfo, rules: SlotRules = SlotRules()) -> SajAdvice | None:
    """What a write round would do for this cycle's plan; None without a plan. Keeps the grid-follow slot as the inverter has it."""
    quarters = planned_quarters(output)
    if not quarters:
        return None
    schedule = build_schedule(quarters, tz, rules)
    missing = missing_entities(hass, names)
    have = read_inputs(hass, names)
    follow = have.discharge[GRID_FOLLOW_SLOT - 1]
    target = wanted_inputs(schedule)
    target = _with_follow(target, follow)
    plan = plan_writes(have, target, names)
    return SajAdvice(schedule, target, tuple(mismatches(have, target)), len(plan.writes), missing)


def _with_follow(target: InverterInputs, follow: SlotInput) -> InverterInputs:
    """The target with discharge slot 7 set to the grid-follow's slot, its mask bit and the mode to match."""
    discharge = target.discharge[:GRID_FOLLOW_SLOT - 1] + (follow,)
    mask = sum(1 << i for i, s in enumerate(discharge) if s.day_mask)
    on = mask or target.charge_mask
    return replace(target, discharge=discharge, discharge_mask=mask, mode=1 if on else 0)


async def async_apply(hass: HomeAssistant, plan: WritePlan, names: dict[str, str], attempts: int = VERIFY_ATTEMPTS,
                      delay_s: float = VERIFY_DELAY_S, rounds: int = WRITE_ROUNDS) -> ApplyResult:
    """Write the plan and verify it; when the inputs do not match the target, write again what still differs, up to `rounds` rounds.

    Every retry is planned from the state read back, so it only repeats what the inverter did not take, in the protocol's order."""
    written, result = 0, ApplyResult(0, True)
    for _ in range(max(1, rounds)):
        result = await _apply_once(hass, plan, names, attempts, delay_s)
        written += result.written
        if result.ok:
            return replace(result, written=written)
        plan = plan_writes(read_inputs(hass, names), plan.target, names)
        if not plan.writes:
            return ApplyResult(written, True)
    return replace(result, written=written)


async def _apply_once(hass: HomeAssistant, plan: WritePlan, names: dict[str, str], attempts: int, delay_s: float) -> ApplyResult:
    """One round: the plan's service calls in order, then read back until they match or the attempts run out.

    A failing call stops the round: later writes (the masks, the mode) depend on the slots being right."""
    written = 0
    for write in plan.writes:
        try:
            await hass.services.async_call(write.domain, "set_value", {"entity_id": write.entity_id, "value": write.value}, blocking=True)
        except Exception as err:  # noqa: BLE001 - any failure of the integration is a failed write round, reported as such
            _LOGGER.warning("HEMS SAJ write failed at %s = %s: %s", write.entity_id, write.value, err)
            return ApplyResult(written, False, (), f"{write.entity_id}: {err}")
        written += 1
    for _ in range(attempts + 1):
        left = mismatches(read_inputs(hass, names), plan.target)
        if not left:
            return ApplyResult(written, True)
        await asyncio.sleep(delay_s)
    return ApplyResult(written, False, tuple(left), "verify mismatch")


@dataclass
class GridFollow:
    """The own grid-follow (battery-manager's adaptive control): one discharge slot around the running quarter, its power stepped on
    the meter so the grid stays at 0 W. The SAJ's own self-consumption sits about 500 W off (Mark, 28 Oct 2026)."""
    max_w: int = 8000
    min_w: int = 0
    inverter_power_w: float = 8000.0
    power_w: int = 0

    def next_slot(self, now: datetime, grid_w: float | None, tz: tzinfo) -> SajSlot | None:
        """The slot after one step, or None when nothing changes. A power of 0 clears the slot (PV surplus or no house load)."""
        target = adaptive_power(grid_w, self.power_w, self.min_w, self.max_w)
        if target is None:
            return None
        self.power_w = target
        start = now.astimezone(tz).replace(minute=now.astimezone(tz).minute - now.astimezone(tz).minute % 15, second=0, microsecond=0)
        end = start + QUARTER
        pct = max(0, min(100, round(target / self.inverter_power_w * 100)))
        return SajSlot(DISCHARGE, start.strftime("%H:%M"), "23:59" if end.hour == 0 and end.minute == 0 else end.strftime("%H:%M"), pct,
                       round(target / 4000, 3))

    def plan(self, have: InverterInputs, slot: SajSlot, names: dict[str, str]) -> WritePlan:
        """The writes for the grid-follow slot alone: the other slots stay as the inverter has them."""
        follow = SlotInput(slot.start, slot.end, slot.power_pct, DAILY) if slot.power_pct else EMPTY
        return plan_writes(have, _with_follow(have, follow), names)
