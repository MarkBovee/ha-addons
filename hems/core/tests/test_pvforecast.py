from datetime import datetime, timedelta, timezone

import pytest

from hems.pvforecast import fit_gain, preceding_mean_to_start, pv_kwh_per_quarter

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def test_irradiance_labels_are_shifted_to_the_start_of_their_interval():
    """A value labelled with the end of its quarter belongs to the quarter that starts 15 minutes earlier."""
    label = datetime(2026, 10, 13, 12, 15, tzinfo=timezone.utc)
    assert preceding_mean_to_start({label: 400.0}) == {datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc): 400.0}


def test_pv_forecast_scales_with_gain_and_clips_at_the_inverter_limit():
    """PV kWh follows irradiance times gain, never goes negative and is capped at the inverter AC limit."""
    noon, night = NOW, NOW + 12 * timedelta(hours=1)
    out = pv_kwh_per_quarter({noon: 500.0, night: -3.0}, gain_w_per_wm2=7.0, max_ac_w=8000)
    assert out[noon] == pytest.approx(3.5 * 0.25) and out[night] == 0.0
    assert pv_kwh_per_quarter({noon: 2000.0}, 7.0, 8000)[noon] == pytest.approx(8.0 * 0.25)   # 14 kW of panel, 8 kW inverter


def test_fit_gain_recovers_the_factor_and_falls_back_without_daylight():
    """The fitted gain matches the generating factor, and the default applies without daylight samples."""
    assert fit_gain([(100.0, 700.0), (400.0, 2800.0), (0.0, 30.0)]) == pytest.approx(7.0)
    assert fit_gain([(0.0, 0.0)]) == 7.0
