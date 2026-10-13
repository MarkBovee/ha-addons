import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hems.const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_GRID, CONF_PRICE_CURVE, CONF_PV,
                                          CONF_SOC, DEFAULT_OPTIONS, DOMAIN)
from custom_components.hems.engine.nordpool import NORD_POOL_URL, nordpool_params
from custom_components.hems.engine.weather import OPEN_METEO_URL

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "hems" / "core" / "tests" / "fixtures" / "quarter_import_prices.csv"
NORDPOOL = ROOT / "hems" / "core" / "tests" / "fixtures" / "nordpool_2026-10-06.json"
NOW = datetime(2026, 10, 6, 11, 7, tzinfo=timezone(timedelta(hours=2)))      # a day with a wide spread, local time
ROLES = {CONF_SOC: "sensor.soc", CONF_BATTERY_POWER: "sensor.battery_power", CONF_PV: "sensor.pv_power", CONF_GRID: "sensor.grid_power",
         CONF_PRICE_CURVE: "sensor.import_price", CONF_BATTERY_POSITIVE_DISCHARGING: True}


def price_curve():
    """6 Oct 2026 as the price sensor publishes it: [{start, end, price}] with UTC starts."""
    with PRICES.open(newline="") as f:
        rows = [(datetime.fromisoformat(r["quarter_utc"]), float(r["import_price_eur_kwh"])) for r in csv.DictReader(f)]
    day = [(t, p) for t, p in rows if datetime(2026, 10, 5, 22, tzinfo=timezone.utc) <= t < datetime(2026, 10, 6, 22, tzinfo=timezone.utc)]
    return [{"start": t.isoformat(), "end": (t + timedelta(minutes=15)).isoformat(), "price": p} for t, p in day]


def weather_payload():
    """A small Open-Meteo answer: 300 W/m2 around the 6 Oct daylight hours."""
    times = [(datetime(2026, 10, 6, 6, 0) + timedelta(minutes=15 * i)).isoformat(timespec="minutes") for i in range(60)]
    return {"minutely_15": {"time": times, "shortwave_radiation": [300.0] * 60, "temperature_2m": [12.0] * 60}}


def set_states(hass: HomeAssistant, soc: str = "40") -> None:
    """The five source entities of the roles above."""
    hass.states.async_set("sensor.soc", soc)
    hass.states.async_set("sensor.battery_power", "0")
    hass.states.async_set("sensor.pv_power", "500")
    hass.states.async_set("sensor.grid_power", "300")
    hass.states.async_set("sensor.import_price", "0.3", {"price_curve": price_curve()})


def day_payload(days_later: int = 0) -> dict:
    """The recorded real day of 6 Oct, moved `days_later` days ahead so it can stand in for a later delivery day."""
    payload = json.loads(NORDPOOL.read_text())
    for entry in payload["multiAreaEntries"]:
        for key in ("deliveryStart", "deliveryEnd"):
            entry[key] = (datetime.fromisoformat(entry[key].replace("Z", "+00:00")) + timedelta(days=days_later)).isoformat().replace("+00:00", "Z")
    return payload


def mock_nordpool(aioclient_mock, today_status: int = 200, tomorrow_status: int = 204) -> None:
    """Nord Pool answers for 6 Oct (the recorded real day) and 7 Oct; a status other than 200 means an outage or 'not yet'."""
    for day, status, later in ((date(2026, 10, 6), today_status, 0), (date(2026, 10, 7), tomorrow_status, 1)):
        kwargs = {"json": day_payload(later)} if status == 200 else {}
        aioclient_mock.get(NORD_POOL_URL, params=nordpool_params(day), status=status, **kwargs)


def nordpool_calls(aioclient_mock) -> list[str]:
    """The delivery dates that were requested from Nord Pool."""
    return [str(call[1]) for call in aioclient_mock.mock_calls if "nordpoolgroup" in str(call[1])]


async def setup_entry(hass: HomeAssistant, freezer, aioclient_mock, roles=None, now=NOW, nordpool=True) -> MockConfigEntry:
    """Set up the integration at a frozen time with weather and (optionally) Nord Pool mocked."""
    freezer.move_to(now)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    if nordpool:
        mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=roles or ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_creates_an_entry_and_rejects_unknown_entities(recorder_mock, hass: HomeAssistant):
    """The user step rejects a non-existent entity and creates an entry with default options otherwise."""
    set_states(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    bad = await hass.config_entries.flow.async_configure(result["flow_id"], {**ROLES, CONF_SOC: "sensor.nope"})
    assert bad["type"] == FlowResultType.FORM and bad["errors"] == {"base": "entity_not_found"}
    good = await hass.config_entries.flow.async_configure(result["flow_id"], ROLES)
    assert good["type"] == FlowResultType.CREATE_ENTRY and good["options"]["reserve_soc_pct"] == 30.0


async def test_plans_in_dry_run_and_publishes_sensors_with_a_reason(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """A full cycle publishes the plan sensors with a reason and appends a dry-run line to the trace."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_status").state == "ok"
    action = hass.states.get("sensor.hems_battery_action")
    assert action.state in ("charge", "discharge", "idle") and action.attributes["reason"]
    assert action.attributes["weather"] is True and action.attributes["load_source"] == "default"
    assert action.attributes["price_source"] == "market" and action.attributes["price_check_max_diff"] < 0.00015   # Nord Pool agrees with the price sensor
    assert float(hass.states.get("sensor.hems_import_price").state) == pytest.approx(0.3375, abs=0.2)
    assert int(hass.states.get("sensor.hems_plan").state) > 0 and hass.states.get("sensor.hems_plan").attributes["slots"]
    assert float(hass.states.get("sensor.hems_pv_forecast_next_24_h").state) > 0
    trace = (Path(hass.config.path("hems", "decision_trace.jsonl"))).read_text().splitlines()
    assert json.loads(trace[-1])["dry_run"] is True and json.loads(trace[-1])["status"] == "ok"


async def test_a_stale_soc_gives_no_decision_and_says_why(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """An unavailable SoC gives status no_soc and an unknown battery action."""
    set_states(hass)
    hass.states.async_set("sensor.soc", "unavailable")
    await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_status").state == "no_soc"
    assert hass.states.get("sensor.hems_battery_action").state == "unknown"


async def test_weather_outage_is_survivable(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """A failing weather endpoint still yields a plan, flagged as without weather."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, status=500)
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_status").state == "ok"
    assert hass.states.get("sensor.hems_battery_action").attributes["weather"] is False


async def test_a_nord_pool_outage_falls_back_to_the_price_sensor(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """With Nord Pool down the plan continues on the price-curve sensor and says so."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock, today_status=500)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_status").state == "ok"
    assert hass.states.get("sensor.hems_battery_action").attributes["price_source"] == "curve"


async def test_without_any_price_source_the_status_says_no_prices(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """No price sensor configured and Nord Pool unavailable: no decision, status no_prices."""
    set_states(hass)
    roles = {k: v for k, v in ROLES.items() if k != CONF_PRICE_CURVE}
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock, today_status=500)
    entry = MockConfigEntry(domain=DOMAIN, data=roles, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_status").state == "no_prices"


async def test_tomorrow_is_requested_after_the_publication_hour_and_204_is_not_an_error(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """At 14:00 both days are requested; tomorrow answers 204 (not published) and the plan still runs on today's prices."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock, now=datetime(2026, 10, 6, 14, 2, tzinfo=timezone(timedelta(hours=2))))
    assert hass.states.get("sensor.hems_status").state == "ok"
    assert len(nordpool_calls(aioclient_mock)) == 2
    assert hass.states.get("binary_sensor.hems_tomorrow_prices_available").state == "off"


async def test_nord_pool_can_be_switched_off_in_the_options(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """With nordpool_enabled off nothing is requested and the price sensor is the source."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options={**DEFAULT_OPTIONS, "nordpool_enabled": False}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert nordpool_calls(aioclient_mock) == []
    assert hass.states.get("sensor.hems_battery_action").attributes["price_source"] == "curve"


async def test_tomorrow_prices_available_turns_on_once_published(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """After 13:00 with tomorrow published the binary sensor is on and reports the 96 quarters and the price source."""
    set_states(hass)
    freezer.move_to(datetime(2026, 10, 6, 14, 2, tzinfo=timezone(timedelta(hours=2))))
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock, tomorrow_status=200)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.hems_tomorrow_prices_available")
    assert state.state == "on" and state.attributes["tomorrow_intervals"] == 96 and state.attributes["price_source"] == "market"
    assert state.attributes["prices_until"].startswith("2026-10-07T22:00")


async def test_tomorrow_prices_are_off_in_the_morning(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Before publication nothing of tomorrow is known, even though today's prices are."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    state = hass.states.get("binary_sensor.hems_tomorrow_prices_available")
    assert state.state == "off" and state.attributes["tomorrow_intervals"] == 0
