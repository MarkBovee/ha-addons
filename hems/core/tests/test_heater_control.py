"""The water heater executor against the add-on's rules (set_water_temperature), on made-up price days."""
from datetime import datetime, timedelta, timezone

from hems.forecast import LOCAL_TZ
from hems.heater import WaterHeaterConfig
from hems.heater_control import (AWAY, BATH, DAY, IDLE, LEGIONELLA, NEGATIVE, NIGHT, HeaterInputs, HeaterRules, decide, price_level)
from hems.prices import PriceSeries

CFG = WaterHeaterConfig(enabled=True)
RULES = HeaterRules()


def prices(day=(2026, 10, 28), days=2, base=0.40, cheap: dict[int, float] | None = None) -> PriceSeries:
    """Quarter prices from local midnight for `days` days: `base`, with {local hour: price} cheap hours on every day."""
    start = datetime(*day, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    starts = [start + timedelta(minutes=15 * k) for k in range(96 * days)]
    imp = [(cheap or {}).get(t.astimezone(LOCAL_TZ).hour, base) for t in starts]
    return PriceSeries(tuple(starts), tuple(imp), tuple(imp))


def at(hour: int, minute: int = 0, day=(2026, 10, 28)) -> datetime:
    return datetime(*day, hour, minute, tzinfo=LOCAL_TZ)


def run(now, series=None, tank=45.0, away=False, bath=False, last=datetime(2026, 10, 24, 14, 0, tzinfo=LOCAL_TZ), previous=None, config=CFG):
    return decide(HeaterInputs(now, tank, away, bath, last, series or prices(cheap={13: 0.30, 3: 0.35})), config, RULES, LOCAL_TZ, previous)


def test_price_levels_are_the_add_ons_fixed_amounts():
    assert [price_level(p, [0.40]) for p in (-0.01, 0.05, 0.30, 0.38, 0.50)] == ["none", "low", "medium", "high", "maximum"]
    assert price_level(0.30, [0.20]) == "high", "above the day's average (at least 0.28) a sub-0.35 price is high"


def test_the_day_run_heats_to_58_in_the_cheapest_hour_and_idles_outside():
    inside = run(at(13, 10))
    assert (inside.program, inside.target_c, inside.in_window) == (DAY, 58, True)
    assert run(at(11)).target_c == 35 and run(at(11)).program == IDLE


def test_the_night_preheats_when_the_night_is_cheaper_than_the_day():
    cheap_night = prices(cheap={3: 0.20, 13: 0.30})
    assert (run(at(3, 15), cheap_night).program, run(at(3, 15), cheap_night).target_c) == (NIGHT, 56)
    assert run(at(3, 15), prices(cheap={3: 0.35, 13: 0.30})).target_c == 52, "day cheaper: minimal night heating"


def test_the_day_is_skipped_when_tomorrow_night_is_cheaper():
    series = prices(cheap={13: 0.38, 3: 0.20})                 # 13:00 is today's cheapest day hour, tomorrow 03:00 is cheaper still
    cmd = run(at(13, 5), series)
    assert cmd.in_window and cmd.target_c == 35 and "tomorrow night cheaper" in cmd.reason


def test_legionella_runs_on_its_day_when_due_and_not_when_not():
    sat = (2026, 10, 31)
    series = prices(sat, cheap={13: 0.30, 14: 0.30, 15: 0.30})
    due = run(at(13, 30, sat), series, last=datetime(2026, 10, 24, 14, 0, tzinfo=LOCAL_TZ))
    assert (due.program, due.target_c, due.window[1] - due.window[0]) == (LEGIONELLA, 62, timedelta(hours=3))
    recent = run(at(13, 30, sat), series, last=datetime(2026, 10, 26, 9, 0, tzinfo=LOCAL_TZ))
    assert recent.program == DAY


def test_negative_price_heats_to_70_whatever_else():
    series = prices(cheap={11: -0.02})
    assert (run(at(11, 20), series, away=True).program, run(at(11, 20), series).target_c) == (NEGATIVE, 70)


def test_away_keeps_35_but_still_does_legionella_on_its_day():
    assert (run(at(13, 10), away=True).program, run(at(13, 10), away=True).target_c) == (AWAY, 35)
    sat = (2026, 10, 31)
    cmd = run(at(13, 30, sat), prices(sat, cheap={13: 0.30, 14: 0.30, 15: 0.30}), away=True)
    assert (cmd.program, cmd.target_c) == (LEGIONELLA, 60), "away legionella: 60 °C at or above 0.20 EUR/kWh"


def test_bath_heats_to_58_and_is_switched_off_above_56():
    on = run(at(10), bath=True, tank=50)
    assert (on.program, on.target_c, on.bath_off) == (BATH, 58, False)
    done = run(at(10), bath=True, tank=57)
    assert done.bath_off and done.program == IDLE


def test_a_run_finishes_during_the_cycle_gap_then_stands_by():
    last_in = run(at(13, 55))
    assert last_in.in_window and last_in.target_c == 58
    assert run(at(14, 20), previous=last_in).target_c == 58, "within 50 minutes after the window: finishing"
    assert run(at(14, 55), previous=last_in).target_c == 35


def test_every_temperature_is_a_setting():
    from hems.heater_control import HeaterTemps
    rules = HeaterRules(temps=HeaterTemps(day_preheat=60))
    cmd = decide(HeaterInputs(at(13, 10), 45, False, False, None, prices(cheap={13: 0.30, 3: 0.35})), CFG, rules, LOCAL_TZ)
    assert cmd.target_c == 60
