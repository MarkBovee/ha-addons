"""What stored energy is worth at the end of the horizon, from the prices of recent days (pure).

The planner sees today and, after 13:00, tomorrow. Energy left in the battery at the end of that horizon can still be sold in a
later peak, and the battery holds only one cycle a day (about 15 kWh between 100 % and the 30 % reserve), so selling it on a small
spread today means it is gone when the day after tomorrow pays more. The default value of that energy, the cheapest import price in
the horizon, ignores this. Here it is the typical peak of the last days: eff x (peak - margin), what a kWh sold in such a peak
earns, never lower than the default.

A 'peak' is the mean of a day's best two hours (eight quarters) of export price: a 15 kWh sale takes about two hours at 8 kW, so the
single best quarter would overstate what the sale earns.
"""
from datetime import date, tzinfo
from statistics import median
from typing import Mapping

from hems.battery import BatteryConfig
from hems.prices import PriceSeries

TOP_QUARTERS = 8                 # the best two hours of a day
MIN_DAY_QUARTERS = 88            # a day with fewer known quarters (a gap in the data) is left out
HISTORY_DAYS = 7
MIN_HISTORY_DAYS = 3             # fewer days than this say too little about a typical peak


def daily_peaks(prices: PriceSeries, tz: tzinfo) -> dict[date, float]:
    """The peak per local day (mean of its eight best export quarters), for the days the series covers completely."""
    by_day: dict[date, list[float]] = {}
    for start, price in zip(prices.starts, prices.export_eur_kwh):
        by_day.setdefault(start.astimezone(tz).date(), []).append(price)
    return {day: sum(sorted(values)[-TOP_QUARTERS:]) / TOP_QUARTERS for day, values in by_day.items() if len(values) >= MIN_DAY_QUARTERS}


def reference_peak(peaks: Mapping[date, float], today: date, days: int = HISTORY_DAYS, min_days: int = MIN_HISTORY_DAYS) -> float | None:
    """The median peak of the last `days` days before `today` that are known; None when fewer than `min_days` of them are."""
    recent = [peak for day, peak in peaks.items() if 0 < (today - day).days <= days]
    return median(recent) if len(recent) >= min_days else None


def terminal_value(peak: float, default: float, cfg: BatteryConfig) -> float:
    """EUR per stored kWh at the end of the horizon: what a kWh sold in a typical peak earns (net of the round trip and the margin and the haircut), at least `default`."""
    eff = cfg.round_trip_eff ** 0.5
    return max(default, eff * (peak - cfg.future_peak_haircut - cfg.min_profit_margin))
