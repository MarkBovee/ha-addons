"""Spa module: keep the water inside a temperature band and heat in the cheap quarters.

Mark (29 Oct 2026): "always at temperature, top up cheaply". The water stays between `comfort - below` and `comfort + above`;
the plan heats when power is cheap or the sun gives a surplus, lets the water drift down when power is dear, and never lets it
leave the band. A small dynamic programme per quarter over a 0.05 °C grid: each quarter the heater is on or off, heating adds
`heat_rate_c_h`, the water loses `cool_k · (water - outdoor)` per hour. Execution is only through the climate's target
temperature: the top of the band to heat, the bottom to pause; HEMS never puts the spa in rest, so the spa keeps its own frost
and overheat protection. Pure: the caller supplies the time, the water temperature, prices, surplus and the outdoor forecast.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from statistics import median
from typing import Mapping, Sequence

from hems.prices import PriceSeries
from hems.slots import SLOT_H

QUARTER = timedelta(minutes=15)
STEP_C = 0.05                      # fine enough that a quarter of cooling (about 0.1 °C) is not rounded away
INF = float("inf")


@dataclass(frozen=True)
class SpaConfig:
    """The spa module's settings; the defaults fit a Balboa spa of about 1300 l with a 3 kW heater on one phase."""
    enabled: bool = False
    control: str = "external"          # "external": the spa's own controller heats (Spapilot): HEMS only forecasts it; "climate": HEMS plans and sets the target
    daily_kwh: float = 20.0            # external control: what the spa heats per day (measured 30-31 Oct 2026: about 20 kWh above the house's usual load)
    learn: bool = True                 # external control: learn the energy per day from the measured load (daily_kwh is the start value); off only in tests
    heater_kw: float = 3.0
    phase: int = 1                     # 0 = L1, 1 = L2, 2 = L3: the phase the heater draws on
    comfort_c: float = 38.0
    above_c: float = 0.5               # may heat up to comfort + above when power is cheap or free
    below_c: float = 1.0               # may drift down to comfort - below when power is dear
    heat_rate_c_h: float = 2.0         # degrees per hour the heater adds (about 3 kW into 1300 l)
    cool_k_h: float = 0.02             # share of the water-outdoor difference lost per hour
    default_outdoor_c: float = 10.0    # when the weather forecast has no temperature for a quarter
    max_quarters: int = 96             # plan 24 h ahead

    @property
    def low_c(self) -> float:
        """The bottom of the band."""
        return self.comfort_c - self.below_c

    @property
    def high_c(self) -> float:
        """The top of the band."""
        return self.comfort_c + self.above_c


@dataclass(frozen=True)
class SpaQuarter:
    """One planned quarter: heater on or off, the expected water temperature at its end and the electricity."""
    start: datetime
    heat: bool
    temp_c: float
    kwh: float
    price: float


@dataclass(frozen=True)
class SpaPlan:
    """The spa's plan: quarters from now on, and why the first one does what it does."""
    quarters: tuple[SpaQuarter, ...]
    reason: str
    feasible: bool = True              # False when the band cannot be held (too cold, too weak a heater): the plan heats as much as it can


def _cool(temp: float, outdoor: float, cfg: SpaConfig) -> float:
    """Degrees lost in one quarter."""
    return max(0.0, temp - outdoor) * cfg.cool_k_h * SLOT_H


def _price(start: datetime, imp: float, exp: float, surplus: Mapping[datetime, float], kwh: float) -> float:
    """What a kWh of the heater costs in this quarter: the export price it forgoes when the sun covers it, else the import price."""
    return exp if surplus.get(start, 0.0) >= kwh - 1e-9 else imp


def plan_spa(prices: PriceSeries, surplus_kwh: Mapping[datetime, float], outdoor_c: Mapping[datetime, float] | None, now: datetime,
             water_c: float | None, cfg: SpaConfig) -> SpaPlan | None:
    """The cheapest on/off schedule that keeps the water in the band (see the module docstring); None without a water temperature or prices."""
    if not cfg.enabled or cfg.control != "climate" or water_c is None:
        return None
    starts = [s for s in prices.starts if s + QUARTER > now][:cfg.max_quarters]
    if not starts:
        return None
    by_start = {s: (i, e) for s, i, e in zip(prices.starts, prices.import_eur_kwh, prices.export_eur_kwh)}
    kwh_on = cfg.heater_kw * SLOT_H
    lo_k = round((min(cfg.low_c, water_c) - 2 * STEP_C) / STEP_C)
    hi_k = round(max(cfg.high_c, water_c) / STEP_C)
    levels = range(lo_k, hi_k + 1)
    band_lo, band_hi = round(cfg.low_c / STEP_C), round(cfg.high_c / STEP_C)
    n = len(starts)
    cost = [{k: INF for k in levels} for _ in range(n + 1)]
    for k in levels:
        cost[n][k] = 0.0
    choice: list[dict[int, tuple[bool, int]]] = [{} for _ in range(n)]
    for t in range(n - 1, -1, -1):
        s = starts[t]
        imp, exp = by_start[s]
        outdoor = (outdoor_c or {}).get(s, cfg.default_outdoor_c)
        price = _price(s, imp, exp, surplus_kwh, kwh_on)
        for k in levels:
            temp = k * STEP_C
            best, best_choice = INF, None
            for heat in (False, True):
                nxt = temp + (cfg.heat_rate_c_h * SLOT_H if heat else 0.0) - _cool(temp, outdoor, cfg)
                k2 = min(max(round(nxt / STEP_C), lo_k), hi_k)
                if k2 > band_hi:                                  # never heat above the band
                    continue
                if k < band_lo and not heat:                      # below the band the heater must run
                    continue
                if k >= band_lo and k2 < band_lo:                 # inside the band the quarter must end inside it too
                    continue
                c = (kwh_on * price if heat else 0.0) + cost[t + 1][k2]
                if c < best:
                    best, best_choice = c, (heat, k2)
            if best_choice is None:                               # nothing keeps the band: heat (the plan says it is not feasible)
                best_choice = (True, min(max(round((temp + cfg.heat_rate_c_h * SLOT_H - _cool(temp, outdoor, cfg)) / STEP_C), lo_k), hi_k))
                best = kwh_on * price + cost[t + 1][best_choice[1]]
            cost[t][k], choice[t][k] = best, best_choice
    k = min(max(round(water_c / STEP_C), lo_k), hi_k)
    quarters = []
    for t, s in enumerate(starts):
        heat, k2 = choice[t][k]
        imp, exp = by_start[s]
        quarters.append(SpaQuarter(s, heat, round(k2 * STEP_C, 2), kwh_on if heat else 0.0, _price(s, imp, exp, surplus_kwh, kwh_on)))
        k = k2
    return SpaPlan(tuple(quarters), _reason(quarters, water_c, cfg), _holds_band(quarters, water_c, cfg))


def _holds_band(quarters: list[SpaQuarter], water_c: float, cfg: SpaConfig) -> bool:
    """True when the plan keeps the band: never below it, or (starting below it) rising every quarter until it is in and staying in."""
    temp, inside = water_c, water_c >= cfg.low_c - 1e-9
    for q in quarters:
        if inside and q.temp_c < cfg.low_c - 1e-9:
            return False
        if not inside and q.temp_c <= temp + 1e-9:
            return False
        inside = inside or q.temp_c >= cfg.low_c - 1e-9
        temp = q.temp_c
    return True


def _reason(quarters: list[SpaQuarter], water_c: float, cfg: SpaConfig) -> str:
    """Why the first quarter heats or not, in a line."""
    first = quarters[0]
    if first.heat and water_c < cfg.low_c:
        return f"below the band ({water_c:.1f} < {cfg.low_c:.1f} °C): heating"
    if first.heat:
        return f"cheap quarter ({first.price:.3f}): topping up towards {cfg.high_c:.1f} °C"
    nxt = next((q for q in quarters if q.heat), None)
    return f"waiting, next heating {nxt.start:%H:%M} UTC" if nxt else "in the band, no heating needed"


LEARN_MIN_DAYS = 3                    # fewer measured days: keep the configured daily_kwh
LEARN_WINDOW_DAYS = 14                # look this far back
LEARN_HALF_LIFE_DAYS = 3.0            # a day this much older counts half: a spa day weighs in, a quiet week lets the forecast drop
SPA_DAY_KWH = 1.0                     # a day with more than this counts as one the spa heated
FULL_DAY_HOURS = 20                   # a day needs about all its hours to be measured


def _day_indexes(history: Sequence[tuple[datetime, float]], tz: tzinfo) -> dict[date, list[int]]:
    """The history's indexes per local day, only for days with about all their hours."""
    days: dict[date, list[int]] = defaultdict(list)
    for index, (ts, _) in enumerate(history):
        days[ts.astimezone(tz).date()].append(index)
    return {day: idx for day, idx in days.items() if len(idx) >= FULL_DAY_HOURS}


def _excess_wh(history: Sequence[tuple[datetime, float]], indexes: list[int], cap_w: float) -> dict[int, float]:
    """Per hour of one day: the load above the day's median, at most the heater's power (what a heater could have drawn)."""
    mid = median(history[i][1] for i in indexes)
    return {i: min(max(history[i][1] - mid, 0.0), cap_w) for i in indexes}


def measured_spa_kwh(history: Sequence[tuple[datetime, float]], cfg: SpaConfig, tz: tzinfo, before: date | None = None) -> dict[date, float]:
    """What the spa drew per measured local day: the day's load above its median (capped at the heater's power per hour), less the
    least such excess of any day in the history. That least day stands for the house's own peaks (cooking and the like): before the
    spa, or a day it hardly heated. Only days with about all their hours, and before `before` (today is still running)."""
    excess = {day: sum(_excess_wh(history, idx, cfg.heater_kw * 1000).values()) / 1000 for day, idx in _day_indexes(history, tz).items()
              if before is None or day < before}
    if not excess:
        return {}
    house = min(excess.values())
    return {day: round(kwh - house, 2) for day, kwh in excess.items()}


def learned_daily_kwh(history: Sequence[tuple[datetime, float]], cfg: SpaConfig, today: date, tz: tzinfo) -> float:
    """The spa's expected energy per day: the measured days before `today` (up to LEARN_WINDOW_DAYS back), the recent ones weighing
    most (half-life LEARN_HALF_LIFE_DAYS). Days before the first one the spa heated (above SPA_DAY_KWH) are left out: that is before
    it was there. The configured daily_kwh with learning off or fewer than LEARN_MIN_DAYS such days."""
    if not cfg.learn or not cfg.enabled or cfg.control != "external":
        return cfg.daily_kwh
    measured = measured_spa_kwh(history, cfg, tz, today)
    first = min((d for d, kwh in measured.items() if kwh > SPA_DAY_KWH), default=None)
    if first is None:
        return cfg.daily_kwh
    days = {d: kwh for d, kwh in measured.items() if d >= first and 0 < (today - d).days <= LEARN_WINDOW_DAYS}
    if len(days) < LEARN_MIN_DAYS:
        return cfg.daily_kwh
    weights = {d: 0.5 ** ((today - d).days / LEARN_HALF_LIFE_DAYS) for d in days}
    return round(sum(days[d] * w for d, w in weights.items()) / sum(weights.values()), 1)


def without_flexible_load(history: Sequence[tuple[datetime, float]], cfg: SpaConfig, tz: tzinfo) -> list[tuple[datetime, float]]:
    """The hourly load history (W) with the externally controlled spa taken out: per local day the energy it drew there
    (measured_spa_kwh with learning on, else daily_kwh), from the hours above the day's median, highest first, at most the heater's
    power per hour. Days without about a full set of hours are left as they are."""
    if not cfg.enabled or cfg.control != "external" or (cfg.daily_kwh <= 0 and not cfg.learn):
        return list(history)
    measured = measured_spa_kwh(history, cfg, tz) if cfg.learn else {}
    cleaned = list(history)
    for day, indexes in _day_indexes(history, tz).items():
        excess = _excess_wh(history, indexes, cfg.heater_kw * 1000)
        left = measured.get(day, 0.0) * 1000 if cfg.learn else cfg.daily_kwh * 1000
        for i in sorted(indexes, key=lambda i: history[i][1], reverse=True):
            take = min(excess[i], left)
            if take <= 0:
                break
            cleaned[i] = (history[i][0], history[i][1] - take)
            left -= take
    return cleaned


def external_spa_kwh(prices: PriceSeries, now: datetime, cfg: SpaConfig, tz: tzinfo, daily_kwh: float | None = None) -> dict[datetime, float]:
    """Where an externally controlled, price-following spa heats: per local day its energy (`daily_kwh`, the learned value, else the
    configured one) in that day's cheapest quarters at the heater's power, as Spapilot does. Quarters already past are left out
    (that energy went in earlier today)."""
    per_day = cfg.daily_kwh if daily_kwh is None else daily_kwh
    if not cfg.enabled or cfg.control != "external" or per_day <= 0:
        return {}
    per_quarter = cfg.heater_kw * SLOT_H
    by_day: dict[date, list[tuple[float, datetime]]] = defaultdict(list)
    for start, price in zip(prices.starts, prices.import_eur_kwh):
        by_day[start.astimezone(tz).date()].append((price, start))
    out: dict[datetime, float] = {}
    for quarters in by_day.values():
        if len(quarters) < 88:                                     # a day without (almost) all its prices: where it heats is unknown
            continue
        left = per_day
        for price, start in sorted(quarters):
            if left <= 0:
                break
            kwh = min(per_quarter, left)
            left -= kwh
            if start + QUARTER > now:
                out[start] = kwh
    return out


def spa_kwh_per_quarter(plan: SpaPlan | None) -> dict[datetime, float]:
    """The heater's planned electricity per quarter, for the load forecast."""
    return {q.start: q.kwh for q in plan.quarters if q.kwh > 0} if plan else {}


@dataclass(frozen=True)
class SpaTarget:
    """The target temperature to set now and why."""
    target_c: float
    heat: bool
    reason: str


def spa_target(plan: SpaPlan | None, now: datetime, cfg: SpaConfig, allowed: bool = True) -> SpaTarget | None:
    """The climate target for now: the top of the band to heat, the bottom to pause; a heating quarter the grid cannot take is paused."""
    if plan is None:
        return None
    current = next((q for q in plan.quarters if q.start <= now < q.start + QUARTER), plan.quarters[0])
    if current.heat and not allowed:
        return SpaTarget(cfg.low_c, False, "paused: the phase is full (the spa gives way first)")
    if current.heat:
        return SpaTarget(cfg.high_c, True, plan.reason)
    return SpaTarget(cfg.low_c, False, plan.reason)
