"""Task G: top-X sell hours are picked from quarters after the charge window."""

from datetime import timedelta

from Tests import curves_2026_10_07 as curves
from Tests.plan_replay import amsterdam_tz, local_start, make_config, replay  # noqa: F401


def _sells(schedule):
    return [p for p in schedule["discharge"] if p["window_type"] == "discharge"]


def _span(period):
    start = local_start(period)
    return start, start + timedelta(minutes=period["duration"])


def test_charge_window_and_sell_hours_on_2026_10_07(monkeypatch, amsterdam_tz):
    updates = []
    schedule = replay(monkeypatch, "12:00", soc=46, remaining_solar=10.0, entity_updates=updates)

    decision = next(attrs for entity, _s, attrs in updates if entity == "decision")
    assert decision["charge_window"][0].startswith("2026-10-07T11:15")
    assert decision["charge_window"][1].startswith("2026-10-07T16:00")

    today = [p for p in _sells(schedule) if local_start(p).day == 7]
    assert today, "evening sell expected"
    for period in today:
        start, end = _span(period)
        assert start >= curves.at(7, "16:00") and end <= curves.at(8, "00:00")
    assert sum(p["duration"] for p in today) <= 120  # X = 2h


def test_morning_peak_neither_sells_from_the_budget_nor_precharges_at_night(monkeypatch, amsterdam_tz):
    config = make_config(**{"heuristics.min_profit_threshold": 0.05})
    schedule = replay(monkeypatch, "21:30", soc=46, remaining_solar=0.0, config=config)

    tomorrow_sells = [p for p in _sells(schedule) if local_start(p).day == 8]
    morning = [p for p in tomorrow_sells if local_start(p).hour < 11]
    assert morning == []  # 08:00 @0.401 is before tomorrow's 11:30 charge window
    night_charge = [
        p for p in schedule["charge"]
        if local_start(p).day == 7 and local_start(p).hour >= 21
    ]
    assert night_charge == []  # no 21:45 / 22:45 charge


def test_legacy_mode_still_picks_the_morning_peak(monkeypatch, amsterdam_tz):
    config = make_config(**{
        "heuristics.discharge_after_charge_only": False,
        "heuristics.min_profit_threshold": 0.05,
    })
    schedule = replay(monkeypatch, "21:30", soc=46, remaining_solar=0.0, config=config)

    morning = [p for p in _sells(schedule) if local_start(p).day == 8 and local_start(p).hour < 11]
    assert morning, "without the option tomorrow's 08:00 peak consumes the sell budget"


def test_sell_budget_is_not_used_up_by_quarters_before_the_charge_window(amsterdam_tz):
    """Even when the morning is the priciest part of the day, X hours are sold after charging."""
    from app.main import _plan_day

    imports, exports = [], []
    for index in range(96):
        start = curves.at(7, "00:00") + timedelta(minutes=15 * index)
        hour = start.hour
        import_price = 0.15 if 11 <= hour < 14 else 0.30
        export_price = 0.70 if 7 <= hour < 9 else (0.50 if 18 <= hour < 20 else 0.25)
        entry = {"start": start.isoformat(), "end": (start + timedelta(minutes=15)).isoformat()}
        imports.append({**entry, "price": import_price})
        exports.append({**entry, "price": export_price})

    config = make_config()
    legacy = _plan_day(make_config(**{"heuristics.discharge_after_charge_only": False}),
                       imports, exports, 12, 8, 15)
    plan = _plan_day(config, imports, exports, 12, 8, 15)

    legacy_hours = sorted({s[11:13] for s in legacy.discharge_slot_starts})
    plan_hours = sorted({s[11:13] for s in plan.discharge_slot_starts})
    assert legacy_hours == ["07", "08"]  # all 8 quarters go to the morning
    assert plan_hours == ["18", "19"]  # sold after the 11:00-14:00 charge window
    assert plan.sell_from is not None and plan.sell_from.hour == 14


def test_clear_spread_day_is_unchanged(monkeypatch, amsterdam_tz):
    """2026-10-06 style: cheap midday, 7 kW sell 18:00-20:00 @0.54-0.59 either way."""
    def build(day):
        imports, exports = [], []
        for index in range(96):
            start = curves.at(day, "00:00") + timedelta(minutes=15 * index)
            hour = start.hour
            import_price = 0.18 if 11 <= hour < 14 else (0.52 if 18 <= hour < 20 else 0.30)
            export_price = {18: 0.54, 19: 0.59}.get(hour, 0.20 if 11 <= hour < 14 else 0.28)
            entry = {"start": start.isoformat(), "end": (start + timedelta(minutes=15)).isoformat()}
            imports.append({**entry, "price": import_price})
            exports.append({**entry, "price": export_price})
        return imports, exports

    imports, exports = build(6)

    def plan(option):
        config = make_config(**{"heuristics.discharge_after_charge_only": option})
        schedule = replay(
            monkeypatch, "10:00", soc=60, remaining_solar=0.0, day=6,
            import_curve=imports, export_curve=exports, config=config,
        )
        return [
            (p["start"], p["duration"], p["power"])
            for p in schedule["discharge"] if p["window_type"] == "discharge"
        ]

    with_option = plan(True)
    assert with_option and with_option == plan(False)
    first = local_start({"start": with_option[0][0]})
    assert first.strftime("%H:%M") == "18:00" and with_option[0][1] == 120
