"""Water heater executor: the target temperature HEMS would set now, ported from the water heater add-on (set_water_temperature).

Mark (28 Oct 2026): HEMS replaces the add-on and takes over its rules faithfully first, price levels included, so the two can be
compared one to one before the add-on stops; improvements come after. The order of the add-on's decision:

  negative price (70 °C) > away (35 °C, the legionella run still on its day) > bath (58 °C, switched off above a temperature)
  > night program (00-06: preheat when the night is cheaper than the day, else minimal) > legionella (on its weekday when due)
  > day program (preheat, skipped when tomorrow night is cheaper and the price is medium or high) > stand-by (35 °C, 50 °C when cheap).

Inside the program's cheapest window the target is the program temperature; outside it the stand-by temperature, after a
cycle gap so a run can finish. Pure: the caller supplies the time, the tank, the toggles, the prices and the previous command.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from hems.heater import DAY_HOURS, NIGHT_HOURS, WaterHeaterConfig, _cheapest_window, _hour_prices, _local, legionella_due
from hems.prices import PriceSeries

NEGATIVE, AWAY, BATH, NIGHT, LEGIONELLA, DAY, IDLE = "negative_price", "away", "bath", "night", "legionella", "day", "idle"
NO_PRICE = 999.0                           # the add-on's stand-in for an unknown price


@dataclass(frozen=True)
class HeaterTemps:
    """The temperatures, all settings (Mark, 28 Oct 2026); the defaults are the add-on's comfort preset as it runs here."""
    night_preheat: float = 56
    night_minimal: float = 52
    day_preheat: float = 58
    day_minimal: float = 35
    negative_price: float = 70
    bath: float = 58
    away: float = 35
    idle: float = 35
    low_price: float = 50                   # stand-by when the price level is low (the add-on's opportunistic heating)
    away_legionella_cheap: float = 66       # away on the legionella day: 66 °C below 0.20 EUR/kWh, else 60 °C
    away_legionella: float = 60




@dataclass(frozen=True)
class HeaterRules:
    """The executor's settings next to the module's: the preset, the night window end, the bath switch-off and the cycle gap."""
    temps: HeaterTemps = HeaterTemps()
    night_end_hour: int = NIGHT_HOURS[1]
    bath_auto_off_c: float = 56.0
    cycle_gap: timedelta = timedelta(minutes=50)


@dataclass(frozen=True)
class HeaterInputs:
    """What the executor reads at one moment."""
    now: datetime
    tank_c: float | None
    away: bool
    bath: bool
    last_legionella: datetime | None
    prices: PriceSeries                     # consumer import price per quarter, today and (once known) tomorrow


@dataclass(frozen=True)
class HeaterCommand:
    """What HEMS would set now, and why."""
    target_c: float
    program: str
    in_window: bool
    window: tuple[datetime, datetime] | None
    reason: str
    bath_off: bool = False                  # the bath toggle should be switched off (the tank passed the bath switch-off)
    window_ended: datetime | None = None    # end of the last window this command came from, for the cycle gap


def price_level(price: float, today: list[float]) -> str:
    """The add-on's price level (from NetDaemon's PriceHelper): none below 0, low below 0.10, medium below 0.35 and the day's
    average (at least 0.28), high below 0.45, maximum above. Fixed amounts, as the add-on has them."""
    threshold = max(sum(today) / len(today), 0.28) if today else 0.28
    if price < 0:
        return "none"
    if price < 0.10:
        return "low"
    if price < 0.35:
        return "medium" if price < threshold else "high"
    return "high" if price < 0.45 else "maximum"


def _price_now(prices: PriceSeries, now: datetime) -> float | None:
    """The import price of the quarter that contains `now`."""
    for start, price in zip(prices.starts, prices.import_eur_kwh):
        if start <= now < start + timedelta(minutes=15):
            return price
    return None


def _window(hours: dict[datetime, float], day: date, part: tuple[int, int], length: int, tz: tzinfo) -> tuple[datetime, float] | None:
    """The cheapest `length` hours of a part of a local day: start and mean price."""
    return _cheapest_window(hours, _local(day, part[0], tz), _local(day, part[1], tz), length)


def decide(inputs: HeaterInputs, config: WaterHeaterConfig, rules: HeaterRules, tz: tzinfo, previous: HeaterCommand | None = None) -> HeaterCommand:
    """The target temperature for now (see the module docstring)."""
    t, now = rules.temps, inputs.now
    local = now.astimezone(tz)
    today = local.date()
    hours = _hour_prices(inputs.prices, tz)
    price = _price_now(inputs.prices, now)
    price = NO_PRICE if price is None else price
    today_prices = [p for s, p in zip(inputs.prices.starts, inputs.prices.import_eur_kwh) if s.astimezone(tz).date() == today]
    level = price_level(price, today_prices) if today_prices else "medium"
    night = local.hour < rules.night_end_hour
    legionella_on = (not night and local.weekday() == config.legionella_weekday and legionella_due(inputs.last_legionella, today, tz))
    length = config.legionella_hours if legionella_on else config.hours
    night_window = _window(hours, today, NIGHT_HOURS, length, tz)
    day_window = _window(hours, today, DAY_HOURS, length, tz)
    next_night = _window(hours, today + timedelta(days=1), NIGHT_HOURS, config.hours, tz)
    chosen = night_window if night else day_window
    window = (chosen[0], chosen[0] + timedelta(hours=length)) if chosen else None
    in_window = bool(window and window[0] <= now < window[1])
    bath = inputs.bath
    bath_off = bath and inputs.tank_c is not None and inputs.tank_c > rules.bath_auto_off_c
    if bath_off:
        bath = False

    standby = t.low_price if level == "low" else t.idle
    if level == "none":
        program, target, standby, why = NEGATIVE, t.negative_price, t.negative_price, f"negative price {price:.3f}: {t.negative_price:.0f} °C"
    elif inputs.away:
        if legionella_on:
            target = t.away_legionella_cheap if price < 0.2 else t.away_legionella
            program, why = LEGIONELLA, f"away, legionella day: {target:.0f} °C"
        else:
            program, target, why = AWAY, t.away, "away: minimal heating"
    elif bath:
        program, target, standby, why = BATH, t.bath, t.bath, f"bath: {t.bath:.0f} °C"
    elif night:
        cheaper = bool(night_window and day_window and night_window[1] < day_window[1])
        program, target = NIGHT, t.night_preheat if cheaper else t.night_minimal
        why = "night cheaper than day: preheat" if cheaper else "day cheaper: minimal night heating"
    elif legionella_on:
        program, target, why = LEGIONELLA, config.legionella_temp_c, f"legionella protection: {config.legionella_temp_c:.0f} °C"
    else:
        program, target, why = DAY, t.day_preheat, f"day program: {t.day_preheat:.0f} °C"
        tomorrow_night = next_night[1] if next_night else NO_PRICE
        if 0 < tomorrow_night < price and level in ("medium", "high"):
            target, why = standby, f"tomorrow night cheaper ({tomorrow_night:.3f} < {price:.3f}): skip day heating"

    if in_window or program in (NEGATIVE, BATH):
        return HeaterCommand(target, program, in_window, window, why, bath_off, window[1] if window and in_window else None)
    # Outside the window: let a run that just ended finish for the cycle gap, then fall back to stand-by.
    ended = previous.window_ended if previous else None
    if previous and previous.target_c > t.idle and ended and now - ended < rules.cycle_gap:
        return HeaterCommand(previous.target_c, previous.program, False, window, f"finishing the {previous.program} run", bath_off, ended)
    nxt = f", next {program} run {window[0].astimezone(tz):%H:%M}" if window and window[0] > now else ""
    return HeaterCommand(standby, IDLE if standby == t.idle else program, False, window,
                         ("stand-by" if standby == t.idle else f"low price: {standby:.0f} °C") + nxt, bath_off)
