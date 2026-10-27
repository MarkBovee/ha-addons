"""The EV module (pure): plans when and how hard to charge a car, in dry-run, from prices, PV surplus and a deadline schedule.

One planner with three priced terms instead of three rule sets, so every quarter has one current and one reason:

- the *required* energy (a target SoC by the next deadline of a weekly schedule) goes to the cheapest quarters before it;
- the *opportunistic* energy (up to a higher target SoC) goes to quarters whose effective price is under an absolute
  threshold, and is the only layer when no deadline applies;
- the effective price of a quarter blends the import price and the export price: the part of the charge that PV surplus
  covers costs what the surplus would have earned on export, the rest costs the import price. Solar charging is therefore
  not a mode; it falls out of the prices, and gets more valuable when the export price drops (end of netting).

A forced charge ("I must charge, whatever the price") plans as early and as hard as allowed until the required target.

The module only proposes. It knows no charger: a current in amperes per quarter, a minimum of 6 A below which a car does
not charge, and the phase count and voltage that turn amperes into watts.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo
from typing import Mapping

from hems.contracts import Reading
from hems.prices import PriceSeries
from hems.rolling import floor_to_quarter
from hems.slots import SLOT_H, SLOT_MINUTES

QUARTER = timedelta(minutes=SLOT_MINUTES)

STATUS_OFF = "off"
STATUS_NOT_PLUGGED = "not_plugged"
STATUS_NO_SOC = "no_soc"
STATUS_PROBLEM = "problem"
STATUS_IDLE = "idle"                          # plugged, nothing to charge now or nothing worth charging
STATUS_PLANNED = "planned"                    # a plan that meets the target before the deadline
STATUS_AT_RISK = "deadline_at_risk"           # the known quarters before the deadline cannot deliver the required energy
STATUS_FORCED = "forced"                      # the owner's override: charge as early and as hard as allowed

TIER_DEADLINE, TIER_CHEAP, TIER_FORCED = "deadline", "cheap", "forced"
WEEKDAYS = 7


@dataclass(frozen=True)
class EvConfig:
    """The EV module's settings; the defaults are this installation's car (Kia EV4, 81.4 kWh) and the NEO's limits."""
    enabled: bool = False
    capacity_kwh: float = 81.4
    charge_efficiency: float = 0.90              # grid kWh to battery kWh; measure with charger kWh against the SoC jump
    target_required_pct: float = 80.0            # reached by every deadline
    target_max_pct: float = 100.0                # reached only through opportunistic quarters
    max_price_eur_kwh: float = 0.20              # opportunistic charging only when the effective price is at or under this
    solar_only: bool = False                     # opportunistic charging only where the surplus alone covers the minimum current
    min_current_a: float = 6.0                   # under this a car does not charge
    max_current_a: float = 16.0                  # the owner's ceiling, never above what the charger accepts
    phases: int = 3
    voltage_v: float = 230.0
    deadlines: tuple[time | None, ...] = (None,) * WEEKDAYS   # local time per weekday (Monday first); None = no deadline that day
    min_on_minutes: float = 10.0                 # a charge that started is not stopped sooner, unless the deadline needs it
    min_off_minutes: float = 10.0                # a stop is not undone sooner

    def power_kw(self, current_a: float) -> float:
        """The charging power for a current per phase."""
        return self.phases * self.voltage_v * current_a / 1000

    def quarter_kwh(self, current_a: float) -> float:
        """The grid energy of one quarter at a current per phase."""
        return self.power_kw(current_a) * SLOT_H


@dataclass(frozen=True)
class EvState:
    """What the planner needs to know about the car and the socket right now."""
    plugged: bool | None                         # None = unknown
    soc_pct: Reading | None
    charging: bool = False
    problem: bool = False
    force: bool = False                          # the owner's override
    last_change: datetime | None = None          # when charging last started or stopped


@dataclass(frozen=True)
class EvQuarter:
    """One planned quarter: the current per phase (0 = no charge) and what it costs."""
    start: datetime
    current_a: float
    kwh: float                                   # grid energy of the quarter
    price: float                                 # effective EUR/kWh of that energy
    surplus_kwh: float                           # PV surplus forecast for the quarter
    tier: str


@dataclass(frozen=True)
class EvPlan:
    """The plan from now on and the numbers behind it."""
    status: str
    quarters: tuple[EvQuarter, ...] = ()
    deadline: datetime | None = None
    required_kwh: float = 0.0                    # grid energy still needed for the required target
    optional_kwh: float = 0.0                    # grid energy still wanted up to the maximum target
    shortfall_kwh: float = 0.0                   # required energy the plan cannot deliver before the deadline
    reason: str = ""
    trace: dict = field(default_factory=dict)

    def planned_kwh(self) -> float:
        """The grid energy the plan delivers."""
        return sum(q.kwh for q in self.quarters)


def next_deadline(now: datetime, deadlines: tuple[time | None, ...], tz: tzinfo) -> datetime | None:
    """The first deadline after `now` of the weekly schedule, as a timezone-aware moment, or None when the schedule has none.

    A day without a time has no deadline. A deadline that already passed today does not count; the next one may be a week away."""
    local = now.astimezone(tz)
    for offset in range(WEEKDAYS + 1):
        day = local.date() + timedelta(days=offset)
        at = deadlines[day.weekday()]
        if at is None:
            continue
        moment = datetime.combine(day, at, tz)
        if moment > now:
            return moment
    return None


def _current_for(kwh: float, config: EvConfig) -> float:
    """The smallest whole current per phase that delivers `kwh` in a quarter, held between the minimum and the ceiling."""
    per_amp = config.quarter_kwh(1.0)
    return float(min(max(math.ceil(kwh / per_amp - 1e-9), config.min_current_a), config.max_current_a))


def effective_price(current_a: float, import_price: float, export_price: float, surplus_kwh: float, config: EvConfig) -> float:
    """EUR/kWh of a quarter's charge: the energy the PV surplus covers costs the export price, the rest the import price."""
    kwh = config.quarter_kwh(current_a)
    if kwh <= 0:
        return import_price
    covered = min(kwh, max(surplus_kwh, 0.0))
    return (covered * export_price + (kwh - covered) * import_price) / kwh


def required_grid_kwh(soc_pct: float, target_pct: float, config: EvConfig) -> float:
    """Grid energy to lift the battery from `soc_pct` to `target_pct`, losses included; never negative."""
    return max(target_pct - soc_pct, 0.0) / 100 * config.capacity_kwh / config.charge_efficiency


@dataclass
class _Slot:
    """A quarter while the plan is being built: what is known and how much current it already has."""
    start: datetime
    import_price: float
    export_price: float
    surplus_kwh: float
    current_a: float = 0.0
    tier: str = ""


def _fill(slots: list[_Slot], order: list[_Slot], need_kwh: float, tier: str, config: EvConfig) -> float:
    """Give `need_kwh` to the slots in `order`, a full current first; returns what could not be placed.

    A slot that already charges is topped up to the ceiling. A remainder under the minimum current's energy is rounded up to
    the minimum, because a car does not charge below it; the plan then delivers a little more than asked."""
    for slot in order:
        if need_kwh <= 1e-9:
            break
        already = config.quarter_kwh(slot.current_a)
        room = config.quarter_kwh(config.max_current_a) - already
        if room <= 1e-9:
            continue
        take = min(need_kwh, room)
        total = already + take
        slot.current_a = _current_for(total, config) if total > 0 else 0.0
        slot.tier = slot.tier or tier
        need_kwh -= config.quarter_kwh(slot.current_a) - already
    return max(need_kwh, 0.0)


def _by_price(slots: list[_Slot], config: EvConfig) -> list[_Slot]:
    """Slots cheapest first at the ceiling current; equal prices go to the later quarter (waiting is free, the car is not needed yet)."""
    key = lambda s: (effective_price(config.max_current_a, s.import_price, s.export_price, s.surplus_kwh, config), -s.start.timestamp())
    return sorted(slots, key=key)


def _deadline_horizon(slots: list[_Slot], deadline: datetime | None, config: EvConfig) -> tuple[list[_Slot], float]:
    """The slots that end before the deadline, and the energy the unknown time between the last known price and the deadline can still deliver.

    That unknown capacity lets the plan wait for prices that are not published yet instead of charging early out of caution."""
    if deadline is None:
        return list(slots), 0.0
    before = [s for s in slots if s.start + QUARTER <= deadline]
    known_end = slots[-1].start + QUARTER if slots else None
    if known_end is None or deadline <= known_end:
        return before, 0.0
    return before, (deadline - known_end) / QUARTER * config.quarter_kwh(config.max_current_a)


def plan_ev(prices: PriceSeries, surplus_kwh: Mapping[datetime, float], now: datetime, config: EvConfig, state: EvState,
            tz: tzinfo, soc_max_age: timedelta = timedelta(minutes=30)) -> EvPlan:
    """Plan the charge from the quarter containing `now` to the end of the known prices.

    The statuses say why there is no plan: off, not plugged, no (fresh) SoC, a problem at the socket. Energy is in grid kWh."""
    if not config.enabled:
        return EvPlan(STATUS_OFF, reason="module switched off")
    if state.problem:
        return EvPlan(STATUS_PROBLEM, reason="the socket reports a problem")
    if state.plugged is not True:
        return EvPlan(STATUS_NOT_PLUGGED, reason="no car is connected" if state.plugged is False else "the plug state is unknown")
    if state.soc_pct is None or not state.soc_pct.is_fresh(now, soc_max_age):
        return EvPlan(STATUS_NO_SOC, reason="no recent SoC of the car")
    soc = state.soc_pct.value
    current_quarter = floor_to_quarter(now)
    slots = [_Slot(s, i, e, surplus_kwh.get(s, 0.0)) for s, i, e in zip(prices.starts, prices.import_eur_kwh, prices.export_eur_kwh)
             if s >= current_quarter]
    required = required_grid_kwh(soc, config.target_required_pct, config)
    optional = required_grid_kwh(soc, config.target_max_pct, config) - required
    deadline = next_deadline(now, config.deadlines, tz)
    base = {"soc_pct": round(soc, 1), "required_kwh": round(required, 2), "optional_kwh": round(optional, 2),
            "deadline": deadline.isoformat() if deadline else None}
    if not slots:
        return EvPlan(STATUS_IDLE, deadline=deadline, required_kwh=required, optional_kwh=optional, reason="no price for the current quarter", trace=base)
    if state.force:
        return _forced(slots, required, optional, deadline, config, base)
    horizon, unknown_kwh = _deadline_horizon(slots, deadline, config)
    must_now = max(required - unknown_kwh, 0.0)
    left = _fill(slots, _by_price(horizon, config), must_now, TIER_DEADLINE, config)
    if optional > 1e-9:
        window = slots if deadline is None or deadline > slots[-1].start + QUARTER else horizon
        cheap = [s for s in _by_price(window, config) if _is_cheap(s, config)]
        _fill(slots, cheap, optional, TIER_CHEAP, config)
    quarters = tuple(_quarter(s, config) for s in slots if s.current_a > 0)
    status = STATUS_AT_RISK if left > 1e-9 else STATUS_PLANNED if quarters else STATUS_IDLE
    reason = _reason(status, quarters, deadline, left, config)
    return EvPlan(status, quarters, deadline, required, optional, left, reason, {**base, "shortfall_kwh": round(left, 2), "unknown_kwh": round(unknown_kwh, 2)})


def _is_cheap(slot: _Slot, config: EvConfig) -> bool:
    """Whether a quarter qualifies for opportunistic charging: its effective price at the ceiling current is under the threshold, and with `solar_only` the surplus covers the minimum current."""
    price = effective_price(config.max_current_a, slot.import_price, slot.export_price, slot.surplus_kwh, config)
    if config.solar_only and slot.surplus_kwh < config.quarter_kwh(config.min_current_a):
        return False
    return price <= config.max_price_eur_kwh + 1e-9


def _forced(slots: list[_Slot], required: float, optional: float, deadline: datetime | None, config: EvConfig, base: dict) -> EvPlan:
    """The owner's override: the required energy as early and as hard as allowed, whatever it costs."""
    left = _fill(slots, list(slots), required, TIER_FORCED, config)
    quarters = tuple(_quarter(s, config) for s in slots if s.current_a > 0)
    return EvPlan(STATUS_FORCED, quarters, deadline, required, optional, left, "forced: charging as early and as hard as allowed until the required target", {**base, "shortfall_kwh": round(left, 2)})


def _quarter(slot: _Slot, config: EvConfig) -> EvQuarter:
    """The finished slot as a plan quarter."""
    return EvQuarter(slot.start, slot.current_a, config.quarter_kwh(slot.current_a),
                     effective_price(slot.current_a, slot.import_price, slot.export_price, slot.surplus_kwh, config), slot.surplus_kwh, slot.tier)


def _reason(status: str, quarters: tuple[EvQuarter, ...], deadline: datetime | None, shortfall: float, config: EvConfig) -> str:
    """One line that says what the plan does and why, with the numbers that decided it."""
    if status == STATUS_AT_RISK:
        return f"the known quarters before the deadline cannot deliver {shortfall:.1f} kWh of the required energy"
    if not quarters:
        return "nothing to charge: the car is at the required target and no quarter is under the price threshold"
    cost = sum(q.kwh * q.price for q in quarters)
    kwh = sum(q.kwh for q in quarters)
    return f"{kwh:.1f} kWh in {len(quarters)} quarters at an average {cost / kwh:.3f} EUR/kWh" + (f", before the deadline" if deadline else "")


def ev_kwh_per_quarter(plan: EvPlan) -> dict[datetime, float]:
    """The planned grid kWh per quarter start, for the load forecast of the battery planner."""
    return {q.start: q.kwh for q in plan.quarters}


@dataclass(frozen=True)
class EvSetpoint:
    """What would be sent to the charger now, after the hysteresis and the grid limit, and what limited it."""
    current_a: float
    planned_a: float
    code: str
    reason: str


def setpoint(plan: EvPlan, now: datetime, state: EvState, config: EvConfig, allowed_a: float | None = None) -> EvSetpoint:
    """The current for the present quarter: the plan's, held by the minimum on and off times, capped by the balancer's `allowed_a`.

    The minimum times never delay a plan that is urgent (at risk or forced). Under the minimum current the answer is zero, because a
    car does not charge below it and a pause is the honest request."""
    current = next((q.current_a for q in plan.quarters if q.start <= now < q.start + QUARTER), 0.0)
    planned, code, reason = current, "as_planned", plan.reason
    urgent = plan.status in (STATUS_AT_RISK, STATUS_FORCED)
    since = (now - state.last_change).total_seconds() / 60 if state.last_change else math.inf
    if not urgent and state.charging and current <= 0 and since < config.min_on_minutes:
        current, code, reason = config.min_current_a, "hold_min_on", f"charging for {since:.0f} min, keeping on until {config.min_on_minutes:.0f}"
    elif not urgent and not state.charging and current > 0 and since < config.min_off_minutes:
        current, code, reason = 0.0, "hold_min_off", f"stopped {since:.0f} min ago, staying off until {config.min_off_minutes:.0f}"
    if allowed_a is not None and current > allowed_a:
        current, code, reason = allowed_a, "limited_by_grid", f"the grid limit leaves {allowed_a:.0f} A"
    if 0 < current < config.min_current_a:
        current = 0.0
        code = code if code != "as_planned" else "below_minimum"
    return EvSetpoint(current, planned, code, reason)
