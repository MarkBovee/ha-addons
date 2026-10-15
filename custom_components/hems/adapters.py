"""Translate Home Assistant states and recorder rows into the engine's types. Pure: no hass, no I/O."""
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .engine.contracts import Reading
from .engine.derive import derive_house_load


def reading_from_state(state: Any, sign: float = 1.0) -> Reading | None:
    """A numeric reading stamped with when the entity last reported and when its value last changed, or None when unavailable/unknown/non-numeric."""
    if state is None or state.state in ("unavailable", "unknown", ""):
        return None
    try:
        return Reading(float(state.state) * sign, state.last_reported or state.last_updated, changed_at=state.last_changed)
    except (TypeError, ValueError):
        return None


def parse_price_curve(raw: Any) -> list[tuple[datetime, float]]:
    """Quarter starts (UTC) and consumer import prices from a `price_curve` attribute; malformed items are skipped."""
    curve = []
    for item in raw or []:
        try:
            start = datetime.fromisoformat(str(item["start"]).replace("Z", "+00:00"))
            if start.tzinfo is None:
                continue
            curve.append((start.astimezone(timezone.utc), float(item["price"])))
        except (KeyError, TypeError, ValueError):
            continue
    return curve


def statistic_rows(rows: Iterable[Mapping[str, Any]] | None) -> list[tuple[datetime, float]]:
    """Hourly (start UTC, mean) from recorder statistics rows, skipping hours without a mean."""
    return [(datetime.fromtimestamp(r["start"], tz=timezone.utc), float(r["mean"])) for r in rows or [] if r.get("mean") is not None]


def base_load_history(grid: Sequence[tuple[datetime, float]], pv: Sequence[tuple[datetime, float]],
                      battery_w: Sequence[tuple[datetime, float]], ev: Sequence[tuple[datetime, float]] = (),
                      inverter: Sequence[tuple[datetime, float]] = ()) -> list[tuple[datetime, float]]:
    """Hourly base load (W) from recorded means; battery_w is + charging. Hours missing an input are left out.

    With an inverter-output series the house is grid + inverter output - EV; otherwise the energy balance
    grid + PV - battery - EV applies."""
    by_hour = lambda rows: dict(rows)
    g, p, b, e, i = by_hour(grid), by_hour(pv), by_hour(battery_w), by_hour(ev), by_hour(inverter)
    out = []
    for hour in sorted(g):
        at = hour
        ev_reading = Reading(e[hour], at) if hour in e else None
        if inverter:
            if hour not in i:
                continue
            load = derive_house_load(Reading(g[hour], at), Reading(i[hour], at), Reading(0.0, at), ev_reading)
        else:
            if hour not in p or hour not in b:
                continue
            load = derive_house_load(Reading(g[hour], at), Reading(p[hour], at), Reading(b[hour], at), ev_reading)
        if load is not None:
            out.append((hour, load.value))
    return out
