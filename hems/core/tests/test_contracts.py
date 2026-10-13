from datetime import datetime, timedelta, timezone

import pytest

from hems.contracts import BatteryCommand, BatteryLimits, MarketPrices, Reading
from hems.derive import derive_house_load
from hems.fakes import FakeBattery, FixedMarketPrices
from hems.forecast import LOCAL_TZ
from hems.prices import PriceModel, build_price_series

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
QUARTER = timedelta(minutes=15)
LIMITS = BatteryLimits(usable_capacity_kwh=25.0, max_charge_w=8000, max_discharge_w=8000)


def battery(soc_pct=50.0, **kw):
    return FakeBattery(LIMITS, NOW, soc_pct, **kw)


def test_reading_freshness():
    r = Reading(1.0, NOW - timedelta(minutes=20))
    assert r.age(NOW) == timedelta(minutes=20)
    assert r.is_fresh(NOW, timedelta(minutes=30)) and not r.is_fresh(NOW, timedelta(minutes=15))


def test_battery_command_rejects_an_empty_window():
    with pytest.raises(ValueError):
        BatteryCommand(NOW, NOW, 1000)


def test_fake_battery_charge_is_clamped_to_the_device_limit_and_loses_energy():
    b = battery(soc_pct=20.0)
    b.apply([BatteryCommand(NOW, NOW + QUARTER, 12000)])          # asks for more than the 8 kW limit
    b.advance(QUARTER)
    assert b.status().power_w.value == pytest.approx(8000)
    assert b.soc_pct == pytest.approx(20.0 + 2.0 * (0.82 ** 0.5) / 25.0 * 100)   # 2 kWh AC in, minus charge loss


def test_fake_battery_stops_discharging_at_the_device_minimum():
    b = battery(soc_pct=5.5)
    b.apply([BatteryCommand(NOW, NOW + QUARTER, -8000)])
    b.advance(QUARTER)
    assert b.soc_pct == pytest.approx(5.0) and abs(b.status().power_w.value) < 8000
    b.apply([BatteryCommand(b.now, b.now + QUARTER, -8000)])
    b.advance(QUARTER)
    assert b.status().power_w.value == 0.0                       # protected: nothing left to give


def test_fake_battery_without_a_matching_command_idles():
    b = battery()
    b.apply([BatteryCommand(NOW + QUARTER, NOW + 2 * QUARTER, 4000)])   # starts in the next quarter only
    b.advance(QUARTER)
    assert b.soc_pct == 50.0 and b.status().power_w.value == 0.0


def test_frozen_battery_sensor_goes_stale_while_the_device_keeps_running():
    b = battery(soc_pct=20.0)
    b.apply([BatteryCommand(NOW, NOW + 2 * QUARTER, 4000)])
    b.advance(QUARTER)
    seen_at = b.status().soc_pct.observed_at
    b.frozen = True
    b.advance(QUARTER)
    assert b.status().soc_pct.observed_at == seen_at
    assert not b.status().soc_pct.is_fresh(b.now, timedelta(minutes=10))


def test_house_load_from_the_energy_balance():
    at = NOW
    # importing 500 W, PV 2000 W, battery charging 1500 W -> the house uses 1000 W
    load = derive_house_load(Reading(500, at), Reading(2000, at), Reading(1500, at))
    assert load.value == 1000
    # same while discharging 3000 W and the EV charging 4000 W: 500 + 0 + 3000 - 4000 -> floor at 0, not negative
    assert derive_house_load(Reading(500, at), Reading(0, at), Reading(-3000, at), Reading(4000, at)).value == 0
    stale = Reading(500, at - timedelta(minutes=5))
    assert derive_house_load(stale, Reading(0, at), Reading(0, at)).observed_at == stale.observed_at


def test_house_load_is_unknown_when_an_input_is_missing():
    assert derive_house_load(Reading(500, NOW), None, Reading(0, NOW)) is None


def test_price_series_drops_the_percentage_bonus_after_sunset():
    # 2026-10-13 in Utrecht: sunset ~18:49 local. Same market price, one quarter at noon and one at 19:00.
    noon = datetime(2026, 10, 13, 12, 0, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    evening = datetime(2026, 10, 13, 19, 0, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    market = MarketPrices((noon, evening), (0.30, 0.30), fetched_at=NOW)
    series = build_price_series(FixedMarketPrices(market).prices(NOW), PriceModel(), 52.0907, 5.1214)
    assert series.import_eur_kwh[0] == series.import_eur_kwh[1]
    assert series.export_eur_kwh[0] - series.export_eur_kwh[1] == pytest.approx(0.30 * 0.10 * 1.21)
    assert market.covers_until() == evening + QUARTER


def test_market_prices_need_one_value_per_slot():
    with pytest.raises(ValueError):
        MarketPrices((NOW,), (0.1, 0.2), fetched_at=NOW)
