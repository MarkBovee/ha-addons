"""Task B: non-top-X grid charging needs sell * efficiency - charge >= margin."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app import main as bm_main
from app.margin import charge_margin, evaluate_grid_charge, intended_sell_price
from Tests.plan_replay import amsterdam_tz, local_start, make_config, replay  # noqa: F401

T0 = datetime(2026, 10, 7, 21, 45, tzinfo=timezone.utc)


def _sell(hours_from_now: float, price: float, minutes: int = 60):
    start = T0 + timedelta(hours=hours_from_now)
    return {"start": start, "end": start + timedelta(minutes=minutes), "avg_price": price}


def test_charge_margin_formula():
    assert charge_margin(0.401, 0.334, 0.90) == pytest.approx(0.0269)
    assert charge_margin(0.422, 0.315, 0.90) == pytest.approx(0.0648)


def test_incident_night_charge_is_rejected_for_both_target_windows():
    """21:45 @0.334 -> 08:00 @0.401 and 22:45 @0.315 -> 19:00 @0.422 lose to the 10% loss."""
    night = {"start": T0, "end": T0 + timedelta(minutes=15), "avg_price": 0.334}
    morning = _sell(10.25, 0.401)
    verdict = evaluate_grid_charge(
        charge_price=0.334, charge_end=night["end"], discharge_windows=[morning],
        charge_windows=[], efficiency=0.90, min_margin=0.10,
    )
    assert not verdict["allowed"]
    assert verdict["margin"] == pytest.approx(0.027, abs=1e-3)

    evening = _sell(21.25, 0.422)
    verdict = evaluate_grid_charge(
        charge_price=0.315, charge_end=T0 + timedelta(hours=2), discharge_windows=[evening],
        charge_windows=[], efficiency=0.90, min_margin=0.10,
    )
    assert not verdict["allowed"]


def test_charge_with_enough_spread_is_allowed():
    verdict = evaluate_grid_charge(
        charge_price=0.20, charge_end=T0, discharge_windows=[_sell(3, 0.56)],
        charge_windows=[], efficiency=0.90, min_margin=0.10,
    )
    assert verdict["allowed"] and verdict["margin"] == pytest.approx(0.304)


def test_no_following_sell_window_means_no_charge():
    verdict = evaluate_grid_charge(
        charge_price=0.20, charge_end=T0, discharge_windows=[],
        charge_windows=[], efficiency=0.90, min_margin=0.10,
    )
    assert not verdict["allowed"] and "no sell window" in verdict["reason"]


def test_intended_sell_price_stops_at_next_charge_window_and_is_duration_weighted():
    windows = [_sell(1, 0.40, 60), _sell(2, 0.50, 180), _sell(10, 0.90, 60)]
    result = intended_sell_price(T0, windows, next_charge_start=T0 + timedelta(hours=8))
    assert result is not None
    assert result[0] == pytest.approx((0.40 * 60 + 0.50 * 180) / 240)
    assert len(result[1]) == 2


def _gate(config, charge_windows, discharge_windows, exact=frozenset()):
    records = []
    kept = bm_main._apply_grid_charge_margin_gate(
        config,
        {"charge": charge_windows, "discharge": discharge_windows},
        set(exact),
        T0 - timedelta(hours=1),
        records,
    )
    return kept, records


def test_gate_exempts_top_x_negative_and_past_windows():
    config = make_config()
    top_x = {"start": T0, "end": T0 + timedelta(hours=1), "avg_price": 0.30, "slots": [{"start": T0}]}
    negative = {"start": T0 + timedelta(hours=2), "end": T0 + timedelta(hours=3), "avg_price": -0.1}
    past = {"start": T0 - timedelta(hours=5), "end": T0 - timedelta(hours=4), "avg_price": 0.30}

    kept, records = _gate(config, [top_x, negative, past], [], exact={T0})

    assert kept == [top_x, negative, past]
    assert records == []


def test_gate_defaults_follow_min_profit_and_options_override():
    window = {"start": T0, "end": T0 + timedelta(hours=1), "avg_price": 0.30, "slots": []}
    sell = [_sell(2, 0.45)]  # 0.45 * 0.9 - 0.30 = 0.105

    config = make_config()
    assert _gate(config, [window], sell)[0] == [window]  # 0.105 >= min_profit 0.10

    config["heuristics"]["min_profit_threshold"] = 0.12
    kept, records = _gate(config, [window], sell)
    assert kept == [] and not records[0]["allowed"]  # margin default tracks min_profit

    config["heuristics"]["grid_charge_min_margin"] = 0.05
    assert _gate(config, [window], sell)[0] == [window]

    config["heuristics"]["grid_charge_min_margin"] = 0.05
    config["heuristics"]["round_trip_efficiency"] = 0.80  # 0.36 - 0.30 = 0.06 still ok
    assert _gate(config, [window], sell)[0] == [window]
    config["heuristics"]["round_trip_efficiency"] = 0.70  # 0.315 - 0.30 = 0.015
    assert _gate(config, [window], sell)[0] == []


def test_night_spread_window_is_skipped_on_2026_10_07(monkeypatch, amsterdam_tz):
    """The 22:45 @0.315 block (spread-only, no profitable sell after it) is not charged."""
    schedule = replay(monkeypatch, "21:30", soc=46, remaining_solar=0.0, entity_updates=[])

    night = [p for p in schedule["charge"] if local_start(p).day == 7 and local_start(p).hour >= 21]
    assert night == []


def test_skipped_window_is_recorded_in_the_trace(monkeypatch, amsterdam_tz):
    updates = []
    replay(monkeypatch, "21:30", soc=46, remaining_solar=0.0, entity_updates=updates)

    decision = next(attrs for entity, _state, attrs in updates if entity == "decision")
    skipped = [g for g in decision["margin_gate"] if not g["allowed"]]
    assert any(g["start"].startswith("2026-10-07T22:45") for g in skipped)
    assert all("reason" in g for g in skipped)


def _precharge_config():
    config = deepcopy(bm_main.DEFAULT_CONFIG)
    config.update({"dry_run": True})
    config["heuristics"]["discharge_after_charge_only"] = False
    config["adaptive"]["enabled"] = False
    config["negative_price_charging"]["enabled"] = False
    config["solar_aware_charging"]["enabled"] = False
    config["temperature_based_discharge"]["enabled"] = False
    config["soc"].update({"min_soc": 5, "conservative_soc": 25, "sell_buffer_min_soc": 20})
    config["power"].update({"max_discharge_power": 8000, "min_discharge_power": 4000, "min_scaled_power": 4000})
    config["heuristics"].update({
        "top_x_charge_hours": 0.25, "top_x_discharge_hours": 1, "min_profit_threshold": 0.10,
        "sell_wait_for_better_morning_enabled": False, "adaptive_price_threshold": 0.25,
    })
    return config


def _precharge_schedule(monkeypatch, config, sell_price):
    now = datetime.now(timezone.utc)
    start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    imports = [0.20, 0.20, 0.20, 0.20, 0.05]
    exports = [sell_price] * 4 + [0.05]

    def curve(prices):
        return [
            {"start": (start + timedelta(minutes=15 * i)).isoformat(),
             "end": (start + timedelta(minutes=15 * (i + 1))).isoformat(), "price": p}
            for i, p in enumerate(prices)
        ]

    monkeypatch.setattr(bm_main, "_get_price_curve", lambda *_: curve(imports))
    monkeypatch.setattr(bm_main, "_get_export_price_curve", lambda *_: curve(exports))
    monkeypatch.setattr(bm_main, "_get_schedule_generation_soc", lambda *a, **k: 30.0)
    monkeypatch.setattr(bm_main, "update_entity", lambda *a, **k: None)
    monkeypatch.setattr(bm_main, "_get_schedule_slot_limits", lambda *_: (3, 6))
    return bm_main.generate_schedule(config, object(), None)


def test_precharge_needs_margin_unless_below_the_safety_floor(monkeypatch):
    rich = _precharge_schedule(monkeypatch, _precharge_config(), sell_price=0.60)
    assert any(p["window_type"] == "precharge" for p in rich["charge"])  # 0.54 - 0.20 = 0.34

    thin = _precharge_schedule(monkeypatch, _precharge_config(), sell_price=0.28)
    assert not any(p["window_type"] == "precharge" for p in thin["charge"])  # 0.252 - 0.20 = 0.05
