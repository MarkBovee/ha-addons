"""SAJ time slots from the battery plan: what HEMS writes to the inverter in Time-of-use mode.

A SAJ slot is a daily repeating window (start, end, one power as a percentage of the inverter's rated power); there are seven
for charging and seven for discharging. Outside a slot the inverter does self-consumption, which HEMS trims to 0 W at the
meter with its own grid-follow (that uses one discharge slot, so six are left for sales).

The builder takes the plan of the coming 24 hours, groups the charge and the sale quarters into pieces, and merges pieces of
the same kind when the gap is short and merging costs little (the slot study of 28 Oct 2026: median EUR 0.014 a day). When
more pieces remain than there are slots, it keeps merging the cheapest gap. A piece over local midnight is split in two,
because it is not known that the SAJ accepts an end before its start. Pure: no I/O, no clock.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from hems.slots import SLOT_H

QUARTER = timedelta(minutes=15)
HORIZON = 96                    # quarters: slots repeat daily, so one day ahead is all a slot can describe
SAJ_SLOTS = 7                   # per direction
CHARGE, DISCHARGE = "charge", "discharge"


@dataclass(frozen=True)
class SlotRules:
    """Settings of the builder."""
    inverter_power_w: float = 8000.0       # 100 % of a slot's power (battery-api `modbus_inverter_power_w`)
    max_gap_quarters: int = 2              # a gap of at most this many quarters may be filled when it is cheap
    max_cost_per_slot: float = 0.05        # EUR: filling such a gap is fine below this per slot saved
    charge_slots: int = SAJ_SLOTS
    discharge_slots: int = SAJ_SLOTS - 1   # one discharge slot stays free for the grid-follow


@dataclass(frozen=True)
class PlannedQuarter:
    """One quarter of the plan as the builder needs it."""
    start: datetime                        # UTC
    action: str                            # charge | discharge | idle (the planner's action: beyond self-consumption)
    battery_kwh: float                     # AC, + charge / - discharge
    grid_kwh: float                        # + import / - export
    import_price: float
    export_price: float


@dataclass(frozen=True)
class SajSlot:
    """One slot as it is written: local time of day, power in percent."""
    kind: str
    start: str                             # "HH:MM" local
    end: str                               # "HH:MM" local, exclusive; "23:59" for a slot that ends at midnight
    power_pct: int
    kwh: float                             # AC energy the slot moves at that power


@dataclass(frozen=True)
class Merge:
    """A filled gap, for the log: which kind, where, and what it costs against the plan."""
    kind: str
    start: datetime
    end: datetime
    cost_eur: float
    forced: bool                           # True when merged only to stay within the slot count


@dataclass(frozen=True)
class Schedule:
    """The slots to write and how they came about."""
    charge: tuple[SajSlot, ...]
    discharge: tuple[SajSlot, ...]
    merges: tuple[Merge, ...] = ()
    dropped: tuple[str, ...] = field(default_factory=tuple)   # pieces left out because nothing could be merged; should stay empty

    @property
    def merge_cost_eur(self) -> float:
        """What the merges cost against the plan, in total."""
        return round(sum(m.cost_eur for m in self.merges), 3)


@dataclass
class _Piece:
    """A run of quarters of one kind, as indices into the plan (last inclusive)."""
    kind: str
    first: int
    last: int


def _marginal_price(q: PlannedQuarter) -> float:
    """What one kWh moved in this quarter costs or earns: import where the plan imports, export where it exports."""
    return q.import_price if q.grid_kwh > 0 else q.export_price


def _block_cost(quarters: list[PlannedQuarter], first: int, last: int) -> float:
    """Extra cost of running quarters first..last at one constant power instead of the planned powers."""
    block = quarters[first:last + 1]
    even = sum(q.battery_kwh for q in block) / len(block)
    return sum((even - q.battery_kwh) * _marginal_price(q) for q in block)


def _merge_cost(quarters: list[PlannedQuarter], a: _Piece, b: _Piece) -> float:
    """What merging two pieces into one slot adds to the cost of running each at its own constant power."""
    return _block_cost(quarters, a.first, b.last) - _block_cost(quarters, a.first, a.last) - _block_cost(quarters, b.first, b.last)


def _pieces(quarters: list[PlannedQuarter]) -> list[_Piece]:
    """Runs of charge and of discharge quarters."""
    out: list[_Piece] = []
    for i, q in enumerate(quarters):
        # a quarter only becomes a slot when its flow goes the slot's way: a mislabelled quarter must never write a backwards slot
        if not ((q.action == CHARGE and q.battery_kwh > 0) or (q.action == DISCHARGE and q.battery_kwh < 0)):
            continue
        if out and out[-1].kind == q.action and out[-1].last == i - 1:
            out[-1].last = i
        else:
            out.append(_Piece(q.action, i, i))
    return out


def _mergeable(quarters: list[PlannedQuarter], pieces: list[_Piece], i: int) -> bool:
    """True when piece i and the next piece of the same kind have only idle quarters between them."""
    a, b = pieces[i], pieces[i + 1]
    return a.kind == b.kind and all(q.action == "idle" for q in quarters[a.last + 1:b.first])


def _merge_at(pieces: list[_Piece], i: int) -> None:
    """Join piece i with piece i + 1."""
    pieces[i].last = pieces[i + 1].last
    del pieces[i + 1]


def _gap_candidates(quarters: list[PlannedQuarter], pieces: list[_Piece], kind: str, max_gap: int | None) -> list[tuple[float, int]]:
    """(cost, index) of every gap of `kind` that may be filled, cheapest first; max_gap None = any length."""
    found = []
    for i in range(len(pieces) - 1):
        if pieces[i].kind != kind or not _mergeable(quarters, pieces, i):
            continue
        gap = pieces[i + 1].first - pieces[i].last - 1
        if max_gap is None or gap <= max_gap:
            found.append((_merge_cost(quarters, pieces[i], pieces[i + 1]), i))
    return sorted(found)


def _fill_gaps(quarters: list[PlannedQuarter], pieces: list[_Piece], kind: str, limit: int, rules: SlotRules) -> tuple[list[Merge], list[str]]:
    """Merge cheap short gaps, then the cheapest gaps until the pieces of `kind` fit in `limit`; returns the merges and what was dropped."""
    merges: list[Merge] = []
    while True:
        cheap = [c for c in _gap_candidates(quarters, pieces, kind, rules.max_gap_quarters) if c[0] < rules.max_cost_per_slot]
        if not cheap:
            break
        cost, i = cheap[0]
        merges.append(Merge(kind, quarters[pieces[i].last].start + QUARTER, quarters[pieces[i + 1].first].start, round(cost, 3), False))
        _merge_at(pieces, i)
    dropped: list[str] = []
    while sum(p.kind == kind for p in pieces) > limit:
        any_gap = _gap_candidates(quarters, pieces, kind, None)
        if any_gap:
            cost, i = any_gap[0]
            merges.append(Merge(kind, quarters[pieces[i].last].start + QUARTER, quarters[pieces[i + 1].first].start, round(cost, 3), True))
            _merge_at(pieces, i)
            continue
        # nothing joinable (an opposite action sits between every pair): leave out the piece that moves the least energy
        smallest = min((p for p in pieces if p.kind == kind), key=lambda p: abs(sum(q.battery_kwh for q in quarters[p.first:p.last + 1])))
        dropped.append(f"{kind} {quarters[smallest.first].start.isoformat()}")
        pieces.remove(smallest)
    return merges, dropped


def _hhmm(moment: datetime) -> str:
    """Local time of day as the SAJ text input wants it."""
    return moment.strftime("%H:%M")


def _to_slots(quarters: list[PlannedQuarter], piece: _Piece, tz: tzinfo, rules: SlotRules) -> list[SajSlot]:
    """One piece as SAJ slots: split at local midnight, power the block's average as a percentage; an empty piece gives none."""
    block = quarters[piece.first:piece.last + 1]
    energy = abs(sum(q.battery_kwh for q in block))
    power_w = energy / (len(block) * SLOT_H) * 1000
    pct = max(0, min(100, round(power_w / rules.inverter_power_w * 100)))
    if pct == 0:
        return []
    start = block[0].start.astimezone(tz)
    end = (block[-1].start + QUARTER).astimezone(tz)
    parts = [(start, end)]
    if end.date() != start.date() and end.time() != datetime.min.time():
        midnight = end.replace(hour=0, minute=0)
        parts = [(start, midnight), (midnight, end)]
    out = []
    for a, b in parts:
        share = (b - a) / (end - start)
        out.append(SajSlot(piece.kind, _hhmm(a), "23:59" if b.time() == datetime.min.time() else _hhmm(b), pct, round(energy * share, 3)))
    return out


def build_schedule(quarters: list[PlannedQuarter], tz: tzinfo, rules: SlotRules = SlotRules()) -> Schedule:
    """The SAJ slots for the coming 24 hours of the plan (see the module docstring)."""
    ahead = quarters[:HORIZON]
    pieces = _pieces(ahead)
    merges, dropped = [], []
    for kind, limit in ((CHARGE, rules.charge_slots), (DISCHARGE, rules.discharge_slots)):
        m, d = _fill_gaps(ahead, pieces, kind, limit, rules)
        merges += m
        dropped += d
    slots = [s for p in pieces for s in _to_slots(ahead, p, tz, rules)]
    # a midnight split can add a slot; the count is checked again on the final slots
    charge = tuple(s for s in slots if s.kind == CHARGE)[:rules.charge_slots]
    discharge = tuple(s for s in slots if s.kind == DISCHARGE)[:rules.discharge_slots]
    lost = [f"{s.kind} {s.start}" for s in slots if s not in charge and s not in discharge]
    return Schedule(charge, discharge, tuple(merges), tuple(dropped + lost))
