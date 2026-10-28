"""The ledger in isolation: energy per quarter from power samples, its cost, the self-consumption baseline, totals and forecast error."""
from datetime import datetime, timedelta, timezone

from custom_components.hems.realised import DEFAULT_BANDS, MIN_BAND_SAMPLES, Ledger, PlannedQuarter, QuarterPrice

UTC = timezone.utc
T0 = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def ledger() -> Ledger:
    return Ledger(capacity_kwh=25, floor_kwh=1.25, max_kw=8, round_trip_eff=0.81)


def run(led: Ledger, start: datetime, seconds: int, grid: float, pv: float, batt: float, prices: dict, step: int = 10, soc: float = 12.5):
    closed = []
    for s in range(0, seconds + 1, step):
        closed += led.sample(start + timedelta(seconds=s), grid, pv, batt, soc, prices, UTC)
    return closed


def test_a_quarter_of_steady_import_is_priced_at_the_import_price():
    led = ledger()
    prices = {T0: QuarterPrice(0.30, 0.10, pv_kwh=0.0, load_kwh=0.2, action="idle")}
    closed = run(led, T0, 900, grid=2000, pv=0, batt=0, prices=prices)
    q = closed[0]
    assert abs(q["import_kwh"] - 0.5) < 1e-6 and q["coverage"] == 1.0 and abs(q["cost"] - 0.15) < 1e-6
    assert abs(q["load_kwh"] - 0.5) < 1e-6 and q["planned"] == "idle"
    # the baseline has the battery cover the house from 12.5 kWh, so it imports nothing
    assert q["baseline_grid_kwh"] == 0 and q["baseline_cost"] == 0
    assert led.result_today()["gain"] == -0.15 and led.gain_total() == -0.15


def test_the_baseline_stores_surplus_and_exports_only_what_does_not_fit():
    led = ledger()
    led.baseline_soc_kwh = 24.9
    prices = {T0: QuarterPrice(0.30, 0.10)}
    q = run(led, T0, 900, grid=-4000, pv=4000, batt=0, prices=prices)[0]          # 1 kWh surplus, 0.1 kWh of room
    assert q["export_kwh"] == 1.0 and 0.85 < -q["baseline_grid_kwh"] < 0.9 and q["baseline_soc_kwh"] <= 25.0


def test_a_long_gap_is_not_integrated_and_lowers_the_coverage():
    led = ledger()
    prices = {T0: QuarterPrice(0.30, 0.10)}
    led.sample(T0, 1000, 0, 0, 12.5, prices, UTC)
    led.sample(T0 + timedelta(minutes=5), 1000, 0, 0, 12.5, prices, UTC)             # 300 s gap: dropped
    closed = run(led, T0 + timedelta(minutes=5), 600, grid=1000, pv=0, batt=0, prices=prices)
    q = closed[0]
    assert q["coverage"] < 0.7 and abs(q["import_kwh"] - 1000 * 600 / 3600 / 1000) < 1e-4


def test_a_new_local_day_closes_yesterday_and_survives_a_restore():
    led = ledger()
    prices = {T0: QuarterPrice(0.30, 0.10), T0 + timedelta(days=1): QuarterPrice(0.20, 0.10)}
    run(led, T0, 900, 1000, 0, 0, prices)
    run(led, T0 + timedelta(days=1), 900, 1000, 0, 0, prices)
    days = led.daily()
    assert [d["date"] for d in days] == ["2026-10-27", "2026-10-28"] and days[-1]["today"] is True
    again = ledger()
    again.restore(led.state())
    assert again.daily() == days and again.gain_total() == led.gain_total()


def test_forecast_error_and_bands_come_from_the_own_records_once_there_are_enough():
    led = ledger()
    assert led.bands("pv") == {"p10": DEFAULT_BANDS["pv"][0], "p90": DEFAULT_BANDS["pv"][1], "source": "default", "samples": 0}
    prices = {}
    start = T0
    for i in range(MIN_BAND_SAMPLES + 4):
        at = start + timedelta(minutes=15 * i)
        prices[at] = QuarterPrice(0.3, 0.1, pv_kwh=0.5, load_kwh=0.25)
    run(led, start, 900 * (MIN_BAND_SAMPLES + 3), grid=-1000, pv=2000, batt=0, prices=prices, step=30)   # actual PV 0.5 kWh, load 0.25
    err = led.forecast_error("pv")
    assert err["mae_kwh_day"] == 0 and err["bias_kwh_day"] == 0
    band = led.bands("pv")
    assert band["source"] == "measured" and band["p10"] == band["p90"] == 1.0


def test_the_car_is_taken_out_of_the_measured_base_load_but_not_out_of_the_baseline():
    led = ledger()
    prices = {T0: QuarterPrice(0.30, 0.10, load_kwh=0.2)}
    q = []
    for sec in range(0, 901, 10):
        q += led.sample(T0 + timedelta(seconds=sec), 4000, 0, 0, 12.5, prices, UTC, ev_w=3000)
    assert abs(q[0]["load_kwh"] - 0.25) < 1e-6 and abs(q[0]["ev_kwh"] - 0.75) < 1e-6
    assert abs(q[0]["baseline_grid_kwh"]) < 1e-6          # the baseline battery covers the whole house, the car included


def test_energy_stored_above_the_baseline_is_valued_so_a_charging_day_is_not_a_loss():
    led = ledger()
    prices = {T0 + timedelta(minutes=15 * i): QuarterPrice(0.30, 0.10) for i in range(2)}
    led.sample(T0, 0, 0, 0, 12.5, prices, UTC)
    # the real battery charges 1 kWh from the grid in the first quarter, then holds it; the baseline does nothing
    run(led, T0, 900, grid=4000, pv=0, batt=4000, prices=prices, soc=12.5)
    run(led, T0 + timedelta(minutes=15), 900, grid=0, pv=0, batt=0, prices=prices, soc=13.5)
    today = led.daily()[-1]
    assert abs(today["cost"] - 0.30) < 1e-3 and abs(today["stock_kwh"] - 1.0) < 1e-3
    assert abs(today["stock_value"] - 0.30) < 1e-3 and abs(today["gain"]) < 1e-3
    assert today["import_kwh"] > 0.99 and today["avg_import"] == 0.3


def test_a_stored_day_from_before_the_energy_fields_gets_one_shape():
    led = ledger()
    led.restore({"days": [{"date": "2026-10-20", "cost": 1.0, "baseline_cost": 1.5, "quarters": 96}]})
    row = led.daily()[0]
    assert row["gain"] == 0.5 and row["import_kwh"] == 0.0 and row["stock_value"] == 0.0


def test_the_rest_of_today_prices_the_plan_against_the_same_baseline_and_stops_at_midnight():
    led = ledger()
    prices = {T0: QuarterPrice(0.30, 0.10)}
    run(led, T0, 900, grid=0, pv=0, batt=0, prices=prices, soc=12.5)          # one measured quarter, baseline and battery level
    start = T0 + timedelta(minutes=15)
    # the plan sells 1 kWh at 0.50 in the next quarter; the house uses nothing; one quarter after midnight must not count
    planned = [PlannedQuarter(start, 0.30, 0.50, 0.0, 0.0, -1.0, 11.25),
               PlannedQuarter(datetime(2026, 10, 28, 0, 0, tzinfo=UTC), 0.30, 0.50, 0.0, 0.0, -1.0, 10.0)]
    rest = led.rest_of_day(planned, UTC)
    assert rest["quarters"] == 1 and rest["cost"] == -0.5 and rest["baseline_cost"] == 0.0
    # 1.25 kWh left the battery that the baseline still holds, valued at today's 0.30
    assert rest["stock_value"] == -0.38 and rest["gain"] == 0.12 and rest["end_of_day"] == round(led.daily()[-1]["gain"] + 0.12, 2)
