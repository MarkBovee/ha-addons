from datetime import datetime, timedelta, timezone

import pytest

from hems.dryrun import EngineInputs, EngineSettings, _load_forecast
from hems.forecast import LOCAL_TZ
from hems.heater import HeatingRun, parse_runs, run_kwh_per_quarter, without_daily_peak

NOW = datetime(2026, 10, 15, 9, 7, tzinfo=LOCAL_TZ)
START = datetime(2026, 10, 15, 7, 0, tzinfo=timezone.utc)            # 09:00 local: the quarter of NOW


def days_of_history(heater_hour: int, days: int = 7, base_w: float = 600.0, heater_w: float = 2000.0) -> list[tuple[datetime, float]]:
    """`days` local days of hourly mean load: a flat base and the heater adding `heater_w` in `heater_hour` of every day."""
    first = datetime(2026, 10, 8, tzinfo=LOCAL_TZ)
    return [(first + timedelta(days=d, hours=h), base_w + (heater_w if h == heater_hour else 0.0)) for d in range(days) for h in range(24)]


def test_malformed_plan_items_are_skipped_and_the_rest_is_parsed():
    """The plan entity is somebody else's output: whatever it carries, HEMS reads what it can."""
    good = {"kind": "day", "start": "2026-10-15T13:00+02:00", "end": "2026-10-15T14:00+02:00", "energy_kwh": 1.9}
    bad = [{"start": "x"}, {"start": "2026-10-15T13:00", "end": "2026-10-15T14:00", "energy_kwh": 1.9},          # no offset
           {**good, "energy_kwh": 0}, {**good, "end": "2026-10-15T12:00+02:00"}, "text", None]
    assert [(r.start.hour, r.energy_kwh) for r in parse_runs([good, *bad])] == [(13, 1.9)]
    assert parse_runs(None) == [] and parse_runs("windows") == []


def test_a_runs_energy_is_spread_evenly_over_its_quarters_in_utc():
    """1.9 kWh over 13:00-14:00 local is 0.475 kWh in each of the four quarters, keyed by UTC quarter start."""
    run = parse_runs([{"start": "2026-10-15T13:00+02:00", "end": "2026-10-15T14:00+02:00", "energy_kwh": 1.9}])
    per_quarter = run_kwh_per_quarter(run)
    assert sorted(per_quarter) == [datetime(2026, 10, 15, 11, 15 * k, tzinfo=timezone.utc) for k in range(4)]
    assert all(v == pytest.approx(0.475) for v in per_quarter.values()) and sum(per_quarter.values()) == pytest.approx(1.9)


def test_each_days_heater_is_taken_out_of_the_history_up_to_the_configured_energy():
    """The peak hour loses what it has above the day's median (2.0 kWh), at most the cap; other hours stay."""
    history = days_of_history(12)
    cleaned = without_daily_peak(history, 1.9, LOCAL_TZ)
    peaks = [w for (_, w), (_, old) in zip(cleaned, history) if w != old]
    assert len(peaks) == 7 and all(w == pytest.approx(2600 - 1900) for w in peaks)
    assert without_daily_peak(history, 5.0, LOCAL_TZ)[12][1] == pytest.approx(600.0), "a bigger cap removes the whole excess, never more"
    assert without_daily_peak(history, 0.0, LOCAL_TZ) == history


def test_a_short_day_is_left_alone():
    """With only a few hours of a day there is no telling which is the peak: nothing is removed."""
    history = days_of_history(12, days=1)[:12]
    assert without_daily_peak(history, 1.9, LOCAL_TZ) == history


def test_the_forecast_without_the_heater_model_is_what_it_was():
    """No cap, no runs: the median profile, labelled 'history'."""
    inputs = EngineInputs(NOW, None, [], days_of_history(12), None)
    load, source = _load_forecast(inputs, EngineSettings(), START, 8)
    assert source == "history" and load[START] == pytest.approx(0.15)


def test_the_planned_run_replaces_the_smeared_peak_in_the_forecast():
    """History has the heater at 12:00 every day; the module plans it at 13:00. Without the model 12:00 stays high and 13:00 is flat; with it the
    peak moves to 13:00 and the day's total grows by nothing (one heater run in, one out)."""
    history = days_of_history(12)
    run = parse_runs([{"start": "2026-10-15T13:00+02:00", "end": "2026-10-15T14:00+02:00", "energy_kwh": 1.9}])
    start = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)                # 12:00 local
    plain, _ = _load_forecast(EngineInputs(NOW, None, [], history, None), EngineSettings(), start, 8)
    modelled, source = _load_forecast(EngineInputs(NOW, None, [], history, None, heating_runs=run), EngineSettings(heater_cap_kwh=1.9), start, 8)
    hour = lambda load, first: sum(load[start + timedelta(minutes=15 * (first + k))] for k in range(4))
    assert source == "history+heater"
    assert hour(plain, 0) == pytest.approx(2.6) and hour(plain, 4) == pytest.approx(0.6)                       # the old forecast: peak at 12, flat at 13
    assert hour(modelled, 0) == pytest.approx(0.7) and hour(modelled, 4) == pytest.approx(0.6 + 1.9)           # the modelled one: 12 flat, peak at 13
