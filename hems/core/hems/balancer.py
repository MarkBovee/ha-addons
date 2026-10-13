"""Load balancer: share grid headroom between controllable loads by priority."""
from dataclasses import dataclass


@dataclass
class Load:
    name: str
    wanted_w: float
    priority: int            # lower = more important
    min_w: float = 0.0       # below this the load is switched off (e.g. EV 6 A ~ 4.1 kW 3-phase)
    controllable: bool = True


def allocate(house_w: float, loads: list[Load], grid_limit_w: float = 15000.0,
             hysteresis_w: float = 500.0, previous: dict[str, float] | None = None) -> dict[str, float]:
    """Return granted power per load. house_w = uncontrollable baseload.
    Loads are served by priority; a load that cannot get min_w gets 0.
    hysteresis: a load that was running keeps min_w alive with hysteresis_w extra slack
    to avoid flapping."""
    previous = previous or {}
    headroom = grid_limit_w - house_w
    granted: dict[str, float] = {}
    for ld in sorted(loads, key=lambda x: x.priority):
        if not ld.controllable:
            granted[ld.name] = ld.wanted_w
            headroom -= ld.wanted_w
            continue
        running = previous.get(ld.name, 0) > 0
        give = min(ld.wanted_w, max(headroom, 0.0))
        floor = ld.min_w - (hysteresis_w if running else 0.0)   # stay on slightly below min
        if give < floor:
            give = 0.0
        elif give < ld.min_w:
            give = ld.min_w
        granted[ld.name] = give
        headroom -= give
    return granted
