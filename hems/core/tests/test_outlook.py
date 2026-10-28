from datetime import datetime, timedelta, timezone

from test_rolling import recorded_day

from hems.battery import BatteryConfig
from hems.forecast import LOCAL_TZ
from hems.outlook import cheapest_block, first_window, forecast_series, hour_mean, hour_total, price_curve, window_total
from hems.prices import PriceSeries
from hems.rolling import HorizonInputs, plan_next

START = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)          # 10:00 local
QUARTER = timedelta(minutes=15)


def quarters(*values: float, start: datetime = START) -> dict[datetime, float]:
    """A series with one value per quarter from `start`."""
    return {start + i * QUARTER: v for i, v in enumerate(values)}


def test_the_coming_hour_is_four_quarters_and_never_a_partial_hour():
    """Energy adds up, irradiance averages; with a quarter missing the answer is unknown, not a figure that reads too low."""
    series = quarters(0.1, 0.2, 0.3, 0.4, 0.5)
    assert hour_total(series, START) == 1.0 and hour_total(series, START + QUARTER) == 1.4
    assert hour_mean(quarters(100, 200, 300, 400), START) == 250.0
    assert hour_total(series, START + 2 * QUARTER) is None and hour_mean(series, START + 2 * QUARTER) is None
    assert hour_total({}, START) is None


def test_the_energy_in_a_window_counts_the_quarters_that_start_inside_it():
    """[begin, end): the quarter that starts at `end` belongs to the next window; unknown quarters count as nothing."""
    series = quarters(1.0, 2.0, 3.0, 4.0)
    assert window_total(series, START + QUARTER, START + 3 * QUARTER) == 5.0
    assert window_total(series, START, START) == 0.0
    assert window_total(series, START + 3 * QUARTER, START + 8 * QUARTER) == 4.0


def test_a_forecast_series_is_in_local_time_skips_what_is_unknown_and_is_cut_at_the_limit():
    """What a dashboard chart reads: local ISO times, one value per known quarter."""
    series = {**quarters(0.1234, 0.2), START + 3 * QUARTER: 0.4}
    points = forecast_series(series, START, LOCAL_TZ, "kwh")
    assert points == [{"start": "2026-10-14T10:00:00+02:00", "kwh": 0.123}, {"start": "2026-10-14T10:15:00+02:00", "kwh": 0.2},
                      {"start": "2026-10-14T10:45:00+02:00", "kwh": 0.4}]
    assert len(forecast_series(quarters(*range(10)), START, LOCAL_TZ, "w", limit=4)) == 4


def test_the_price_curve_starts_now_and_carries_import_and_export_separately():
    """The recorded day of 6 Oct: the curve from 12:00 local on, the same numbers the planner reads."""
    prices = recorded_day("2026-10-06")
    now = datetime(2026, 10, 6, 12, 0, tzinfo=LOCAL_TZ)
    imp, exp = price_curve(prices, "import", now, LOCAL_TZ), price_curve(prices, "export", now, LOCAL_TZ)
    assert imp[0]["start"] == "2026-10-06T12:00:00+02:00" and len(imp) == len(exp) == sum(1 for t in prices.starts if t >= now)
    first = prices.starts.index(now)
    assert imp[0]["price"] == round(prices.import_eur_kwh[first], 4) and exp[0]["price"] == round(prices.export_eur_kwh[first], 4)
    assert all(p["price"] is not None for p in imp)


def test_the_first_window_of_a_real_plan_has_times_and_the_energy_the_plan_expects_in_it():
    """A plan from 06:07 with a half-empty battery: the first charge comes before the first discharge, PV in the window is what the slots say."""
    now = datetime(2026, 10, 6, 6, 7, tzinfo=LOCAL_TZ)
    decision = plan_next(HorizonInputs(now, 8.0, recorded_day("2026-10-06"), {}, {}), BatteryConfig())
    charge, discharge = first_window(decision.trace["segments"], "charge"), first_window(decision.trace["segments"], "discharge")
    assert charge is not None and discharge is not None and charge["begin"] >= decision.slot_start and charge["end"] > charge["begin"]
    assert isinstance(charge["begin"], datetime) and charge["begin"].tzinfo is not None and charge["kwh"] > 0
    pv = {decision.slot_start + i * QUARTER: s.pv_kwh for i, s in enumerate(decision.slots)}
    in_window = sum(s.pv_kwh for i, s in enumerate(decision.slots) if charge["begin"] <= decision.slot_start + i * QUARTER < charge["end"])
    assert window_total(pv, charge["begin"], charge["end"], digits=6) == round(in_window, 6)


def test_a_plan_without_the_action_has_no_window():
    """Nothing planned: None, so a sensor can say unknown instead of inventing a time."""
    assert first_window([{"action": "idle", "from": START.isoformat(), "to": (START + QUARTER).isoformat()}], "charge") is None
    assert first_window([], "discharge") is None


def segment(action: str, begin_q: int, end_q: int, kwh: float = 0.0, price: float | None = None, soc: tuple[float, float] = (50.0, 50.0)) -> dict:
    """A plan segment between two quarters counted from START."""
    return {"action": action, "from": (START + begin_q * QUARTER).isoformat(), "to": (START + end_q * QUARTER).isoformat(), "kwh": kwh,
            "avg_w": round(kwh * 4000 / (end_q - begin_q)) if kwh else 0, "avg_price": price, "soc_from_pct": soc[0], "soc_to_pct": soc[1]}


def test_a_period_continues_over_idle_quarters_and_ends_where_the_opposite_action_starts():
    """The plan charges in pieces (an idle quarter where the price bumps): that is still one charge period, up to the next sale."""
    segments = [segment("idle", 0, 2), segment("charge", 2, 10, 4.0, 0.20, (40, 56)), segment("idle", 10, 11), segment("charge", 11, 13, 1.0, 0.30, (56, 60)),
                segment("idle", 13, 20), segment("discharge", 20, 24, 3.0, 0.50, (60, 48)), segment("idle", 24, 26), segment("discharge", 26, 28, 1.0, 0.40, (48, 44)),
                segment("charge", 40, 44, 2.0, 0.25, (44, 52))]
    charge, discharge = first_window(segments, "charge"), first_window(segments, "discharge")
    assert (charge["begin"], charge["end"]) == (START + 2 * QUARTER, START + 13 * QUARTER) and charge["kwh"] == 5.0
    assert charge["avg_price"] == 0.22 and (charge["soc_from_pct"], charge["soc_to_pct"]) == (40, 60)
    assert charge["avg_w"] == round(5.0 * 1000 / (10 * 0.25))                 # 10 active quarters, the idle one does not count
    assert (discharge["begin"], discharge["end"]) == (START + 20 * QUARTER, START + 28 * QUARTER) and discharge["kwh"] == 4.0
    assert discharge["avg_price"] == 0.475 and (discharge["soc_from_pct"], discharge["soc_to_pct"]) == (60, 44), "the later charge is another period"
    assert (charge["active_min"], discharge["active_min"]) == (150, 90), "the pauses inside a period are not counted as charging or selling"


def test_the_period_that_is_going_on_starts_at_the_current_quarter():
    """The first segment is the quarter now: a charge in progress is the first charge period, not a later one."""
    segments = [segment("charge", 0, 3, 1.5, 0.2, (30, 36)), segment("idle", 3, 8), segment("discharge", 8, 12, 2.0, 0.5, (36, 28)), segment("charge", 20, 24, 3.0, 0.2, (28, 40))]
    now = first_window(segments, "charge")
    assert now["begin"] == START and now["end"] == START + 3 * QUARTER and now["kwh"] == 1.5


def test_a_rest_of_more_than_an_hour_splits_a_period_so_the_window_is_not_a_whole_morning():
    """The night charge is the first charge window; the midday top-up three hours later is a period of its own."""
    segments = [segment("charge", 0, 8, 5.0, 0.20, (30, 60)), segment("idle", 8, 20), segment("charge", 20, 24, 2.0, 0.25, (60, 70))]
    first = first_window(segments, "charge")
    assert first["end"] == START + 8 * QUARTER and first["kwh"] == 5.0


def import_series(*prices: float, start: datetime = START) -> PriceSeries:
    """Import prices (export the same) per quarter from `start`."""
    return PriceSeries(tuple(start + i * QUARTER for i in range(len(prices))), tuple(prices), tuple(prices))


def test_the_cheapest_block_is_the_cheapest_run_of_consecutive_quarters_from_now_on():
    """Three quarters of 0.20 sit between dear ones; the block of 3 starting there wins, an earlier valley before `start` does not count, and the average is reported."""
    series = import_series(0.05, 0.05, 0.05, 0.40, 0.30, 0.20, 0.20, 0.20, 0.35, 0.40)
    block = cheapest_block(series, START + 3 * QUARTER, quarters=3)
    assert (block["begin"], block["end"], block["avg_price"]) == (START + 5 * QUARTER, START + 8 * QUARTER, 0.20)


def test_equal_blocks_take_the_earliest_and_a_short_horizon_has_no_block():
    """A flat curve starts at once; fewer known quarters than the block needs is None, never a shorter block that reads cheaper."""
    assert cheapest_block(import_series(0.3, 0.3, 0.3, 0.3), START, quarters=2)["begin"] == START
    assert cheapest_block(import_series(0.3, 0.3), START, quarters=3) is None


def _day_series() -> PriceSeries:
    """A local day of 96 quarters (UTC grid) plus the first quarter of the next day: imports 0.10 to 0.40, exports 0.05 to 0.35."""
    first = datetime(2026, 10, 26, 23, 0, tzinfo=timezone.utc)                  # 00:00 local on 27 Oct (CET after the clock change on 25 Oct)
    starts = tuple(first + i * QUARTER for i in range(97))
    imports = tuple(round(0.10 + 0.30 * (i % 96) / 95, 4) for i in range(97))
    return PriceSeries(starts, imports, tuple(round(p - 0.05, 4) for p in imports))


def test_the_price_curve_for_a_day_keeps_the_past_quarters_in_the_shape_of_the_energy_prices_sensor():
    """Intent: the curve starts at local midnight even late in the day, carries start, end and price in UTC, and includes the following day's known quarters.
    Why: the water heater add-on and the dashboard charts read the whole day from the old sensor; a curve that starts at 'now' would break them."""
    from hems.outlook import price_curve_for_day
    series = _day_series()
    now = datetime(2026, 10, 27, 12, 7, tzinfo=timezone.utc)
    curve = price_curve_for_day(series, "import", now, LOCAL_TZ)
    assert len(curve) == 97 and curve[0] == {"start": "2026-10-26T23:00:00+00:00", "end": "2026-10-26T23:15:00+00:00", "price": 0.1}
    assert price_curve_for_day(series, "export", now, LOCAL_TZ)[0]["price"] == 0.05


def test_the_day_statistics_are_those_of_the_local_day_only():
    """Intent: average, minimum, maximum import, maximum export and maximum profit cover the 96 quarters of the local day, not the quarter of tomorrow.
    Why: the dashboard tiles say 'today'; tomorrow's first quarter must not move them."""
    from hems.outlook import day_price_stats
    series = _day_series()
    stats = day_price_stats(series, datetime(2026, 10, 27, 12, 7, tzinfo=timezone.utc), LOCAL_TZ)
    assert stats["minimum"] == 0.10 and stats["maximum"] == 0.40 and abs(stats["average"] - 0.25) < 1e-6
    assert stats["max_export"] == 0.35 and abs(stats["max_profit"] - 0.25) < 1e-6
    assert day_price_stats(series, datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc), LOCAL_TZ) is None
