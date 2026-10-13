import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from hems.contracts import MarketPrices
from hems.nordpool import (delivery_dates, fetch_due, merge_days, nordpool_params, parse_day_ahead, tomorrow_quarters, wanted_until)
from hems.forecast import LOCAL_TZ
from hems.prices import PriceModel

FIXTURES = Path(__file__).parent / "fixtures"


def real_day():
    """A real Nord Pool answer for delivery day 2026-10-06 (public data, trimmed)."""
    return json.loads((FIXTURES / "nordpool_2026-10-06.json").read_text())


def at(day, hour, minute=0):
    """A local (Amsterdam) moment."""
    return datetime(2026, 10, day, hour, minute, tzinfo=LOCAL_TZ)


def test_a_real_day_parses_to_96_quarters_in_eur_per_kwh():
    """A real delivery day gives 96 contiguous quarters, converted from EUR/MWh to EUR/kWh."""
    prices = parse_day_ahead(real_day())
    assert len(prices) == 96 and min(prices) == datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)
    assert all(b - a == timedelta(minutes=15) for a, b in zip(sorted(prices), sorted(prices)[1:]))
    assert 0.12 < min(prices.values()) < 0.14 and 0.40 < max(prices.values()) < 0.41


def test_parsed_prices_reproduce_the_recorded_consumer_prices():
    """Market price through the import formula equals what sensor.current_price recorded that day (add-on rounds to 4 decimals)."""
    with (FIXTURES / "quarter_import_prices.csv").open(newline="") as handle:
        recorded = {datetime.fromisoformat(r["quarter_utc"]): float(r["import_price_eur_kwh"]) for r in csv.DictReader(handle)}
    model = PriceModel()
    diffs = [abs(model.import_price(p) - recorded[s]) for s, p in parse_day_ahead(real_day()).items()]
    assert len(diffs) == 96 and max(diffs) < 0.00015


def test_entries_without_a_price_for_the_area_are_skipped_and_a_bad_payload_fails_fast():
    """Entries for another area are skipped; a payload without entries raises instead of yielding nothing."""
    payload = {"multiAreaEntries": [{"deliveryStart": "2026-10-06T10:00:00Z", "entryPerArea": {"DE": 50.0}},
                                    {"deliveryStart": "2026-10-06T10:15:00Z", "entryPerArea": {"NL": 80.0}}]}
    assert parse_day_ahead(payload) == {datetime(2026, 10, 6, 10, 15, tzinfo=timezone.utc): 0.08}
    with pytest.raises(KeyError):
        parse_day_ahead({"error": "nope"})


def test_days_merge_into_one_sorted_series_and_nothing_is_none():
    """Several days become one sorted series; no prices at all gives None."""
    first, second = parse_day_ahead(real_day()), {datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc): 0.2}
    merged = merge_days([second, first], datetime(2026, 10, 6, 12, tzinfo=timezone.utc))
    assert len(merged.starts) == 97 and list(merged.starts) == sorted(merged.starts)
    assert merge_days([{}], datetime(2026, 10, 6, 12, tzinfo=timezone.utc)) is None


def test_request_parameters_name_the_delivery_day_and_area():
    """The request carries the delivery date, the day-ahead market, the area and the currency."""
    assert nordpool_params(date(2026, 10, 7)) == {"date": "2026-10-07", "market": "DayAhead", "deliveryArea": "NL", "currency": "EUR"}


def test_tomorrow_is_wanted_from_the_publication_hour():
    """Tomorrow is requested from 13:00 local, not before."""
    assert delivery_dates(at(6, 12, 59)) == [date(2026, 10, 6)]
    assert delivery_dates(at(6, 13, 0)) == [date(2026, 10, 6), date(2026, 10, 7)]
    assert wanted_until(at(6, 9)) == at(7, 0).astimezone(timezone.utc)
    assert wanted_until(at(6, 14)) == at(8, 0).astimezone(timezone.utc)


def test_a_fetch_is_due_only_when_prices_are_missing_and_not_retried_too_fast():
    """A fetch is due only for missing coverage and at most once per retry interval."""
    today = merge_days([parse_day_ahead(real_day())], at(6, 9))
    assert fetch_due(at(6, 9), None, None)                               # nothing known
    assert not fetch_due(at(6, 9), today, None)                          # today is complete
    assert fetch_due(at(6, 14), today, None)                             # tomorrow should exist by now
    assert not fetch_due(at(6, 14), today, at(6, 13, 55))                # tried 5 minutes ago
    assert fetch_due(at(6, 14), today, at(6, 13, 45))                    # tried 15 minutes ago
    assert isinstance(today, MarketPrices)


def test_tomorrow_counts_only_quarters_of_the_next_delivery_day():
    """The real 6 Oct day is 'tomorrow' on 5 Oct and nothing on 6 Oct; a partial day counts what is there."""
    starts = list(parse_day_ahead(real_day()))
    assert tomorrow_quarters(starts, at(5, 14)) == 96
    assert tomorrow_quarters(starts, at(6, 14)) == 0
    assert tomorrow_quarters(starts[:10], at(5, 14)) == 10
