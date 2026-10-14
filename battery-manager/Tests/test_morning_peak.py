"""2026-10-14: a morning peak before the midday charge window was missed (incident).

The day had two peaks: 07:30-09:30 (export up to 0.62) before the cheapest window at 11:45-15:45, and 18:30-20:15 (up to
0.53) after it. Sell planning looked only at quarters after the charge window, so only the evening was planned, and the
battery covered the house load all morning. ``top_x_discharge_hours`` applies to each peak, and the day's charge is sized
to refill what the morning sale takes out, so the evening keeps its full budget.
"""

from datetime import datetime, timedelta, timezone

from dateutil.parser import isoparse

from app import main as bm_main
from Tests import curves_2026_10_14 as real
from Tests.plan_replay import amsterdam_tz, local_start, make_config, replay  # noqa: F401

USER_SETTINGS = {  # Mark's sell buffer of 13 Oct: 40 % floor, charge the buffer 4 h before the sale
    "soc.sell_buffer_min_soc": 40,
    "soc.sell_buffer_activation_hours_before_sell": 4,
}


def _plan(monkeypatch, hhmm, soc, **overrides):
    """Plan 2026-10-14 at local ``hhmm`` with ``soc`` percent and Mark's sell-buffer settings."""
    config = make_config(**{**USER_SETTINGS, **overrides})
    return replay(monkeypatch, hhmm, soc=soc, remaining_solar=0.0, day=14,
                  import_curve=real.import_curve(), export_curve=real.export_curve(), config=config)


def _sells(schedule):
    """The sell windows of a schedule (adaptive placeholders left out)."""
    return [p for p in schedule["discharge"] if p["window_type"] == "discharge"]


def _minutes(periods, start_hour, end_hour):
    """Minutes of the periods that start between the two local hours."""
    return sum(p["duration"] for p in periods if start_hour <= local_start(p).hour < end_hour)


def test_the_morning_peak_gets_a_sell_window_next_to_the_evening(monkeypatch, amsterdam_tz):
    """Both peaks of the day are planned: 07:30-09:30 and the evening."""
    schedule = _plan(monkeypatch, "00:00", soc=45)
    sells = _sells(schedule)
    morning = [p for p in sells if local_start(p).hour < 11]
    evening = [p for p in sells if local_start(p).hour >= 16]
    assert morning and evening
    assert local_start(morning[0]).strftime("%H:%M") == "07:30"
    assert morning[0]["price"] > 0.53  # the 07:30-09:30 block averages 0.537; the evening block 0.519


def test_the_pre_sell_charge_is_not_blocked_by_the_price_ceiling_and_fills_the_morning_window(monkeypatch, amsterdam_tz):
    """A pre-sell charge at 0.33 passes the margin gate despite the 0.25 ceiling, so the morning window is not cut."""
    # 04:00 = four hours before the sale: the sell buffer activates. Import is 0.33 there, above the 0.25 ceiling,
    # but 0.537 x 0.9 - 0.33 clears the margin gate, so the buffer is charged.
    schedule = _plan(monkeypatch, "04:00", soc=58)
    assert any(p["window_type"] == "precharge" for p in schedule["charge"])
    morning = [p for p in _sells(schedule) if local_start(p).hour < 11]
    assert _minutes(morning, 0, 11) >= 105  # of 120: the energy for the whole peak is there


def test_the_midday_charge_refills_what_the_morning_sale_takes_out(monkeypatch, amsterdam_tz):
    """The deficit includes the morning energy: the evening keeps its full two hours and the midday charge is sized up."""
    schedule = _plan(monkeypatch, "06:00", soc=54)
    evening = [p for p in _sells(schedule) if local_start(p).hour >= 16]
    assert sum(p["duration"] for p in evening) == 120  # the full X = 2 h; it was cut to 90-98 min before
    main_charge = next(p for p in schedule["charge"] if p["window_type"] == "charge")
    assert main_charge["power"] >= 4500  # sized on the deficit plus the morning energy, not on the current SoC alone


def test_the_budget_is_per_peak_x_hours_each(monkeypatch, amsterdam_tz):
    """top_x_discharge_hours = 1 gives one hour in the morning and one in the evening, not one in total."""
    config = make_config(**{"heuristics.top_x_discharge_hours": 1})
    schedule = replay(monkeypatch, "06:00", soc=90, remaining_solar=0.0, day=14,
                      import_curve=real.import_curve(), export_curve=real.export_curve(), config=config)
    sells = _sells(schedule)
    assert _minutes(sells, 0, 11) <= 60 and _minutes(sells, 16, 24) <= 60
    assert _minutes(sells, 0, 11) > 0 and _minutes(sells, 16, 24) > 0


def test_without_the_option_the_whole_day_shares_one_budget(monkeypatch, amsterdam_tz):
    """discharge_after_charge_only = false keeps the old whole-day ranking with a single budget."""
    legacy = _plan(monkeypatch, "00:00", soc=45, **{"heuristics.discharge_after_charge_only": False})
    assert sum(p["duration"] for p in _sells(legacy)) <= 120  # the old ranking: X hours for the whole day, wherever they fall


def _planned_kw(schedule, quarter_start):
    """Battery AC power (kW, + charge) the published schedule plans for the quarter that starts at ``quarter_start``."""
    net = 0.0
    for kind, sign in (("charge", 1), ("discharge", -1)):
        for period in schedule.get(kind, []):
            if kind == "discharge" and period.get("window_type") == "adaptive":
                continue
            start = isoparse(period["start"])
            if start <= quarter_start < start + timedelta(minutes=period["duration"]):
                net += sign * period["power"] / 1000.0
    return net


def test_the_midday_charge_is_recomputed_on_the_actual_soc_after_the_sale_and_changes_about_hourly(monkeypatch, amsterdam_tz):
    """One cycle per quarter from the pre-sell charge to noon, SoC following the published plan (25 kWh, 0.3 pp house load per quarter)."""
    config = make_config(**USER_SETTINGS)
    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)
    cest = timezone(timedelta(hours=2))
    soc, now = 58.0, datetime(2026, 10, 14, 3, 30, tzinfo=cest)
    cycles = []
    while now < datetime(2026, 10, 14, 13, 0, tzinfo=cest):
        schedule = replay(monkeypatch, now.strftime("%H:%M"), soc=soc, remaining_solar=0.0, day=14,
                          import_curve=real.import_curve(), export_curve=real.export_curve(), config=config, state=state)
        main = [p["power"] for p in schedule["charge"] if p["window_type"] == "charge"]
        cycles.append({"at": now, "soc": soc, "main": main[0], "am": _minutes(_sells(schedule), 0, 11), "pm": _minutes(_sells(schedule), 16, 24)})
        soc = max(5.0, min(99.0, soc + _planned_kw(schedule, now) * 0.25 / 25.0 * 100.0 - 0.3))
        now += timedelta(minutes=15)

    at = {c["at"].strftime("%H:%M"): c for c in cycles}
    assert at["05:15"]["soc"] >= 98  # the pre-sell charge filled the battery before the sale
    assert at["09:30"]["soc"] < 40 and at["07:30"]["am"] >= 100  # the morning peak was sold
    assert all(c["pm"] == 120 for c in cycles)  # the evening budget is never cut
    # After the sale the midday power follows the actual SoC (it rises as SoC sinks) ...
    assert at["12:30"]["main"] > at["05:30"]["main"] >= 4500
    # ... and moves at most once an hour (a lock hour, or an SoC deviation of more than 5 pp), not every quarter.
    after_sale = [c["main"] for c in cycles if c["at"] >= datetime(2026, 10, 14, 9, 30, tzinfo=cest)]
    changes = sum(1 for a, b in zip(after_sale, after_sale[1:]) if a != b)
    assert 1 <= changes <= 4  # 9:30-13:00 is 3.5 hours


def test_the_runtime_band_lets_a_selected_morning_quarter_discharge_before_the_charge_window_ends():
    """Before the main charge window ends the discharge band is off, except for the quarters selected as a morning peak."""
    from dataclasses import replace

    plan = bm_main._plan_day(make_config(), real.import_curve(), real.export_curve(), 12, 8, 15)
    assert plan.sell_from is not None and plan.pre_window_sell_starts
    morning = sorted(plan.pre_window_sell_starts)[0]
    early = isoparse(morning).astimezone(timezone.utc)
    assert bm_main._sell_band_applies(plan, early, {"start": morning})  # the 09:00-ish peak quarter may discharge
    assert not bm_main._sell_band_applies(plan, early, {"start": real.import_curve()[44]["start"]})  # 11:00 is neither peak nor after the window
    assert not bm_main._sell_band_applies(plan, early, None)
    assert bm_main._sell_band_applies(plan, plan.sell_from, None)  # after the window the band always applies
    assert bm_main._sell_band_applies(replace(plan, sell_from=None), early, None)  # legacy mode: no gate at all
