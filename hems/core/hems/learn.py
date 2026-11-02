"""Settings HEMS learns from what it measures (Mark, 2 Nov 2026): every value it can measure it learns; the configured value is the
start value until there are enough measurements, and the fallback when the measurement is missing or implausible.

Pure: the caller supplies the hourly history from the recorder.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo
from math import sqrt
from statistics import median
from typing import Sequence

from hems.heater import WaterHeaterConfig

MIN_CHARGED_KWH = 100.0             # less charged energy in the window: the SoC ends (hourly means) weigh too much against the losses
PLAUSIBLE_RTE = (0.60, 0.98)        # outside this the measurement is wrong (a gap, a wrong sign), not the battery


@dataclass(frozen=True)
class Learned:
    """A learned value next to the configured one: what is used, and why."""
    value: float
    configured: float
    source: str                     # "learned" or the reason the configured value is used
    samples: float = 0.0            # what the value rests on (kWh charged, days measured)


def round_trip_efficiency(battery_w: Sequence[tuple[datetime, float]], soc_pct: Sequence[tuple[datetime, float]], capacity_kwh: float,
                          configured: float) -> Learned:
    """The battery's round-trip efficiency from hourly mean power (+ charging, W) and state of charge (%) over the window.

    Charged energy `cin` goes in at sqrt(eta), discharged `out` comes out at 1/sqrt(eta), and the stored energy changed by `d`:
    d = cin·x − out/x with x = sqrt(eta), so x = (d + sqrt(d² + 4·cin·out)) / (2·cin). The same split the planner uses."""
    soc_at = dict(soc_pct)
    hours = sorted(t for t, _ in battery_w if t in soc_at)          # only hours with both: the energy and the SoC change span the same time
    if len(hours) < 2:
        return Learned(configured, configured, "too little measured", 0.0)
    power = {t: w for t, w in battery_w if hours[0] <= t <= hours[-1]}
    cin = sum(max(w, 0.0) for w in power.values()) / 1000
    out = sum(max(-w, 0.0) for w in power.values()) / 1000
    if cin < MIN_CHARGED_KWH or out <= 0:
        return Learned(configured, configured, "too little measured", round(cin, 1))
    d = (soc_at[hours[-1]] - soc_at[hours[0]]) / 100 * capacity_kwh
    x = (d + sqrt(d * d + 4 * cin * out)) / (2 * cin)
    eta = round(x * x, 2)
    if not PLAUSIBLE_RTE[0] <= eta <= PLAUSIBLE_RTE[1]:
        return Learned(configured, configured, f"implausible measurement ({eta})", round(cin, 1))
    return Learned(eta, configured, "learned", round(cin, 1))


MIN_HEATER_DAYS = 3                 # fewer measured days: keep the configured run energies


def hourly_from_sum(rows: Sequence[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Hourly energy (Wh, which is also the hour's mean W) from an energy statistic's running sum per hour start; a drop (a reset or a
    meter swap) counts as 0, never as negative energy."""
    out = []
    for (prev, before), (start, after) in zip(rows, rows[1:]):
        if start - prev == timedelta(hours=1):     # across a gap the energy cannot be put in one hour
            out.append((start, max(after - before, 0.0)))
    return out


def water_heater_runs(heater_w: Sequence[tuple[datetime, float]], cfg: WaterHeaterConfig, today: date, tz: tzinfo,
                      legionella_days: frozenset[date] = frozenset()) -> tuple[WaterHeaterConfig, dict]:
    """The water heater module's run energies from the heater's own metered hours (Wh per hour), before `today`.

    A normal day's total is split over the night and day run as configured (night share = night / (night + day)); the median normal
    day is the learned value. A legionella day is one HEMS recorded a legionella run on (`legionella_days`), else the legionella
    weekday with clearly more than a normal day (1.5 times the median); its mean is the legionella run, less the night run, and
    never less than the day run. The configured values stay with fewer than MIN_HEATER_DAYS normal days."""
    days: dict[date, float] = defaultdict(float)
    hours: dict[date, int] = defaultdict(int)
    for start, wh in heater_w:
        day = start.astimezone(tz).date()
        if day < today:
            days[day] += wh / 1000
            hours[day] += 1
    totals = {d: kwh for d, kwh in days.items() if hours[d] >= 20}
    record = {"configured_kwh": cfg.energy_kwh + cfg.night_energy_kwh, "days": len(totals)}
    if not totals:
        return cfg, {**record, "source": "no measurement"}
    typical = median(totals.values())
    is_legionella = lambda d, kwh: d in legionella_days or (d.weekday() == cfg.legionella_weekday and kwh > 1.5 * typical)
    legionella = [kwh for d, kwh in totals.items() if is_legionella(d, kwh)]
    normal = [kwh for d, kwh in totals.items() if not is_legionella(d, kwh)]
    if len(normal) < MIN_HEATER_DAYS:
        return cfg, {**record, "source": "too few days"}
    day_kwh = median(normal)
    night_share = cfg.night_energy_kwh / (cfg.night_energy_kwh + cfg.energy_kwh) if cfg.night_energy_kwh + cfg.energy_kwh > 0 else 0.0
    night, day = round(day_kwh * night_share, 2), round(day_kwh * (1 - night_share), 2)
    leg = round(max(sum(legionella) / len(legionella) - night, day), 2) if legionella else cfg.legionella_energy_kwh
    learned = replace(cfg, energy_kwh=day, night_energy_kwh=night, legionella_energy_kwh=leg)
    return learned, {**record, "source": "learned", "day_kwh": day, "night_kwh": night, "legionella_kwh": leg, "legionella_days": len(legionella)}


def without_metered(history: Sequence[tuple[datetime, float]], metered_w: Sequence[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """The hourly load history (W) with a separately metered device taken out hour by hour (never below 0)."""
    metered = dict(metered_w)
    return [(start, max(w - metered.get(start, 0.0), 0.0)) for start, w in history]
