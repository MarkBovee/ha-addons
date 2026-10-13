from hems.prices import PriceModel, curves
from hems.battery import BatteryConfig, Slot, plan
from hems.balancer import Load, allocate
from hems.forecast import hourly_profile, to_slots_kwh


def mk(market, load_w=300, pv_w=None):
    m = PriceModel()
    imp, exp = curves(market, m)
    pv_w = pv_w or [0] * len(market)
    return [Slot(i, e, load_w / 1000 * .25, p / 1000 * .25) for i, e, p in zip(imp, exp, pv_w)]


def hourly_to_quarters(hourly):
    return [p for p in hourly for _ in range(4)]


def test_price_formulas():
    m = PriceModel()
    assert abs(m.import_price(0.10) - (0.121 + 0.11085 + 0.02)) < 1e-9
    assert abs(m.export_price(0.10) - (0.10 * 1.331 + 0.13085)) < 1e-9
    assert abs(PriceModel(salderen=False).export_price(0.10) - 0.13) < 1e-9


def test_clear_spread_charges_cheap_discharges_peak():
    # night 0.02, day 0.10, evening peak 0.30 (market EUR/kWh), 24 h
    mk_h = [0.02] * 6 + [0.10] * 12 + [0.30] * 4 + [0.10] * 2
    slots = mk(hourly_to_quarters(mk_h))
    p = plan(slots, 0.30 * 25, BatteryConfig())
    ch = [s.index for s in p.slots if s.action == "charge"]
    di = [s.index for s in p.slots if s.action == "discharge"]
    assert ch and di
    assert max(ch) < min(di)                  # discharge happens AFTER the charge window
    assert all(18 * 4 <= i < 22 * 4 for i in di)
    assert p.saving > 0


def test_thin_spread_no_cycling():
    mk_h = [0.10] * 12 + [0.115] * 12
    p = plan(mk(hourly_to_quarters(mk_h)), 0.30 * 25, BatteryConfig())
    assert all(s.action == "idle" for s in p.slots)


def test_wear_cost_blocks_marginal_cycles():
    mk_h = [0.10] * 12 + [0.16] * 12
    cheap = plan(mk(hourly_to_quarters(mk_h)), 0.5 * 25, BatteryConfig(wear_cost=0.0))
    dear = plan(mk(hourly_to_quarters(mk_h)), 0.5 * 25, BatteryConfig(wear_cost=0.10))
    assert sum(s.action != "idle" for s in cheap.slots) > sum(s.action != "idle" for s in dear.slots)


def test_never_below_floor():
    mk_h = [0.30] * 24
    p = plan(mk(hourly_to_quarters(mk_h)), 0.31 * 25, BatteryConfig())
    assert min(s.soc_kwh for s in p.slots) >= 0.30 * 25 - 1e-9


def test_balancer_priorities_and_min_power():
    out = allocate(9000, [Load("ev", 11000, 2, min_w=4100), Load("battery", 8000, 1)], 15000)
    assert out["battery"] == 6000 and out["ev"] == 0   # battery first, EV below min -> off
    out = allocate(2000, [Load("ev", 11000, 2, min_w=4100), Load("battery", 8000, 1)], 15000)
    assert out["battery"] == 8000 and out["ev"] == 5000
    # hysteresis: running EV survives 4000 W headroom, a stopped one does not
    loads = [Load("ev", 11000, 2, min_w=4100)]
    assert allocate(11000, loads, 15000, previous={"ev": 4100})["ev"] == 4100
    assert allocate(11000, loads, 15000)["ev"] == 0


def test_forecast_median_robust():
    hist = [(h, 300.0) for _ in range(7) for h in range(24)]
    hist[10] = (10, 9000.0)   # one EV spike
    prof = hourly_profile(hist)
    assert prof[10] == 300.0
    assert abs(sum(to_slots_kwh(prof, 0, 4)) - 0.3) < 1e-9
