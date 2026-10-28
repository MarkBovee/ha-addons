from datetime import date, datetime, timedelta, timezone

import pytest

from hems.battery import BatteryConfig
from hems.forecast import LOCAL_TZ
from hems.prices import PriceSeries
from hems.rolling import HorizonInputs, plan_next
from hems.terminal import daily_peaks, reference_peak, terminal_value

QUARTER = timedelta(minutes=15)
CFG = BatteryConfig()


def day_series(*days: tuple[date, float, int], base: float = 0.30) -> PriceSeries:
    """Quarter prices for local days: `base` all day with the evening quarters 18:00 to 20:00 (eight of them) at `peak`; `quarters` limits a day to its first quarters."""
    starts, prices = [], []
    for day, peak, quarters in days:
        midnight = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
        for k in range(quarters):
            moment = midnight.astimezone(timezone.utc) + k * QUARTER
            starts.append(moment)
            local = moment.astimezone(LOCAL_TZ)
            prices.append(peak if 18 <= local.hour < 20 else base)
    return PriceSeries(tuple(starts), tuple(prices), tuple(prices))


def test_a_days_peak_is_the_mean_of_its_eight_best_quarters_and_an_incomplete_day_is_left_out():
    """Eight quarters at 0.50 among 0.30 ones give 0.50; a day with a gap (80 quarters) says nothing about its peak."""
    series = day_series((date(2026, 10, 14), 0.50, 96), (date(2026, 10, 15), 0.60, 80))
    assert daily_peaks(series, LOCAL_TZ) == {date(2026, 10, 14): pytest.approx(0.50)}


def test_the_best_quarter_alone_does_not_make_the_peak():
    """One quarter at 0.90 and seven at 0.50: the peak is their mean (0.55), because a sale takes about two hours."""
    series = day_series((date(2026, 10, 14), 0.50, 96))
    prices = list(series.export_eur_kwh)
    prices[next(i for i, p in enumerate(prices) if p == 0.50)] = 0.90
    assert daily_peaks(PriceSeries(series.starts, series.import_eur_kwh, tuple(prices)), LOCAL_TZ)[date(2026, 10, 14)] == pytest.approx(0.55)


def test_the_reference_peak_is_the_median_of_the_last_days_before_today_and_needs_three():
    """Median of up to seven earlier days (today and later days excluded, older days too); fewer than three days is None."""
    peaks = {date(2026, 10, d): p for d, p in ((1, 0.90), (10, 0.40), (11, 0.60), (12, 0.50), (13, 0.55), (14, 0.30), (15, 0.99))}
    assert reference_peak(peaks, date(2026, 10, 14)) == pytest.approx(0.525)       # 10, 11, 12, 13: the median of 0.40, 0.60, 0.50, 0.55
    assert reference_peak({date(2026, 10, 13): 0.5, date(2026, 10, 12): 0.5}, date(2026, 10, 14)) is None


def test_the_terminal_value_is_what_a_typical_peak_pays_net_and_never_below_the_default():
    """eff x (peak - margin - haircut); a low peak cannot take the value under the default of the cheapest refill."""
    eff = CFG.round_trip_eff ** 0.5
    assert terminal_value(0.60, 0.25, CFG) == pytest.approx(eff * (0.60 - CFG.min_profit_margin))
    assert terminal_value(0.60, 0.25, BatteryConfig(future_peak_haircut=0.05)) == pytest.approx(eff * (0.60 - 0.05 - CFG.min_profit_margin))
    assert terminal_value(0.30, 0.25, CFG) == 0.25


def stock_day(history_peak: float | None):
    """A day with 0.45 in the evening, 90 % in the battery: the decision for 17:00 local and the plan's discharge kWh."""
    series = day_series((date(2026, 10, 15), 0.45, 96))
    now = datetime(2026, 10, 15, 17, 0, tzinfo=LOCAL_TZ)
    load = {t: 0.05 for t in series.starts}
    pv = {t: 0.0 for t in series.starts}
    decision = plan_next(HorizonInputs(now, 0.9 * CFG.capacity_kwh, series, load, pv, max_slots=40, history_peak=history_peak), CFG)
    return decision, sum(-s.battery_kwh for s in decision.plan.slots if s.battery_kwh < 0)


def test_stock_is_sold_in_a_modest_peak_by_default_and_kept_when_recent_peaks_were_higher():
    """The end of the horizon decides: with the default value the evening at 0.45 is sold; when the last days peaked at 0.60 the energy is worth more
    kept for them, so nothing is sold in 0.45. This is the scarce daily capacity, priced."""
    default, sold_default = stock_day(None)
    kept, sold_kept = stock_day(0.60)
    assert sold_default > 5 and sold_kept == 0
    assert default.trace["terminal"]["history_peak"] is None and kept.trace["terminal"]["history_peak"] == 0.60
    assert kept.trace["terminal"]["value"] > default.trace["terminal"]["value"] == default.trace["terminal"]["default"]
