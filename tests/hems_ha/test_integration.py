import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hems.const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_GRID, CONF_PRICE_CURVE, CONF_PV,
                                          CONF_SOC, DEFAULT_OPTIONS, DOMAIN)
from custom_components.hems.engine.weather import OPEN_METEO_URL

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "hems" / "core" / "tests" / "fixtures" / "quarter_import_prices.csv"
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


async def setup_entry(hass: HomeAssistant, freezer, aioclient_mock) -> MockConfigEntry:
    """Set up the integration at a frozen time with the weather endpoint mocked."""
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
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
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_status").state == "ok"
    assert hass.states.get("sensor.hems_battery_action").attributes["weather"] is False
