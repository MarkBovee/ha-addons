"""Modes and recommendations: the step between "HEMS would do this" and "HEMS does this".

Every module has a mode. `dry_run` only plans. `advisory` also turns the next planned action into a recommendation the owner
can apply or dismiss on the dashboard. Applying fires the Home Assistant event `hems_recommendation_applied` with what to do;
an automation of the owner's choice carries it out, so HEMS still writes to no device itself. `auto` is not offered yet: no module
has an executor that writes, and a mode that promises control it does not have would be a lie on the dashboard.

A recommendation's id is a hash of what it asks (module, action, window, setpoint). A dismissed one stays away until the plan
changes what it asks, so a new id appears; that is the owner's rule "back when the plan changes". Pure: no Home Assistant objects.
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from typing import Any

MODULES = ("battery", "ev", "water_heater")
MODE_DRY_RUN = "dry_run"
MODE_ADVISORY = "advisory"
MODES = (MODE_DRY_RUN, MODE_ADVISORY)
QUARTER = timedelta(minutes=15)
EVENT_APPLIED = "hems_recommendation_applied"


def _iso(moment) -> str | None:
    return moment.astimezone(timezone.utc).isoformat() if moment else None


ID_FIELDS = ("action", "kind", "to", "power_w", "current_a")     # what the owner decides on; 'from' moves in an ongoing window and kWh with every replan


def _rec(module: str, kind: str, payload: dict[str, Any], reason: str, expires: str | None) -> dict[str, Any]:
    """One recommendation with an id over what it asks (end time, action and setpoint), so a replan of the same advice keeps its id."""
    core = {k: payload.get(k) for k in ID_FIELDS}
    digest = hashlib.sha1(json.dumps([module, kind, core], sort_keys=True).encode()).hexdigest()[:12]
    return {"id": digest, "module": module, "kind": kind, "payload": payload, "reason": reason, "expires": expires}


def battery_recommendation(snap: Any) -> dict[str, Any] | None:
    """The first planned charge or discharge period (it may be going on now), with its average power rounded to 100 W."""
    windows = [w for w in snap.plan_windows if w.get("action") in ("charge", "discharge")]
    if not windows:
        return None
    w = windows[0]
    payload = {"action": w["action"], "from": w["from"], "to": w["to"], "power_w": int(round(abs(w["power_w"]) / 100) * 100), "kwh": w["kwh"]}
    reason = (snap.output.trace or {}).get("reason") or ""
    return _rec("battery", w["action"], payload, reason, w["to"])


def ev_recommendation(snap: Any) -> dict[str, Any] | None:
    """The first block of planned charge quarters with the same current."""
    plan = snap.output.ev_plan
    quarters = [q for q in (plan.quarters if plan else ()) if q.current_a]
    if not quarters:
        return None
    first = quarters[0]
    end = first.start + QUARTER
    kwh = first.kwh
    for q in quarters[1:]:
        if q.start != end or q.current_a != first.current_a:
            break
        end += QUARTER
        kwh += q.kwh
    payload = {"action": "charge", "from": _iso(first.start), "to": _iso(end), "current_a": first.current_a, "kwh": round(kwh, 2), "tier": first.tier}
    return _rec("ev", "charge", payload, plan.reason, _iso(end))


def water_heater_recommendation(snap: Any) -> dict[str, Any] | None:
    """The next planned heating run."""
    runs = snap.output.heating_runs
    if not runs:
        return None
    r = runs[0]
    payload = {"action": "heat", "kind": r.kind, "from": _iso(r.start), "to": _iso(r.end), "kwh": round(r.energy_kwh, 2)}
    return _rec("water_heater", r.kind, payload, f"cheapest hours, average {r.avg_price:.4f} EUR/kWh", _iso(r.end))


BUILDERS = {"battery": battery_recommendation, "ev": ev_recommendation, "water_heater": water_heater_recommendation}


@dataclass
class Control:
    """The owner's modes, the master switch and the fate of recommendations. The master is never stored: after a restart it is off."""
    modes: dict[str, str] = field(default_factory=lambda: {m: MODE_DRY_RUN for m in MODULES})
    armed: bool = False
    dismissed: dict[str, None] = field(default_factory=dict)     # an ordered set: the oldest are dropped first
    applied: dict[str, str] = field(default_factory=dict)       # id -> when (UTC ISO)

    def state(self) -> dict[str, Any]:
        return {"modes": self.modes, "dismissed": list(self.dismissed)[-200:], "applied": dict(list(self.applied.items())[-200:])}

    def restore(self, data: dict[str, Any] | None) -> None:
        if not isinstance(data, dict):
            return
        for module, mode in (data.get("modes") or {}).items():
            if module in MODULES and mode in MODES:
                self.modes[module] = mode
        self.dismissed = dict.fromkeys(data.get("dismissed") or [])
        self.applied = dict(data.get("applied") or {})

    def recommendations(self, snap: Any) -> list[dict[str, Any]]:
        """Open recommendations of the modules in advisory mode, with their status (open or applied); dismissed ones are left out."""
        if snap is None or snap.output.decision is None:
            return []
        out = []
        for module in MODULES:
            if self.modes.get(module) != MODE_ADVISORY:
                continue
            rec = BUILDERS[module](snap)
            if rec is None or rec["id"] in self.dismissed:
                continue
            out.append({**rec, "status": "applied" if rec["id"] in self.applied else "open", "applied_at": self.applied.get(rec["id"])})
        return out
