"""The dashboard's view of one cycle: everything the HEMS panel draws, as one JSON-ready dict.

It is sent over the websocket (hems/subscribe) and never stored, so the full horizon (up to 192 quarters) does not
land in the recorder. Times are UTC ISO strings; the panel formats them in local time. Nothing here decides anything.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from .engine.rolling import Decision
from .engine.windows import record

QUARTER = timedelta(minutes=15)
PAYLOAD_VERSION = 1
PLAN_STALE_S = 20 * 60          # one cycle plus margin: an older plan is drawn as stale
LIVE_STALE_S = 2 * 60           # live power readings
PRICES_STALE_S = 25 * 3600      # the market series is refreshed at least daily


def _iso(moment: datetime | None) -> str | None:
    """UTC ISO time, or None."""
    return moment.astimezone(timezone.utc).isoformat() if moment else None


def _r(value: float | None, digits: int) -> float | None:
    """Round when there is a value."""
    return None if value is None else round(value, digits)


def plan_diff(current: Decision | None, previous: Decision | None) -> dict[str, Any]:
    """What changed between the previous cycle's plan and this one, over the quarters both cover.

    `changed` counts quarters whose action differs; `runs` merges neighbouring changed quarters into stretches with the
    old and new action; `previous_soc` is the previous SoC trajectory keyed by quarter (UTC ISO), for a ghost line."""
    if current is None or previous is None:
        return {"available": False, "changed": 0, "runs": [], "previous_soc": {}, "previous_at": None}
    old = {previous.slot_start + i * QUARTER: s for i, s in enumerate(previous.plan.slots)}
    runs: list[dict[str, Any]] = []
    changed = 0
    for i, slot in enumerate(current.plan.slots):
        at = current.slot_start + i * QUARTER
        was = old.get(at)
        if was is None or was.action == slot.action:
            continue
        changed += 1
        last = runs[-1] if runs else None
        if last and last["to"] == _iso(at) and last["was"] == was.action and last["now"] == slot.action:
            last["to"] = _iso(at + QUARTER)
        else:
            runs.append({"from": _iso(at), "to": _iso(at + QUARTER), "was": was.action, "now": slot.action, "reason": slot.reason})
    return {"available": True, "changed": changed, "runs": runs, "previous_at": _iso(previous.slot_start),
            "previous_soc": {_iso(t): round(s.soc_kwh, 2) for t, s in old.items() if t >= current.slot_start}}


def build_payload(snap: Any, *, build: str, cycle_at: datetime | None, previous: Decision | None, battery: Any, soc_max_age: timedelta,
                  force_charge: bool, bands: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The panel's data for one snapshot (see the module docstring); works for a snapshot without a decision too."""
    out = snap.output
    d: Decision | None = out.decision
    trace = out.trace or {}
    meta = {"version": PAYLOAD_VERSION, "build": build, "cycle_at": _iso(cycle_at), "status": out.status, "dry_run": True,
            "price_source": trace.get("price_source"), "weather_age_min": _r(snap.weather_age_min, 0), "history_hours": snap.history_hours,
            "tomorrow_quarters": snap.tomorrow_quarters, "prices_until": _iso(snap.prices_until), "pv_gain_w_per_wm2": _r(snap.pv_gain_w_per_wm2, 2),
            "stale_after_s": {"soc": int(soc_max_age.total_seconds()), "plan": PLAN_STALE_S, "live": LIVE_STALE_S, "prices": PRICES_STALE_S}}
    cap = battery.capacity_kwh
    batt = {"capacity_kwh": cap, "reserve_kwh": round(cap * battery.reserve_soc, 2), "floor_kwh": round(cap * battery.hard_min_soc, 2),
            "max_power_kw": battery.max_power_kw, "round_trip_eff": battery.round_trip_eff, "min_profit_margin": battery.min_profit_margin}
    e = snap.execution
    execution = {"code": e.code, "planned_w": e.planned_w, "power_w": e.power_w, "overridden": e.overridden, "reason": e.reason, "soc_pct": e.soc_pct}
    decision = None
    if d is not None:
        first = d.plan.slots[0] if d.plan.slots else None
        decision = {"slot_start": _iso(d.slot_start), "action": first.action if first else None, "reason": trace.get("reason"),
                    "compare": trace.get("compare"), "power_w": trace.get("power_w"), "soc_pct": trace.get("soc_pct"),
                    "import_price": trace.get("import_price"), "export_price": trace.get("export_price"),
                    "expected_saving": round(d.plan.saving, 2), "plan_text": snap.plan_text}

    # One row per quarter over the whole known price horizon; plan fields stay empty past the planned slots.
    rows: list[dict[str, Any]] = []
    band = lambda key, value, end: None if value is None or not bands else round(value * bands[key][end], 3)
    prices = out.prices
    if prices and d is not None:
        planned = {d.slot_start + i * QUARTER: s for i, s in enumerate(d.plan.slots)}
        ev = {q.start: q for q in out.ev_plan.quarters} if out.ev_plan else {}
        heat = [(r.start, r.end, r.kind) for r in out.heating_runs]
        for at, imp, exp in zip(prices.starts, prices.import_eur_kwh, prices.export_eur_kwh):
            if at < d.slot_start:
                continue
            s, q = planned.get(at), ev.get(at)
            kind = next((k for a, b, k in heat if a <= at < b), None)
            rows.append({"t": _iso(at), "imp": round(imp, 4), "exp": round(exp, 4),
                         "act": s.action if s else None, "w": round(s.battery_kwh * 4000) if s else None, "soc": _r(s.soc_kwh, 2) if s else None,
                         "why": s.reason if s else None, "code": s.reason_code if s else None,
                         "sell": _r(s.sell_value, 4) if s else None, "buy": _r(s.buy_cost, 4) if s else None, "keep": _r(s.stored_value, 4) if s else None,
                         "pv": _r(out.pv_kwh.get(at), 3), "load": _r(out.load_kwh.get(at), 3),
                         "pv_lo": band("pv", out.pv_kwh.get(at), "p10"), "pv_hi": band("pv", out.pv_kwh.get(at), "p90"),
                         "load_lo": band("load", out.load_kwh.get(at), "p10"), "load_hi": band("load", out.load_kwh.get(at), "p90"),
                         "ev_a": q.current_a if q and q.current_a else None, "ev_tier": q.tier if q and q.current_a else None, "heat": kind})

    analysis = d.analysis if d else None
    ev_plan = out.ev_plan
    point = snap.ev_setpoint
    return {
        "meta": meta, "battery": batt, "execution": execution, "decision": decision, "quarters": rows,
        "windows": list(snap.plan_windows),
        "sell_windows": [record(r) for r in analysis.reports] if analysis else [],
        "heating": [{"kind": r.kind, "from": _iso(r.start), "to": _iso(r.end), "kwh": round(r.energy_kwh, 2), "avg_price": round(r.avg_price, 4)}
                    for r in out.heating_runs],
        "ev": None if ev_plan is None else {
            "status": ev_plan.status, "reason": ev_plan.reason, "deadline": _iso(ev_plan.deadline), "required_kwh": round(ev_plan.required_kwh, 2),
            "optional_kwh": round(ev_plan.optional_kwh, 2), "planned_kwh": round(ev_plan.planned_kwh(), 2), "shortfall_kwh": round(ev_plan.shortfall_kwh, 2),
            "force_charge": force_charge,
            "setpoint": None if point is None else {"current_a": point.current_a, "planned_a": point.planned_a, "code": point.code, "reason": point.reason},
            "allowed_a": snap.ev_allowed_a},
        "diff": plan_diff(d, previous),
    }
