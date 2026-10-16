"""Heating plan: when the heat pump is expected to heat and how much electricity that takes (pure).

Other Home Assistant modules (for instance an energy manager forecasting the house load) need to know the water heater's
planned consumption without knowing how this add-on works. The plan is published as one entity (`sensor.wh_heating_plan`)
by `main.publish_heating_plan`; everything here is plain functions on prices and configuration, so it can be tested
without Home Assistant.

A day's plan is the cheapest heating window of the night window (00-06) and the day window (06-24), the same cheapest-window
rule the scheduler uses when it chooses its program; on the legionella day the day window is the longer legionella window.
The energy per window is a setting (measured on this installation: about 1.9 kWh for a heating window, 2.6 kWh on the
legionella day): the add-on controls a temperature, not a power, so it cannot know the consumption by itself.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Tuple

LowestWindow = Callable[[Dict[datetime, float], int, int, datetime, int], Tuple[datetime, float]]

NIGHT, DAY, LEGIONELLA = "night", "day", "legionella"
NIGHT_HOURS = (0, 6)
DAY_HOURS = (6, 24)


@dataclass(frozen=True)
class HeatingWindow:
    """One planned heating run: what kind, when, for how long, and how much electricity it is expected to use."""
    kind: str
    start: datetime
    end: datetime
    energy_kwh: float
    avg_price: float


def _day_window(prices: Dict[datetime, float], day: date, duration: int, lowest_window: LowestWindow, legionella: bool,
                config) -> HeatingWindow:
    """The cheapest heating window of one day: the cheaper of the night and the day window, or the legionella window."""
    target = datetime.combine(day, time())
    day_start, day_price = lowest_window(prices, DAY_HOURS[0], DAY_HOURS[1], target, duration)
    if legionella:
        return HeatingWindow(LEGIONELLA, day_start, day_start + timedelta(hours=duration), config.legionella_energy_kwh, day_price)
    night_start, night_price = lowest_window(prices, NIGHT_HOURS[0], NIGHT_HOURS[1], target, duration)
    if night_price < day_price:
        return HeatingWindow(NIGHT, night_start, night_start + timedelta(hours=duration), config.night_heating_energy_kwh, night_price)
    return HeatingWindow(DAY, day_start, day_start + timedelta(hours=duration), config.heating_energy_kwh, day_price)


def build_heating_plan(config, prices_by_day: Dict[date, Dict[datetime, float]], now: datetime, lowest_window: LowestWindow,
                       away: bool = False, legionella_due: bool = True, legionella_weekday: int = 5) -> List[HeatingWindow]:
    """The planned heating windows from `now` on, one per day with prices (today, and tomorrow once its prices are known).

    `prices_by_day` maps a date to that day's price curve; `lowest_window` is the scheduler's cheapest-window search
    (`main.get_lowest_price_window`). Nothing is planned in away mode, for a window that has already ended, or when the
    energy for that kind is 0 (night heating defaults to 0: the day window carries the heating on this installation).
    Today's legionella window only counts while the weekly protection is due; tomorrow's is assumed due."""
    windows: List[HeatingWindow] = []
    if away:
        return windows
    for day in sorted(prices_by_day):
        prices = prices_by_day[day]
        if not prices:
            continue
        legionella = day.weekday() == legionella_weekday and (day != now.date() or legionella_due)
        duration = config.legionella_duration_hours if legionella else config.heating_duration_hours
        window = _day_window(prices, day, duration, lowest_window, legionella, config)
        if window.energy_kwh > 0 and window.end > now:
            windows.append(window)
    return windows


def plan_state(windows: List[HeatingWindow]) -> str:
    """The entity state: the start of the next planned heating run (local ISO time with offset), or 'none'."""
    return windows[0].start.astimezone().isoformat(timespec="minutes") if windows else "none"


def plan_attributes(windows: List[HeatingWindow], config) -> Dict[str, Any]:
    """The entity attributes: every planned window with local ISO times, kind, expected kWh and average price, and the settings behind them."""
    iso = lambda moment: moment.astimezone().isoformat(timespec="minutes")
    return {
        "friendly_name": "Water heater heating plan",
        "icon": "mdi:water-boiler",
        "windows": [{"kind": w.kind, "start": iso(w.start), "end": iso(w.end), "energy_kwh": round(w.energy_kwh, 2),
                     "avg_price": round(w.avg_price, 4)} for w in windows],
        "heating_energy_kwh": config.heating_energy_kwh,
        "night_heating_energy_kwh": config.night_heating_energy_kwh,
        "legionella_energy_kwh": config.legionella_energy_kwh,
    }
