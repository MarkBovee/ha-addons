"""What HEMS expects, as plain numbers and series for people (pure): the coming hour of a forecast, the energy inside
a charge or discharge window, the price curve and the first window of the plan.

The planner works on these same series; this module only reads them out for sensors and dashboards, so what a user
sees is exactly what the plan was computed from.
"""
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Mapping, Sequence

from hems.prices import PriceSeries

QUARTER = timedelta(minutes=15)
HOUR_QUARTERS = 4
DAY_QUARTERS = 96
MAX_PERIOD_GAP = timedelta(hours=1)    # rest between two runs of the same action that still counts as one period


def _hour(series: Mapping[datetime, float], start: datetime) -> list[float] | None:
    """The four quarters from `start`, or None when the series misses any of them (a partial hour would read too low)."""
    quarters = [start + i * QUARTER for i in range(HOUR_QUARTERS)]
    return [series[t] for t in quarters] if all(t in series for t in quarters) else None


def hour_total(series: Mapping[datetime, float], start: datetime, digits: int = 3) -> float | None:
    """The sum of the coming hour (four quarters from `start`): energy per quarter becomes energy for the hour."""
    values = _hour(series, start)
    return None if values is None else round(sum(values), digits)


def hour_mean(series: Mapping[datetime, float], start: datetime, digits: int = 1) -> float | None:
    """The mean of the coming hour (four quarters from `start`): for irradiance and temperature, which are rates, not energy."""
    values = _hour(series, start)
    return None if values is None else round(sum(values) / HOUR_QUARTERS, digits)


def window_total(series: Mapping[datetime, float], begin: datetime, end: datetime, digits: int = 2) -> float:
    """The sum of the quarters that start in [begin, end); quarters the series does not know count as nothing."""
    total, moment = 0.0, begin
    while moment < end:
        total += series.get(moment, 0.0)
        moment += QUARTER
    return round(total, digits)


def forecast_series(series: Mapping[datetime, float], start: datetime, tz: tzinfo, key: str, digits: int = 3,
                    limit: int = DAY_QUARTERS) -> list[dict]:
    """The next `limit` quarters from `start` as [{"start": local ISO time, key: value}], for a dashboard chart."""
    points = []
    for i in range(limit):
        moment = start + i * QUARTER
        if moment in series:
            points.append({"start": moment.astimezone(tz).isoformat(), key: round(series[moment], digits)})
    return points


def price_curve(prices: PriceSeries, field: str, start: datetime, tz: tzinfo) -> list[dict]:
    """Every known price from `start` on as [{"start": local ISO time, "price": EUR/kWh}]; field is 'import' or 'export'."""
    values = prices.import_eur_kwh if field == "import" else prices.export_eur_kwh
    return [{"start": t.astimezone(tz).isoformat(), "price": round(v, 4)} for t, v in zip(prices.starts, values) if t >= start]


def _local_day(prices: PriceSeries, now: datetime, tz: tzinfo) -> list[int]:
    """The indexes of the quarters that start on the local day of `now`."""
    day = now.astimezone(tz).date()
    return [i for i, t in enumerate(prices.starts) if t.astimezone(tz).date() == day]


def price_curve_for_day(prices: PriceSeries, field: str, now: datetime, tz: tzinfo) -> list[dict]:
    """The quarters of the local day of `now` and everything known after it, as [{"start", "end", "price"}] with UTC ISO times.

    This is the shape of the `price_curve` attribute of the energy-prices sensor (whole current day, past quarters included), so a
    consumer written for that sensor, such as the water heater add-on, a dashboard chart or a template, can read this one instead."""
    values = prices.import_eur_kwh if field == "import" else prices.export_eur_kwh
    first = datetime.combine(now.astimezone(tz).date(), time.min, tz).astimezone(timezone.utc)
    return [{"start": t.astimezone(timezone.utc).isoformat(), "end": (t + QUARTER).astimezone(timezone.utc).isoformat(), "price": round(v, 4)}
            for t, v in zip(prices.starts, values) if t >= first]


def day_price_stats(prices: PriceSeries, now: datetime, tz: tzinfo) -> dict[str, float] | None:
    """Average, minimum and maximum import price of the local day of `now`, the maximum export price, and the maximum profit
    (highest export price minus lowest import price), all EUR/kWh; None when the series holds no quarter of that day."""
    days = _local_day(prices, now, tz)
    if not days:
        return None
    imports, exports = [prices.import_eur_kwh[i] for i in days], [prices.export_eur_kwh[i] for i in days]
    return {"average": sum(imports) / len(imports), "minimum": min(imports), "maximum": max(imports), "max_export": max(exports),
            "max_profit": max(exports) - min(imports)}


def _merge(runs: Sequence[Mapping]) -> dict:
    """One period from consecutive runs of the same action: energy adds up, power is the mean over the quarters that move
    energy, price is weighted by energy, SoC runs from the start of the first run to the end of the last."""
    kwh = sum(r["kwh"] for r in runs)
    active_h = sum((datetime.fromisoformat(r["to"]) - datetime.fromisoformat(r["from"])).total_seconds() for r in runs) / 3600
    priced = [(r["kwh"], r["avg_price"]) for r in runs if r.get("avg_price") is not None and r["kwh"]]
    return {"begin": datetime.fromisoformat(runs[0]["from"]), "end": datetime.fromisoformat(runs[-1]["to"]), "from": runs[0]["from"], "to": runs[-1]["to"],
            "action": runs[0]["action"], "kwh": round(kwh, 2), "avg_w": round(kwh * 1000 / active_h) if active_h else 0,
            "soc_from_pct": runs[0]["soc_from_pct"], "soc_to_pct": runs[-1]["soc_to_pct"],
            "avg_price": round(sum(k * p for k, p in priced) / sum(k for k, _ in priced), 4) if priced else None}


def periods(segments: Sequence[Mapping]) -> list[dict]:
    """The charge and discharge periods of the plan, in order, with real datetimes.

    The plan moves energy in pieces (a quarter of rest where the price bumps up), which would read as a string of
    short windows. Runs of the same action with at most MAX_PERIOD_GAP of rest between them are one period; the
    opposite action, or a longer rest, starts a new one (a night charge and a midday top-up stay two periods)."""
    found: list[dict] = []
    current: list[Mapping] = []
    for run in segments:
        kind = run.get("action")
        if kind not in ("charge", "discharge"):
            continue
        rest = datetime.fromisoformat(run["from"]) - datetime.fromisoformat(current[-1]["to"]) if current else None
        if current and current[0]["action"] == kind and rest <= MAX_PERIOD_GAP:
            current.append(run)
            continue
        if current:
            found.append(_merge(current))
        current = [run]
    if current:
        found.append(_merge(current))
    return found


CHEAP_BLOCK_QUARTERS = 12              # the block shown when the plan does not charge: three hours


def cheapest_block(prices: PriceSeries, start: datetime, quarters: int = CHEAP_BLOCK_QUARTERS) -> dict | None:
    """The cheapest run of `quarters` consecutive import-price quarters from `start` on, as {begin, end, avg_price}; None when the prices do not cover one.

    It answers 'when is charging cheapest?' on a day the plan itself does not charge (the battery is full enough, PV covers it): the window of the
    prices, not of the plan, so the sensor that shows it says so."""
    known = {t: p for t, p in zip(prices.starts, prices.import_eur_kwh) if t >= start}
    firsts = [t for t in sorted(known) if all(t + k * QUARTER in known for k in range(quarters))]
    if not firsts:
        return None
    mean = lambda t: sum(known[t + k * QUARTER] for k in range(quarters)) / quarters
    begin = min(firsts, key=lambda t: (mean(t), t))
    return {"begin": begin, "end": begin + quarters * QUARTER, "avg_price": round(mean(begin), 4)}


def first_window(segments: Sequence[Mapping], action: str) -> dict | None:
    """The first period of `action` ('charge' or 'discharge'); None when the plan has none.

    A period that is going on now starts at the current quarter."""
    return next((period for period in periods(segments) if period["action"] == action), None)
