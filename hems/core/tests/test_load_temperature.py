"""The load forecast follows the outdoor temperature when the history shows a heat pump: colder means more load."""
from datetime import datetime, timedelta, timezone

from hems.dryrun import EngineInputs, EngineSettings, _load_forecast
from hems.forecast import LOCAL_TZ, hourly_profile, temperature_slope, with_temperature

START = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)


def history_with_heat_pump(days: int = 7, slope_w: float = -100.0):
    """Hourly load of 500 W plus slope × (temperature − 8 °C); the temperature swings 4 °C around 8 °C from day to day."""
    hours, temps = [], {}
    for h in range(days * 24):
        hour = START - timedelta(days=days) + timedelta(hours=h)
        temp = 8.0 + (4.0 if (h // 24) % 2 else -4.0)
        for q in range(4):
            temps[hour + timedelta(minutes=15 * q)] = temp
        hours.append((hour, 500.0 + slope_w * (temp - 8.0)))
    return hours, temps


def test_the_fit_finds_the_heat_pump_response_and_ignores_a_flat_house():
    """A history that uses 100 W more per degree colder gives about −100 W/°C; a house that does not care gives no slope."""
    history, temps = history_with_heat_pump()
    fit = temperature_slope(history, temps, hourly_profile(history, 7, LOCAL_TZ), LOCAL_TZ)
    assert fit is not None and abs(fit[0] + 100.0) < 5.0
    flat = [(t, 500.0) for t, _ in history]
    assert temperature_slope(flat, temps, hourly_profile(flat, 7, LOCAL_TZ), LOCAL_TZ) is None
    assert temperature_slope(history[:24], temps, hourly_profile(history[:24], 7, LOCAL_TZ), LOCAL_TZ) is None, "one day is too little"


def test_a_cold_forecast_raises_the_load_and_the_engine_says_so():
    """Tomorrow 6 °C colder than the history's mean: about 600 W more per hour, the source and the slope tell why."""
    history, temps = history_with_heat_pump()
    cold = {START + timedelta(minutes=15 * q): 2.0 for q in range(8)}
    inputs = EngineInputs(START, None, [], history, None, outdoor_c={**temps, **cold})
    load, source, slope = _load_forecast(inputs, EngineSettings(), START, 8)
    plain, plain_source, plain_slope = _load_forecast(EngineInputs(START, None, [], history, None), EngineSettings(), START, 8)
    assert source == "history+temperature" and plain_source == "history" and plain_slope is None and slope < 0
    extra_w = (load[START] - plain[START]) * 4 * 1000
    assert 500 < extra_w < 700


def test_a_warm_spell_never_forecasts_an_empty_house():
    """However warm, a quarter keeps at least a quarter of its usual load."""
    profile = [400.0] * 24
    load = {START: 0.1}
    out = with_temperature(load, profile, -300.0, [8.0] * 24, {START: 30.0}, LOCAL_TZ)
    assert out[START] == 400.0 / 4 / 1000 * 0.25
