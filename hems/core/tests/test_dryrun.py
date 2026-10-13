import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hems.contracts import Reading
from hems.dryrun import (STATUS_NO_PRICE_NOW, STATUS_NO_PRICES, STATUS_NO_SOC, STATUS_OK, STATUS_STALE_SOC, EngineInputs,
                         EngineSettings, step)
from hems.forecast import LOCAL_TZ
from hems.weather import Weather, open_meteo_params, parse_open_meteo

FIXTURES = Path(__file__).parent / "fixtures"
SETTINGS = EngineSettings()
NOW = datetime(2026, 10, 6, 11, 7, tzinfo=LOCAL_TZ)


def day_curve(local_day="2026-10-06"):
    """The recorded import curve of one local day, as the energy-prices sensor would publish it."""
    first = datetime.fromisoformat(local_day).replace(tzinfo=LOCAL_TZ)
    with open(FIXTURES / "quarter_import_prices.csv", newline="") as f:
        rows = [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"])) for r in csv.DictReader(f)]
    return [(t, p) for t, p in rows if first <= t < first + timedelta(days=1)]


def inputs(**changes):
    """Engine inputs for 6 Oct 11:07 local with sensible defaults; override single fields per test."""
    base = dict(now=NOW, soc_pct=Reading(40.0, NOW - timedelta(minutes=1)), import_curve=day_curve(), load_history_w=[], ghi_w_m2=None)
    return EngineInputs(**{**base, **changes})


def test_a_normal_quarter_gives_a_decision_with_a_reason_and_notes_missing_inputs():
    """A normal quarter yields a command for the right slot, a reason, and flags the default load and missing weather."""
    out = step(inputs(), SETTINGS)
    assert out.status == STATUS_OK and out.decision.command.start == datetime(2026, 10, 6, 11, 0, tzinfo=LOCAL_TZ)
    assert out.trace["reason"] and out.trace["load_source"] == "default" and out.trace["weather"] is False


def test_no_decision_without_a_fresh_soc():
    """A missing or hour-old SoC gives no decision and a status that says why."""
    assert step(inputs(soc_pct=None), SETTINGS).status == STATUS_NO_SOC
    stale = step(inputs(soc_pct=Reading(40.0, NOW - timedelta(hours=1))), SETTINGS)
    assert stale.status == STATUS_STALE_SOC and stale.decision is None and stale.trace["soc_age_s"] == 3600


def test_no_decision_without_prices_for_the_current_quarter():
    """No curve, or only yesterday's curve, gives no decision with the right status."""
    assert step(inputs(import_curve=[]), SETTINGS).status == STATUS_NO_PRICES
    old = step(inputs(import_curve=day_curve("2026-10-05")), SETTINGS)       # yesterday's curve only
    assert old.status == STATUS_NO_PRICE_NOW and old.trace["prices_end"]


def test_history_and_weather_feed_the_forecasts():
    """Recorded load history and irradiance replace the default load and the zero PV forecast."""
    history = [(NOW.replace(hour=h, minute=0) - timedelta(days=d), 600.0) for d in range(1, 4) for h in range(24)]
    ghi = {t: 300.0 for t, _ in day_curve()}
    out = step(inputs(load_history_w=history, ghi_w_m2=ghi), SETTINGS)
    assert out.trace["load_source"] == "history" and out.trace["weather"] is True
    noon = datetime(2026, 10, 6, 12, 0, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    assert out.load_kwh[noon] == 0.6 * 0.25 and out.pv_kwh[noon] == 300.0 * 7.0 / 1000 * 0.25


def test_open_meteo_payload_is_rekeyed_to_quarter_starts():
    """Open-Meteo interval-end labels become quarter starts and null values are skipped."""
    payload = {"minutely_15": {"time": ["2026-10-13T12:15", "2026-10-13T12:30", "2026-10-13T12:45"],
                               "shortwave_radiation": [400.0, None, 410.0], "temperature_2m": [11.0, 11.1, 11.2]}}
    weather = parse_open_meteo(payload, datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))
    assert isinstance(weather, Weather)
    assert weather.ghi_w_m2 == {datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc): 400.0,
                                datetime(2026, 10, 13, 12, 30, tzinfo=timezone.utc): 410.0}     # the null quarter is skipped
    assert open_meteo_params(52.0, 5.0)["timezone"] == "UTC"


def test_weather_request_does_not_leak_the_exact_home_location():
    """The weather request carries coordinates rounded to about one kilometre."""
    params = open_meteo_params(52.090731, 5.121398)
    assert (params["latitude"], params["longitude"]) == (52.09, 5.12)
