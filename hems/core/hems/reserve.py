"""Sell floor from the expected house use: keep what the house needs until the battery can refill.

The reserve is a sell floor (Mark, 28 Oct 2026): a sale stops there, below it the battery only covers the house. A fixed 30 % is
right for an autumn night but too little for a cold winter one, so the floor of each quarter is the energy the house is
expected to draw (load above PV, with a safety factor for the forecast) from that quarter until the next moment the battery
can refill: the first quarter with PV above the load, or the first cheap import quarter (the bottom quarter of the horizon's price range,
where the plan charges). On top comes the hard minimum, and the result stays between the configured minimum and maximum.
"""
from dataclasses import replace

from hems.battery import BatteryConfig, Slot

MAX_LOOKAHEAD = 96            # quarters (24 h): beyond that the forecast is too weak to hold energy back for
CHEAP_QUANTILE = 0.25         # import prices at or below this share of the horizon count as a refill moment


def cheap_price_threshold(slots: list[Slot]) -> float | None:
    """Import price in the bottom CHEAP_QUANTILE of the horizon's price range: quarters at or below it are where the plan charges.

    The range, not the rank: with a flat day most quarters share one price and a rank quantile would call all of them cheap.
    None when the prices are flat (nothing is cheaper than anything else)."""
    prices = [s.import_price for s in slots]
    low, high = min(prices), max(prices)
    if high - low < 1e-6:
        return None
    return low + CHEAP_QUANTILE * (high - low)


def _is_refill(slot: Slot, cheap: float | None) -> bool:
    """True when the battery can refill in this quarter: PV covers the house, or import is cheap."""
    return slot.pv_kwh >= slot.load_kwh or (cheap is not None and slot.import_price <= cheap)


def usage_floor(slots: list[Slot], cfg: BatteryConfig) -> list[float]:
    """Sell floor per slot (fraction of capacity), from the expected use until the next refill moment.

    Returns cfg.reserve_soc everywhere when the maximum equals the minimum (the feature switched off)."""
    if cfg.reserve_max_soc <= cfg.reserve_soc or not slots:
        return [cfg.reserve_soc] * len(slots)
    eff = cfg.round_trip_eff ** 0.5
    cheap = cheap_price_threshold(slots)
    floors = []
    for t in range(len(slots)):
        need = 0.0
        for slot in slots[t:t + MAX_LOOKAHEAD]:
            if _is_refill(slot, cheap):
                break
            need += max(0.0, slot.load_kwh * cfg.reserve_load_factor - slot.pv_kwh) / eff
        fraction = cfg.hard_min_soc + need / cfg.capacity_kwh
        floors.append(round(min(cfg.reserve_max_soc, max(cfg.reserve_soc, fraction)), 3))
    return floors


def with_usage_floor(slots: list[Slot], cfg: BatteryConfig) -> list[Slot]:
    """The slots with their sell floor set from the expected use (Slot.reserve_soc); an explicit floor already set is kept."""
    floors = usage_floor(slots, cfg)
    return [s if s.reserve_soc is not None else replace(s, reserve_soc=f) for s, f in zip(slots, floors)]
