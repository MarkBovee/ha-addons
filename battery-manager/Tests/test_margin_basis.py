"""Task C: margin_basis day_min_import | solar_export on the 2026-10-07 curves."""

from app import main as bm_main
from app.price_analyzer import calculate_price_ranges, find_profitable_discharge_starts
from Tests import curves_2026_10_07 as curves
from Tests.plan_replay import amsterdam_tz, make_config  # noqa: F401


def _today():
    imports, _ = bm_main._split_curve_by_date(curves.import_curve(), curves.at(7, "12:00"))
    exports, _ = bm_main._split_curve_by_date(curves.export_curve(), curves.at(7, "12:00"))
    return imports, exports


def test_default_basis_is_day_min_import_and_unchanged(amsterdam_tz):
    imports, exports = _today()

    legacy = find_profitable_discharge_starts(imports, exports, 24, 0.10)
    explicit = find_profitable_discharge_starts(imports, exports, 24, 0.10, cost_basis=None)

    assert legacy == explicit
    # Day min import is 0.31, so the threshold is 0.41: the 0.40 and 0.38 export quarters fail.
    prices = {e["start"]: e["price"] for e in exports}
    assert min(prices[s] for s in legacy) >= 0.41 - 1e-9
    _, discharge, _ = calculate_price_ranges(imports, exports, 12, 24, 0.10)
    assert discharge.min_price >= 0.41 - 1e-9


def test_solar_export_basis_lowers_the_threshold_to_forgone_export_price(amsterdam_tz):
    imports, exports = _today()

    day_min = find_profitable_discharge_starts(imports, exports, 24, 0.10)
    solar = find_profitable_discharge_starts(imports, exports, 24, 0.10, cost_basis=0.20)

    # 0.20 + 0.10 = 0.30: the 0.40 / 0.38 evening quarters now qualify.
    assert day_min < solar
    prices = {e["start"]: e["price"] for e in exports}
    added = sorted(prices[s] for s in solar - day_min)
    assert added and added[0] >= 0.30 and added[-1] < 0.41

    _, discharge, _ = calculate_price_ranges(imports, exports, 12, 24, 0.10, cost_basis=0.20)
    assert discharge.min_price < 0.41


def test_plan_day_uses_planned_pv_window_export_price(amsterdam_tz):
    imports, exports = _today()
    config = make_config(**{"heuristics.top_x_discharge_hours": 6})
    config["heuristics"]["margin_basis"] = "solar_export"

    plan = bm_main._plan_day(config, imports, exports, 12, 24, 15, None, "2026-10-07")
    legacy = bm_main._plan_day(make_config(**{"heuristics.top_x_discharge_hours": 6}),
                               imports, exports, 12, 24, 15, None, "2026-10-07")

    assert plan.basis_source == "solar_export"
    assert plan.cost_basis == 0.20  # lowest export price in the 11:15-16:00 charge window
    assert legacy.basis_source == "day_min_import" and legacy.cost_basis is None
    assert legacy.day_min_import == 0.31  # midday import
    assert len(plan.discharge_slot_starts) > len(legacy.discharge_slot_starts)


def test_actual_pv_window_price_lowers_basis_further(amsterdam_tz):
    imports, exports = _today()
    config = make_config()
    config["heuristics"]["margin_basis"] = "solar_export"
    state = bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)
    state.pv_charge_export_min["2026-10-07"] = 0.12

    plan = bm_main._plan_day(config, imports, exports, 12, 8, 15, state, "2026-10-07")

    assert plan.cost_basis == 0.12


def test_negative_export_price_never_gives_a_free_pass(amsterdam_tz):
    imports, exports = _today()
    exports = [dict(e, price=-0.05) if "T12:" in e["start"] else e for e in exports]
    config = make_config()
    config["heuristics"]["margin_basis"] = "solar_export"

    plan = bm_main._plan_day(config, imports, exports, 12, 8, 15, None, "2026-10-07")

    assert plan.cost_basis == 0.0


def test_solar_export_without_known_pv_window_falls_back(amsterdam_tz):
    config = make_config()
    config["heuristics"]["margin_basis"] = "solar_export"
    flat = [{"start": curves.at(7, "00:00").isoformat(), "price": 0.30}]

    plan = bm_main._plan_day(config, flat, flat, 0, 8, 15, None, "2026-10-07")  # no charge slots

    assert plan.cost_basis is None
    assert "no PV charge window" in plan.basis_source
