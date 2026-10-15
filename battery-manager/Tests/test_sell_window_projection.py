"""Task D: sell windows are judged on the projected SOC at their start."""

from datetime import timedelta, timezone

from app import main as bm_main
from app.price_analyzer import find_profitable_discharge_starts
from Tests import curves_2026_10_07 as curves
from Tests.plan_replay import amsterdam_tz, local_start, make_config, replay  # noqa: F401


def _sell_periods(schedule, day=7):
    return [
        p for p in schedule["discharge"]
        if p["window_type"] == "discharge" and local_start(p).day == day
    ]


def test_evening_sell_survives_low_midday_soc_when_pv_will_fill_the_battery(monkeypatch, amsterdam_tz):
    """SoC 36% at 12:00 must not truncate the 17:30 sell: ~12 kWh of PV is forecast."""
    schedule = replay(monkeypatch, "12:00", soc=36, remaining_solar=15.0)

    sells = _sell_periods(schedule)
    assert len(sells) == 1
    assert local_start(sells[0]).strftime("%H:%M") == "17:30"
    assert sells[0]["duration"] == 120  # the full 2h top-X, not 43 minutes


def test_filter_trace_reports_projection_and_reason(monkeypatch, amsterdam_tz):
    config = make_config()
    now = curves.at(7, "12:00").astimezone(timezone.utc)
    window = {"start": curves.at(7, "17:30"), "end": curves.at(7, "19:30"), "avg_price": 0.46}
    charge = [{
        "start": curves.at(7, "12:00").isoformat(), "duration": 240, "power": 1000,
        "window_type": "charge", "forecast_solar_kwh": 12.0,
    }]

    with_pv, without_pv = [], []
    kept = bm_main._filter_supported_discharge_windows(
        [window], charge, 36.0, config, now, 8, 4000, trace=with_pv)
    no_pv_charge = [{k: v for k, v in charge[0].items() if k != "forecast_solar_kwh"}]
    cut = bm_main._filter_supported_discharge_windows(
        [window], no_pv_charge, 36.0, config, now, 8, 4000, trace=without_pv)

    assert kept[0]["end"] == window["end"]
    assert with_pv[0]["decision"] == "kept"
    assert with_pv[0]["projected_soc_at_start"] > 90
    assert with_pv[0]["reserve_floor_soc"] == 25.0
    # Without the PV share the same window is cut (what the old filter did).
    assert without_pv[0]["decision"] == "truncated"
    assert cut[0]["end"] < window["end"]
    assert without_pv[0]["needed_kwh"] > without_pv[0]["available_kwh"]


def test_equal_prices_form_one_contiguous_window():
    """Ties must not drift to the end of the day (19:30/19:45 instead of 19:15)."""
    export = [
        {"start": curves.at(7, "18:00").isoformat(), "price": 0.60},
        {"start": curves.at(7, "18:15").isoformat(), "price": 0.60},
        {"start": curves.at(7, "18:30").isoformat(), "price": 0.42},
        {"start": curves.at(7, "18:45").isoformat(), "price": 0.42},
        {"start": curves.at(7, "19:00").isoformat(), "price": 0.42},
        {"start": curves.at(7, "19:15").isoformat(), "price": 0.20},
    ]
    imports = [{**e, "price": 0.20} for e in export]

    starts = find_profitable_discharge_starts(imports, export, 4, 0.10)

    assert starts == {e["start"] for e in export[:4]}


def test_planned_sell_windows_have_no_hole_between_equal_priced_quarters(monkeypatch, amsterdam_tz):
    """Replay at 18:00 / SoC 87%: the sold quarters are one contiguous block."""
    schedule = replay(monkeypatch, "18:00", soc=87, remaining_solar=2.0)

    sells = _sell_periods(schedule)
    assert len(sells) == 1, [(local_start(p), p["duration"]) for p in sells]
    end = local_start(sells[0]) + timedelta(minutes=sells[0]["duration"])
    assert end.strftime("%H:%M") == "19:30"
