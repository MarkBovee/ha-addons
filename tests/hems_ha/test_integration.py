import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.hems.const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_GRID, CONF_PRICE_CURVE, CONF_PV,
                                          CONF_SOC, DEFAULT_OPTIONS, DOMAIN)
from custom_components.hems.engine.nordpool import NORD_POOL_URL, nordpool_params
from custom_components.hems.engine.weather import OPEN_METEO_URL

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "hems" / "core" / "tests" / "fixtures" / "quarter_import_prices.csv"
NORDPOOL = ROOT / "hems" / "core" / "tests" / "fixtures" / "nordpool_2026-10-06.json"
NOW = datetime(2026, 10, 6, 11, 7, tzinfo=timezone(timedelta(hours=2)))      # a day with a wide spread, local time
EVENING = datetime(2026, 10, 6, 19, 7, tzinfo=timezone(timedelta(hours=2)))  # the evening peak: with enough SoC the plan discharges
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
    assert float(hass.states.get("sensor.hems_pv_forecast_24h").state) > 0
    trace = (Path(hass.config.path("hems", "decision_trace.jsonl"))).read_text().splitlines()
    assert json.loads(trace[-1])["dry_run"] is True and json.loads(trace[-1])["status"] == "ok"


async def test_a_stale_soc_gives_no_decision_and_says_why(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock, caplog):
    """An unavailable SoC gives status no_soc, an unknown battery action, and a log line that says so."""
    set_states(hass)
    hass.states.async_set("sensor.soc", "unavailable")
    with caplog.at_level(logging.INFO, logger="custom_components.hems"):
        await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_status").state == "no_soc"
    assert hass.states.get("sensor.hems_battery_action").state == "unknown"
    lines = [r.getMessage() for r in caplog.records]
    assert "HEMS no_soc: no decision this quarter | executor no_plan" in lines and "HEMS status no_soc: no decision this quarter" in lines
    assert hass.states.get("sensor.hems_executor").state == "no_plan"


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


async def test_entity_ids_do_not_depend_on_the_instance_language(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """On a Dutch instance the ids are still the English, key-based ones (regression: they came out as sensor.hems_batterij_actie)."""
    hass.config.language = "nl"
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    for entity_id in ("sensor.hems_battery_action", "sensor.hems_battery_setpoint", "sensor.hems_status", "sensor.hems_plan",
                      "sensor.hems_pv_forecast_24h", "binary_sensor.hems_tomorrow_prices_available"):
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get("sensor.hems_batterij_actie") is None


async def test_a_missing_soc_after_a_restart_is_retried_within_a_minute(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The battery sensors appear shortly after HA starts; HEMS replans after 60 s instead of waiting for the next quarter."""
    set_states(hass)
    hass.states.async_set("sensor.soc", "unavailable")
    await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_status").state == "no_soc"
    hass.states.async_set("sensor.soc", "40")
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_status").state == "ok"


def read_jsonl(hass: HomeAssistant, name: str) -> list[dict]:
    """The lines of one HEMS log file (decision_trace.jsonl, plans.jsonl, events.jsonl) as dicts."""
    path = Path(hass.config.path("hems", name))
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


async def test_the_decision_record_explains_inputs_comparison_and_plan_shape(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """One cycle leaves a decision line with inputs (and their ages), the comparison, the plan segments and a settings hash."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    record = read_jsonl(hass, "decision_trace.jsonl")[-1]
    assert record["status"] == "ok" and len(record["settings"]) == 8
    assert record["inputs"]["price_quarters"] == 96 and record["inputs"]["market_age_min"] == 0 and record["inputs"]["price_curve_configured"] is True
    assert set(record["compare"]) >= {"code", "sell", "buy", "keep", "at_floor", "at_full", "best_sell_later", "best_buy_later"}
    assert record["segments"] and record["segments"][0]["from"] == record["slot_start"]
    assert record["previous_action"] is None and record["action_changed"] is False


async def test_every_cycle_logs_the_full_plan_as_compact_arrays(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """plans.jsonl holds all planned quarters of the cycle, equal in number to what sensor.hems_plan reports."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    plan = read_jsonl(hass, "plans.jsonl")[-1]
    assert plan["n"] == int(hass.states.get("sensor.hems_plan").state) and plan["start"] == plan["cycle"]
    assert len(plan["a"]) == plan["n"] and all(len(plan[k]) == plan["n"] for k in ("w", "soc", "imp", "exp", "load", "pv", "keep"))


async def test_the_full_plan_log_can_be_switched_off(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """With trace_full_plan off the decision line is still written, plans.jsonl is not."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options={**DEFAULT_OPTIONS, "trace_full_plan": False}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert read_jsonl(hass, "decision_trace.jsonl") and read_jsonl(hass, "plans.jsonl") == []


async def test_events_record_fetches_settings_and_the_first_status_and_action(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """events.jsonl tells how the first cycle came about: settings, history, Nord Pool, weather, PV gain, status, action."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    events = {e["event"]: e for e in read_jsonl(hass, "events.jsonl")}
    assert {"settings", "history", "market", "weather", "pv_gain", "status", "action"} <= set(events)
    assert events["settings"]["values"]["battery"]["min_profit_margin"] == 0.10 and events["settings"]["previous"] is None
    assert events["settings"]["roles"]["soc_entity"] == "sensor.soc"
    assert events["market"]["fetched"] == [{"day": "2026-10-06", "http": 200, "quarters": 96}] and events["market"]["known_quarters"] == 96
    assert events["weather"]["ok"] is True and events["status"]["to"] == "ok" and events["status"]["from"] is None


async def test_failed_fetches_and_status_changes_are_logged_with_the_reason(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """A Nord Pool outage and a missing SoC end up in the events, including the retry that follows."""
    set_states(hass)
    hass.states.async_set("sensor.soc", "unavailable")
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock, today_status=500)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.soc", "40")
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    events = read_jsonl(hass, "events.jsonl")
    market = next(e for e in events if e["event"] == "market")
    assert "error" in market["fetched"][0] and market["covers_until"] is None
    assert [(e["from"], e["to"]) for e in events if e["event"] == "status"] == [(None, "no_soc"), ("no_soc", "ok")]
    assert any(e["event"] == "retry" and e["status"] == "no_soc" for e in events)
    last = read_jsonl(hass, "decision_trace.jsonl")[-1]
    assert last["status"] == "ok" and last["inputs"]["price_curve_configured"] is True and last["price_source"] == "curve"



async def test_the_executor_holds_a_discharge_when_the_soc_reaches_the_floor_inside_the_quarter(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock, caplog):
    """The planner still says discharge for the quarter; the executor re-checks every SoC update and holds at the floor, then releases."""
    set_states(hass, soc="60")
    await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    assert hass.states.get("sensor.hems_battery_action").state == "discharge"
    assert hass.states.get("sensor.hems_executor").state == "as_planned" and int(hass.states.get("sensor.hems_battery_setpoint").state) < -1000
    with caplog.at_level(logging.WARNING, logger="custom_components.hems"):
        hass.states.async_set("sensor.soc", "30")
        await hass.async_block_till_done()
    executor = hass.states.get("sensor.hems_executor")
    assert executor.state == "at_floor" and hass.states.get("sensor.hems_battery_setpoint").state == "0"
    assert hass.states.get("sensor.hems_battery_action").state == "discharge"                  # the plan is the planner's, the setpoint the executor's
    assert executor.attributes["planned_w"] < -1000 and executor.attributes["overridden"] is True and "floor 30%" in executor.attributes["reason"]
    assert any("executor overrides the plan" in r.getMessage() for r in caplog.records)
    assert [(e["from"], e["to"]) for e in read_jsonl(hass, "events.jsonl") if e["event"] == "executor"] == [(None, "as_planned"), ("as_planned", "at_floor")]
    hass.states.async_set("sensor.soc", "61")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_executor").state == "as_planned" and int(hass.states.get("sensor.hems_battery_setpoint").state) < -1000


def line_starting(lines: list[str], prefix: str) -> str:
    """The first log line that starts with `prefix`; the failure message lists the HEMS lines that did exist."""
    found = [line for line in lines if line.startswith(prefix)]
    assert found, f"no log line starts with {prefix!r}; HEMS lines: {[line[:120] for line in lines if line.startswith('HEMS')]}"
    return found[0]


async def test_the_cycle_decision_and_the_plan_are_visible_in_the_home_assistant_log(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock, caplog):
    """INFO lines carry the decision with its comparison, the plan's charge and discharge windows, and every event."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")             # the log shows local time, like the home it describes
    set_states(hass, soc="60")
    with caplog.at_level(logging.INFO, logger="custom_components.hems"):
        await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    lines = [r.getMessage() for r in caplog.records if r.name.startswith("custom_components.hems")]
    cycle = line_starting(lines, "HEMS 19:00 ok: discharge")
    assert "sell " in cycle and "keep " in cycle and "buy " in cycle and "prices market" in cycle and "executor" not in cycle
    tree = line_starting(lines, "HEMS plan from 19:00")
    assert " discharge " in tree
    assert any(line.startswith("HEMS event market ") and "known_quarters" in line for line in lines)
    assert any(line.startswith("HEMS event settings hash=") for line in lines) and any(line.startswith("HEMS event executor ") for line in lines)


async def test_the_integration_makes_its_info_lines_visible_but_leaves_a_configured_level_alone(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """`logger: default: warning` would hide the decision log, so setup sets INFO unless the user already chose a level for it."""
    package = logging.getLogger("custom_components.hems")
    assert package.level == logging.NOTSET
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    assert package.level == logging.INFO
    await hass.config_entries.async_unload(entry.entry_id)
    package.setLevel(logging.DEBUG)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert package.level == logging.DEBUG
