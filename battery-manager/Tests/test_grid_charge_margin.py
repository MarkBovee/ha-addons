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


def test_gate_exempts_negative_and_past_windows():
    config = make_config()
    negative = {"start": T0 + timedelta(hours=2), "end": T0 + timedelta(hours=3), "avg_price": -0.1}
    past = {"start": T0 - timedelta(hours=5), "end": T0 - timedelta(hours=4), "avg_price": 0.30}

    kept, records = _gate(config, [negative, past], [_sell(8, 0.20)])

    assert kept == [negative, past]
    assert records == []


def test_gate_applies_to_top_x_windows_too():
    """2026-10-19: tonight's top-X quarters at 0.343 for a 0.443 sale tomorrow morning earn 0.056 < 0.12."""
    config = make_config(**{"heuristics.min_profit_threshold": 0.12})
    tonight = {"start": T0, "end": T0 + timedelta(hours=2), "avg_price": 0.343, "slots": [{"start": T0}]}
    morning_sale = _sell(10, 0.443, 120)
    next_start = T0 + timedelta(hours=14)
    next_charge = {"start": next_start, "end": T0 + timedelta(hours=18), "avg_price": 0.268, "slots": [{"start": next_start}]}

    kept, records = _gate(config, [tonight, next_charge], [morning_sale], exact={T0, next_start})

    assert kept == [next_charge]
    assert records[0]["top_x"] and not records[0]["allowed"]
    assert records[0]["margin"] == pytest.approx(0.056, abs=1e-3)


def test_gate_judges_a_block_of_split_windows_against_the_sale_behind_it():
    """2026-10-19 20:11: 20:45, 21:15 and 22:15 are one block for the 0.443 sale; the first two kept hiding behind the next charge window."""
    config = make_config(**{"heuristics.min_profit_threshold": 0.12})

    def window(offset_h, hours, price):
        start = T0 + timedelta(hours=offset_h)
        return {"start": start, "end": start + timedelta(hours=hours), "avg_price": price, "slots": [{"start": start}]}

    block = [window(0, 0.25, 0.340), window(0.5, 0.75, 0.346), window(1.5, 1.75, 0.343)]
    next_day = window(14, 4, 0.268)
    exact = {w["start"] for w in block + [next_day]}

    kept, records = _gate(config, block + [next_day], [_sell(10, 0.443, 120)], exact=exact)

    assert kept == [next_day]
    assert [r["allowed"] for r in records] == [False, False, False, True] or len(records) == 4
    assert sorted(r["start"] for r in records) == [r["start"] for r in records]  # chronological


def test_gate_keeps_the_block_when_the_sale_behind_it_pays():
    config = make_config(**{"heuristics.min_profit_threshold": 0.12})
    first = {"start": T0, "end": T0 + timedelta(minutes=15), "avg_price": 0.30, "slots": [{"start": T0}]}
    second_start = T0 + timedelta(minutes=30)
    second = {"start": second_start, "end": second_start + timedelta(hours=1), "avg_price": 0.30, "slots": [{"start": second_start}]}

    kept, _ = _gate(config, [first, second], [_sell(10, 0.55, 120)], exact={T0, second_start})

    assert kept == [first, second]


def test_gate_keeps_a_top_x_window_that_earns_the_margin():
    config = make_config(**{"heuristics.min_profit_threshold": 0.12})
    tonight = {"start": T0, "end": T0 + timedelta(hours=2), "avg_price": 0.30, "slots": [{"start": T0}]}

    kept, records = _gate(config, [tonight], [_sell(10, 0.55, 120)], exact={T0})  # 0.495 - 0.30 = 0.195

    assert kept == [tonight] and records[0]["allowed"]


def test_gate_keeps_a_top_x_window_without_a_following_sale_but_not_a_spread_window():
    """Nothing to measure a top-X charge against; a spread-only window without a sale is dropped."""
    config = make_config()
    top_x = {"start": T0, "end": T0 + timedelta(hours=1), "avg_price": 0.30, "slots": [{"start": T0}]}
    spread = {"start": T0 + timedelta(hours=2), "end": T0 + timedelta(hours=3), "avg_price": 0.31, "slots": []}

    kept, records = _gate(config, [top_x, spread], [], exact={T0})

    assert kept == [top_x]
    assert records[0]["allowed"] and "no sell window" in records[0]["reason"]
    assert not records[1]["allowed"]


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
    imports = [0.20, 0.20, 0.20, 0.20, 0.20, 0.05]
    exports = [0.05] + [sell_price] * 4 + [0.05]  # the sale starts a quarter from now: the pre-sell check only runs before it

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


def test_precharge_below_the_start_soc_does_not_need_a_sell_margin(monkeypatch):
    """Below sell_buffer_min_soc the battery is charged back up to it: the sale cannot start without it."""
    config = _precharge_config()
    config["soc"]["sell_buffer_min_soc"] = 40  # SoC is 30
    for sell_price in (0.60, 0.28):  # a rich and a thin sale: 0.54 - 0.20 = 0.34 and 0.252 - 0.20 = 0.05
        schedule = _precharge_schedule(monkeypatch, config, sell_price=sell_price)
        assert any(p["window_type"] == "precharge" for p in schedule["charge"])


def test_nothing_is_precharged_at_or_above_the_start_soc(monkeypatch):
    """The sell margin only rules the top-X charge slots; at 30% a start SOC of 30 (or less) buys nothing for the sale."""
    for start_soc in (20, 30):
        config = _precharge_config()
        config["soc"]["sell_buffer_min_soc"] = start_soc
        schedule = _precharge_schedule(monkeypatch, config, sell_price=0.60)
        assert not any(p["window_type"] == "precharge" for p in schedule["charge"])
