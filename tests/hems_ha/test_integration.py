import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.hems.config_flow import SECTIONS
from custom_components.hems.config_flow import ROLE_SELECTORS
from custom_components.hems.const import (CONF_EV_CHARGING, CONF_EV_CURRENTS, CONF_EV_PLUGGED, CONF_EV_SOC, CONF_METER_CURRENTS, CONF_METER_EXPORTS, CONF_EV, CONF_INVERTER, CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_GRID, CONF_PRICE_CURVE, CONF_PV,
                                          CONF_SOC, DEFAULT_OPTIONS, DOMAIN)
from custom_components.hems.engine.nordpool import NORD_POOL_URL, nordpool_params
from custom_components.hems.engine.weather import OPEN_METEO_URL
from custom_components.hems.websocket import ws_settings, ws_subscribe

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


async def setup_entry(hass: HomeAssistant, freezer, aioclient_mock, roles=None, now=NOW, nordpool=True, options=None) -> MockConfigEntry:
    """Set up the integration at a frozen time with weather and (optionally) Nord Pool mocked."""
    freezer.move_to(now)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    if nordpool:
        mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=roles or ROLES, options={**DEFAULT_OPTIONS, **(options or {})}, unique_id=DOMAIN)
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


async def test_reconfigure_changes_only_the_optional_roles_and_can_clear_one(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The reconfigure step swaps the EV role, rejects an unknown entity, keeps the required roles, and clearing a field removes the role."""
    set_states(hass)
    hass.states.async_set("sensor.ev_old", "0")
    hass.states.async_set("sensor.ev_new", "0")
    entry = await setup_entry(hass, freezer, aioclient_mock, roles={**ROLES, CONF_EV: "sensor.ev_old"})
    form = await entry.start_reconfigure_flow(hass)
    assert form["type"] == FlowResultType.FORM and form["step_id"] == "reconfigure"
    assert set(form["data_schema"].schema) == set(ROLE_SELECTORS) and {CONF_INVERTER, CONF_EV, CONF_PRICE_CURVE} <= set(ROLE_SELECTORS)
    bad = await hass.config_entries.flow.async_configure(form["flow_id"], {CONF_EV: "sensor.nope", CONF_PRICE_CURVE: "sensor.import_price"})
    assert bad["type"] == FlowResultType.FORM and bad["errors"] == {"base": "entity_not_found"}
    done = await hass.config_entries.flow.async_configure(form["flow_id"], {CONF_EV: "sensor.ev_new", CONF_PRICE_CURVE: "sensor.import_price"})
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "reconfigure_successful"
    assert entry.data[CONF_EV] == "sensor.ev_new" and entry.data[CONF_SOC] == "sensor.soc" and entry.data[CONF_PRICE_CURVE] == "sensor.import_price"
    again = await entry.start_reconfigure_flow(hass)
    await hass.config_entries.flow.async_configure(again["flow_id"], {CONF_PRICE_CURVE: "sensor.import_price"})
    assert CONF_EV not in entry.data and entry.data[CONF_GRID] == "sensor.grid_power"


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
    plan = hass.states.get("sensor.hems_plan")
    assert plan.state[:6] in ("Charge", "Discha") and "–" in plan.state and plan.attributes["slots"] and plan.attributes["windows"]
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
    """plans.jsonl holds all planned quarters of the cycle, equal in number to what sensor.hems_plan reports as `quarters`."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    plan = read_jsonl(hass, "plans.jsonl")[-1]
    assert plan["n"] == hass.states.get("sensor.hems_plan").attributes["quarters"] and plan["start"] == plan["cycle"]
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


async def test_the_plan_sensor_says_in_words_what_happens_when(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The state is read by a person: windows in local time, in English even on a Dutch instance; the quarter count is an attribute."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    hass.config.language = "nl"
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    plan = hass.states.get("sensor.hems_plan")
    assert plan.state.startswith(("Charge ", "Discharge ")) and plan.state.count("–") >= 1 and len(plan.state) <= 255
    window = plan.attributes["windows"][0]
    assert window["from"].endswith(("+01:00", "+02:00")) and window["action"] in ("charge", "discharge") and plan.attributes["quarters"] > 48
    table = plan.attributes["markdown"].splitlines()
    assert table[0] == "|Time|Type|Power|Price|SoC|Purpose|" and table[2].startswith("|🔴 ") and len(table) >= 4
    first_slot = plan.attributes["slots"][0]
    assert set(first_slot) == {"start", "action", "power_w", "soc_kwh", "reason"} and first_slot["start"].endswith(("+01:00", "+02:00"))


async def test_the_plan_sensor_has_no_state_without_a_decision(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """No SoC means no plan: the state is unknown, not a misleading '0'."""
    set_states(hass)
    hass.states.async_remove("sensor.soc")
    await setup_entry(hass, freezer, aioclient_mock)
    plan = hass.states.get("sensor.hems_plan")
    assert plan.state == "unknown" and plan.attributes["status"] != "ok"


async def test_saving_the_settings_form_reloads_hems_and_the_planner_uses_the_new_values(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The Configure button: the form lists the settings, saving stores them, reloads the entry and logs the new settings hash."""
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    first = [e for e in read_jsonl(hass, "events.jsonl") if e["event"] == "settings"][-1]
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] == FlowResultType.FORM and list(map(str, form["data_schema"].schema)) == ["module_battery", "module_water_heater", "module_ev", "base_prices", "base_forecast", "base_grid", "logging"]
    saved = await hass.config_entries.options.async_configure(form["flow_id"], {"module_battery": {"reserve_soc_pct": 40.0, "hold_cost_kwh_h": 0.01}})
    await hass.async_block_till_done()
    assert saved["type"] == FlowResultType.CREATE_ENTRY and entry.options["reserve_soc_pct"] == 40.0 and entry.options["hold_cost_kwh_h"] == 0.01
    assert entry.state.value == "loaded" and hass.states.get("sensor.hems_status").state == "ok"
    latest = [e for e in read_jsonl(hass, "events.jsonl") if e["event"] == "settings"][-1]
    assert latest["hash"] != first["hash"] and latest["values"]["battery"]["reserve_soc"] == 0.4 and latest["values"]["battery"]["hold_cost_kwh_h"] == 0.01


async def test_the_core_values_are_entities_with_series_for_a_chart(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Prices, PV, house load, irradiance, temperature and the first charge and discharge window are visible without reading the logs."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    pv = hass.states.get("sensor.hems_pv_forecast_next_hour")
    assert float(pv.state) >= 0 and pv.attributes["unit_of_measurement"] == "kWh" and len(pv.attributes["forecast"]) > 4
    assert float(pv.state) == pytest.approx(sum(p["kwh"] for p in pv.attributes["forecast"][:4]), abs=0.005)
    assert float(hass.states.get("sensor.hems_load_forecast_next_hour").state) > 0
    sun, temperature = hass.states.get("sensor.hems_irradiance_forecast"), hass.states.get("sensor.hems_temperature_forecast")
    assert float(sun.state) == 300.0 and sun.attributes["unit_of_measurement"] == "W/m²" and sun.attributes["forecast"][0] == {"start": "2026-10-06T11:00:00+02:00", "w_m2": 300.0}
    assert float(temperature.state) == 12.0 and temperature.attributes["unit_of_measurement"] == "°C" and temperature.attributes["forecast"][0]["celsius"] == 12.0
    for entity in ("sensor.hems_import_price", "sensor.hems_export_price"):
        curve = hass.states.get(entity).attributes["curve"]
        assert len(curve) > 48 and curve[0]["start"] == "2026-10-06T11:00:00+02:00" and curve[0]["price"] == pytest.approx(float(hass.states.get(entity).state), abs=1e-9)
    charge, discharge = hass.states.get("sensor.hems_charge_window"), hass.states.get("sensor.hems_discharge_window")
    assert charge.state not in ("unknown", "unavailable") and datetime.fromisoformat(charge.attributes["end"]) > datetime.fromisoformat(charge.state)
    assert charge.attributes["kwh"] > 0 and charge.attributes["pv_kwh"] >= 0 and charge.attributes["load_kwh"] > 0
    assert {"power_w", "avg_price_eur_kwh", "soc_from_pct", "soc_to_pct", "pv_kwh", "load_kwh"} <= set(charge.attributes)
    assert discharge.state not in ("unknown", "unavailable") and discharge.attributes["avg_price_eur_kwh"] > 0


async def test_the_window_sensors_are_unknown_when_the_plan_has_no_such_window(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Without a SoC there is no plan: the windows and forecasts say unknown instead of showing stale values."""
    set_states(hass)
    hass.states.async_remove("sensor.soc")
    await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_charge_window").state == "unknown" and hass.states.get("sensor.hems_pv_forecast_next_hour").state == "unknown"
    assert hass.states.get("sensor.hems_irradiance_forecast").state == "unknown"


async def test_a_reading_knows_when_the_value_changed_apart_from_when_it_was_reported(recorder_mock, hass: HomeAssistant, freezer):
    """A sensor that repeats 95.4 every minute is fresh (reported now) but its information dates from the last change."""
    from custom_components.hems.adapters import reading_from_state
    freezer.move_to(NOW)
    hass.states.async_set("sensor.soc", "95.4")
    freezer.move_to(NOW + timedelta(seconds=70))
    hass.states.async_set("sensor.soc", "95.4")                       # same value: only `last_reported` moves
    reading = reading_from_state(hass.states.get("sensor.soc"))
    assert reading.changed_at == NOW and reading.observed_at == NOW + timedelta(seconds=70) and reading.known_since == NOW
    freezer.move_to(NOW + timedelta(seconds=80))
    hass.states.async_set("sensor.soc", "95.7")
    assert reading_from_state(hass.states.get("sensor.soc")).changed_at == NOW + timedelta(seconds=80)


async def test_every_record_and_the_device_say_which_build_made_them(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock, monkeypatch):
    """A decision, the settings event and the device carry the deployed commit, so a review can tell old code from current code."""
    from homeassistant.helpers import device_registry as dr
    monkeypatch.setattr("custom_components.hems.read_build", lambda: "abc1234")
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    assert read_jsonl(hass, "decision_trace.jsonl")[-1]["build"] == "abc1234"
    assert [e for e in read_jsonl(hass, "events.jsonl") if e["event"] == "settings"][-1]["build"] == "abc1234"
    assert dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0].sw_version == "abc1234"


async def test_a_copy_without_a_stamp_reports_unknown(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock, monkeypatch):
    """Nothing breaks when BUILD is missing (a hand-copied integration): the build is 'unknown'."""
    monkeypatch.setattr("custom_components.hems.BUILD_FILE", "NO_SUCH_STAMP")
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    assert read_jsonl(hass, "decision_trace.jsonl")[-1]["build"] == "unknown"


async def test_the_sell_windows_are_a_sensor_a_trace_field_and_an_event(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Detected windows are visible three ways: the next window as a sensor, every window in the decision record, a `windows` event when they change."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    sensor = hass.states.get("sensor.hems_sell_window")
    windows = sensor.attributes["windows"]
    assert windows and sensor.state not in ("unknown", "unavailable") and sensor.attributes["status"] == windows[0]["status"]
    assert windows[0]["from"].endswith("+02:00") and {"peak", "viable", "need_fresh", "room_fresh", "need_replace", "room_replace", "sold_kwh", "charges"} <= set(windows[0])
    record = read_jsonl(hass, "decision_trace.jsonl")[-1]
    assert [w["status"] for w in record["windows"]] == [w["status"] for w in windows] and "windows_outside_kwh" in record
    event = [e for e in read_jsonl(hass, "events.jsonl") if e["event"] == "windows"][-1]
    assert [w["from"] for w in event["windows"]] == [w["from"] for w in record["windows"]] and event["outside_kwh"] == record["windows_outside_kwh"]
    table = hass.states.get("sensor.hems_plan").attributes["markdown"].splitlines()
    assert table[0].endswith("|Doel|") or table[0].endswith("|Purpose|")


async def test_an_unsold_window_is_warned_once_and_only_again_when_the_picture_changes(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock, caplog):
    """A window that pays, has energy and is not sold is what a reviewer would hunt for: one warning per change, not one per quarter."""
    from types import SimpleNamespace
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    coordinator = entry.runtime_data
    window = {"from": "2026-10-06T06:00:00+00:00", "to": "2026-10-06T08:00:00+00:00", "peak": 0.55, "viable": "fresh", "status": "unsold", "sold_kwh": 0.0, "from_stock_kwh": 0.0}
    caplog.clear()
    await coordinator._note_windows(SimpleNamespace(trace={"windows": [window], "windows_outside_kwh": 0.0}))
    await coordinator._note_windows(SimpleNamespace(trace={"windows": [window], "windows_outside_kwh": 0.0}))
    assert sum("HEMS window check" in r.getMessage() for r in caplog.records) == 1
    await coordinator._note_windows(SimpleNamespace(trace={"windows": [{**window, "status": "planned", "sold_kwh": 3.0}], "windows_outside_kwh": 0.0}))
    assert sum("HEMS window check" in r.getMessage() for r in caplog.records) == 1                      # now fine: no new warning
    assert [e["windows"][0]["status"] for e in read_jsonl(hass, "events.jsonl") if e["event"] == "windows"][-2:] == ["unsold", "planned"]


def weather_calls(aioclient_mock) -> int:
    """How many times Open-Meteo was asked."""
    return sum(1 for call in aioclient_mock.mock_calls if OPEN_METEO_URL in str(call[1]))


async def test_a_weather_outage_right_after_a_restart_is_retried_after_a_minute_and_only_once(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """16 Oct 08:38 and 15 Oct 09:37: Open-Meteo answered 503 on the first fetch and the plan ran half an hour without a PV forecast.
    Without a copy of the forecast one quick retry follows; if that fails too the normal 30 minutes apply (no fetch every minute)."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, status=503)
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert read_jsonl(hass, "decision_trace.jsonl")[-1]["weather"] is False and weather_calls(aioclient_mock) == 1
    assert any(e["event"] == "retry" and e["status"] == "weather" for e in read_jsonl(hass, "events.jsonl"))
    for _ in range(3):                                                  # the outage goes on: no further fetch for the next minutes
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert weather_calls(aioclient_mock) == 2
    aioclient_mock.clear_requests()                                     # Open-Meteo is back; the regular 30 minutes pass
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock)
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert [e["ok"] for e in read_jsonl(hass, "events.jsonl") if e["event"] == "weather"][-1] is True


async def test_the_quick_weather_retry_gets_the_forecast_back_within_two_minutes(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """When the second fetch works the next planning cycle already has the weather."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, status=503)
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert read_jsonl(hass, "decision_trace.jsonl")[-1]["weather"] is True and float(hass.states.get("sensor.hems_pv_forecast_next_hour").state) >= 0


async def test_a_second_outage_that_costs_the_forecast_again_gets_its_own_quick_retry(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The quick retry is once per outage, not once per run: after the forecast was back and then went stale (6 hours without a fetch) it is available again."""
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, status=503)
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock)
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert read_jsonl(hass, "decision_trace.jsonl")[-1]["weather"] is True
    aioclient_mock.clear_requests()
    aioclient_mock.get(OPEN_METEO_URL, status=503)
    mock_nordpool(aioclient_mock)
    for _ in range(16):                                                  # eight hours of a 503 every half hour: the copy goes stale after six
        freezer.tick(timedelta(minutes=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert sum(e["event"] == "retry" and e["status"] == "weather" for e in read_jsonl(hass, "events.jsonl")) == 2


async def test_the_pv_forecast_is_clipped_at_the_panels_peak_not_at_the_inverter(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Full sun (1000 W/m2) would give 7 kW at the default gain; this installation peaks at 5 kW, so the next hour is 5 kWh, not 7 or 8."""
    set_states(hass)
    freezer.move_to(NOW)
    payload = weather_payload()
    payload["minutely_15"]["shortwave_radiation"] = [1000.0] * 60
    aioclient_mock.get(OPEN_METEO_URL, json=payload)
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.hems_pv_forecast_next_hour").state) == pytest.approx(5.0, abs=0.01)
    assert DEFAULT_OPTIONS["pv_max_ac_w"] == 5000.0


def forecast_by_start(hass: HomeAssistant) -> dict[str, float]:
    """The load forecast sensor's quarters by local start time."""
    return {point["start"]: point["kwh"] for point in hass.states.get("sensor.hems_load_forecast_next_hour").attributes["forecast"]}


async def test_the_water_heater_module_plans_the_cheapest_hour_and_puts_it_in_the_load_forecast(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Module on: the cheapest hour of 6 Oct (13:00-14:00) is the run, the sensor says so in local time, those four quarters carry the run's 1.9 kWh on top of the
    flat 0.1 kWh, the others do not, and the trace counts the run."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")             # the module plans local days; the test default is US/Pacific
    set_states(hass)
    freezer.move_to(NOW)
    aioclient_mock.get(OPEN_METEO_URL, json=weather_payload())
    mock_nordpool(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=ROLES, options={**DEFAULT_OPTIONS, "water_heater_enabled": True}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    plan = hass.states.get("sensor.hems_water_heater_plan")
    assert plan.state == "2026-10-06T11:00:00+00:00"
    assert [(w["kind"], w["start"], w["end"], w["energy_kwh"]) for w in plan.attributes["windows"]] == [("heating", "2026-10-06T13:00+02:00", "2026-10-06T14:00+02:00", 1.9)]
    quarters = forecast_by_start(hass)
    inside = {k: v for k, v in quarters.items() if k[11:13] == "13" and k.startswith("2026-10-06")}
    assert len(inside) == 4 and all(v == pytest.approx(0.1 + 1.9 / 4, abs=0.002) for v in inside.values())
    assert all(v == pytest.approx(0.1, abs=0.002) for k, v in quarters.items() if k not in inside)
    record = read_jsonl(hass, "decision_trace.jsonl")[-1]
    assert record["inputs"]["heating_runs"] == 1 and record["load_source"] == "default"


async def test_the_water_heater_module_is_off_by_default_and_changes_nothing(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Off: no state on the plan sensor, a flat forecast, no run in the trace."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    plan = hass.states.get("sensor.hems_water_heater_plan")
    assert plan.state == "unknown" and plan.attributes["windows"] == []
    assert all(v == pytest.approx(0.1, abs=0.002) for v in forecast_by_start(hass).values())
    assert read_jsonl(hass, "decision_trace.jsonl")[-1]["inputs"]["heating_runs"] == 0


async def test_the_options_form_switches_the_water_heater_module_on_and_the_plan_follows(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The settings form shows the module's fields (the weekday as a choice), saving reloads the entry and the plan appears; a legionella weekday of today
    (Tuesday 6 Oct) makes today's run the three-hour, 2.6 kWh one."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    saved = await hass.config_entries.options.async_configure(form["flow_id"], {"module_water_heater": {"water_heater_enabled": True, "water_heater_legionella_weekday": "tuesday"}})
    await hass.async_block_till_done()
    assert saved["type"] == FlowResultType.CREATE_ENTRY and entry.options["water_heater_enabled"] is True
    window, = hass.states.get("sensor.hems_water_heater_plan").attributes["windows"]
    assert (window["kind"], window["energy_kwh"]) == ("legionella", 2.6)
    assert datetime.fromisoformat(window["end"]) - datetime.fromisoformat(window["start"]) == timedelta(hours=3)


async def test_the_settings_form_is_split_into_parts_that_cover_every_option_and_are_translated(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Five parts, the battery open and the rest folded; every option appears in exactly one part and has a label in both languages; saving one part keeps the others as they were."""
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    collapsed = {str(name): part.options["collapsed"] for name, part in form["data_schema"].schema.items()}
    assert collapsed == {"module_battery": False, "module_water_heater": True, "module_ev": True, "base_prices": True, "base_forecast": True, "base_grid": True, "logging": True}
    assert list(collapsed) == list(SECTIONS), "modules first, then the base components they share"
    keys = [key for keys in SECTIONS.values() for key in keys]
    assert sorted(keys) == sorted(set(keys)) and set(keys) == set(DEFAULT_OPTIONS), "every editable option is in exactly one part"
    for language in ("strings", "translations/en"):
        texts = json.loads((ROOT / "custom_components" / "hems" / f"{language}.json").read_text())["options"]["step"]["init"]["sections"]
        assert {name: set(part["data"]) for name, part in texts.items()} == {name: set(keys) for name, keys in SECTIONS.items()}
    before = dict(entry.options)
    await hass.config_entries.options.async_configure(form["flow_id"], {"module_water_heater": {"water_heater_hours": 2}})
    await hass.async_block_till_done()
    assert entry.options["water_heater_hours"] == 2 and {k: v for k, v in entry.options.items() if k != "water_heater_hours"} == {k: v for k, v in before.items() if k != "water_heater_hours"}


async def test_the_settings_form_shows_the_current_values_inside_every_section(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The screen fills a field from its suggested value: every field of every section carries the current option, a changed option included, and
    no section has a default of its own (that made the screen start every section empty)."""
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    first = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(first["flow_id"], {"module_battery": {"reserve_soc_pct": 40.0}})
    await hass.async_block_till_done()
    form = await hass.config_entries.options.async_init(entry.entry_id)
    shown = {}
    for marker, part in form["data_schema"].schema.items():
        assert marker.default is vol.UNDEFINED, "a section default empties the section on screen"
        shown.update({str(key): (key.description or {}).get("suggested_value", "missing") for key in part.schema.schema})
    assert set(shown) == set(DEFAULT_OPTIONS) and "missing" not in shown.values()
    assert shown["reserve_soc_pct"] == 40.0 and shown["capacity_kwh"] == DEFAULT_OPTIONS["capacity_kwh"]


async def test_a_charge_window_the_plan_does_not_have_shows_the_cheapest_price_block_and_says_so(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """A full battery gets no charge in the plan; the charge window sensor then shows the cheapest three-hour block of import prices (not 'unknown')
    with `planned` False, so nobody reads it as an instruction."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    set_states(hass, soc="100")
    await setup_entry(hass, freezer, aioclient_mock)
    charge = hass.states.get("sensor.hems_charge_window")
    curve = hass.states.get("sensor.hems_import_price").attributes["curve"]
    start = datetime.fromisoformat(charge.state)
    block = [p["price"] for p in curve if start <= datetime.fromisoformat(p["start"]) < start + timedelta(hours=3)]
    assert charge.attributes["planned"] is False and len(block) == 12
    assert charge.attributes["avg_price_eur_kwh"] == pytest.approx(sum(block) / 12, abs=0.0001)
    assert all(sum(block) <= sum(p["price"] for p in curve[i:i + 12]) + 1e-9 for i in range(len(curve) - 11)), "no cheaper three-hour block exists"
    assert datetime.fromisoformat(charge.attributes["end"]) - start == timedelta(hours=3)


async def test_a_charge_the_plan_makes_is_marked_planned(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """With room in the battery the plan charges and the charge window is the plan's: `planned` True."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_charge_window").attributes["planned"] is True


async def test_the_sell_window_follows_a_sale_of_stock_and_the_saving_sensor_is_named_revenue(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """A full battery sells stock; the sale is inside a window (no kWh outside), the sell window sensor has a start, and the sensor that holds the gross
    revenue of the planned sale is called revenue, not saving."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    set_states(hass, soc="95")
    await setup_entry(hass, freezer, aioclient_mock)
    sell = hass.states.get("sensor.hems_sell_window")
    assert sell.state not in ("unknown", "unavailable") and sell.attributes["outside_kwh"] < 2      # without holds the sale starts a quarter before the detected window
    assert "revenue" in hass.states.get("sensor.hems_expected_saving").attributes["friendly_name"].lower()


def test_the_integration_is_english_only():
    """Mark wants every HEMS text in English whatever the language of Home Assistant: there is no other translation file, and en matches strings."""
    folder = ROOT / "custom_components" / "hems" / "translations"
    assert sorted(p.name for p in folder.iterdir()) == ["en.json"]
    names = {file: {(domain, key): ent["name"] for domain, group in json.loads((ROOT / "custom_components" / "hems" / f"{file}.json").read_text())["entity"].items()
                    for key, ent in group.items()} for file in ("strings", "translations/en")}
    assert names["translations/en"] == names["strings"]
    assert len(names["strings"]) == 44 and names["strings"][("sensor", "charge_window")] == "Charge window"


EV_ROLES = {**ROLES, CONF_EV_PLUGGED: "binary_sensor.car_plugged", CONF_EV_CHARGING: "binary_sensor.car_charging", CONF_EV_SOC: "sensor.car_soc",
            **dict(zip(CONF_METER_CURRENTS, ("sensor.meter_l1", "sensor.meter_l2", "sensor.meter_l3"))),
            **dict(zip(CONF_METER_EXPORTS, ("sensor.export_l1", "sensor.export_l2", "sensor.export_l3"))),
            **dict(zip(CONF_EV_CURRENTS, ("sensor.charger_l1", "sensor.charger_l2", "sensor.charger_l3")))}


def set_car(hass: HomeAssistant, plugged: str = "on", soc: str = "40", meter=("10", "12", "8")) -> None:
    """The car, its socket and the three meter phases of EV_ROLES; the house is idle on the export and charger sensors."""
    hass.states.async_set("binary_sensor.car_plugged", plugged)
    hass.states.async_set("binary_sensor.car_charging", "off")
    hass.states.async_set("sensor.car_soc", soc)
    for phase, amps in enumerate(meter, start=1):
        hass.states.async_set(f"sensor.meter_l{phase}", amps)
        hass.states.async_set(f"sensor.export_l{phase}", "0")
        hass.states.async_set(f"sensor.charger_l{phase}", "0")


async def test_the_ev_module_plans_in_dry_run_and_the_override_forces_the_charge(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Intent: with the module on and a car plugged in the EV sensors show a plan, a setpoint limited by the busiest phase and a status; the force
    switch turns the plan into a forced one and nothing is ever written to a device.
    Why: this is the whole dry-run surface of the module, seen the way a dashboard sees it."""
    set_states(hass)
    set_car(hass)
    await setup_entry(hass, freezer, aioclient_mock, roles=EV_ROLES, options={"ev_enabled": True, "ev_max_price": 0.60})
    assert hass.states.get("sensor.hems_ev_status").state == "planned"
    plan = hass.states.get("sensor.hems_ev_plan")
    assert plan.state not in ("unknown", "unavailable") and plan.attributes["quarters"] and plan.attributes["quarters"][0]["current_a"] >= 6
    setpoint = hass.states.get("sensor.hems_ev_setpoint")
    assert setpoint.attributes["allowed_a"] == 12.0 and float(setpoint.state) <= 12.0
    assert hass.states.get("switch.hems_ev_force_charge").state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hems_ev_force_charge"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("switch.hems_ev_force_charge").state == "on" and hass.states.get("sensor.hems_ev_status").state == "forced"
    set_car(hass, plugged="off")
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.hems_ev_force_charge"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.hems_ev_status").state == "not_plugged"


async def test_the_ev_module_off_leaves_the_sensors_empty(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Intent: with the module off the EV sensors have no state and the plan of the battery is the one it was.
    Why: a module that is switched off must cost nothing and change nothing."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    assert hass.states.get("sensor.hems_ev_status").state in ("unknown", "unavailable")
    assert hass.states.get("sensor.hems_status").state == "ok"


async def test_the_netting_date_can_be_cleared_in_the_settings_form(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Intent: submitting an empty netting date stores an empty date, so only the switch decides again.
    Why: the form fills a field that is left out with its old value; an owner who clears the date must really get it cleared."""
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock)
    assert entry.options["salderen_until"] == "2027-01-01"
    form = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(form["flow_id"], {"base_prices": {"salderen_until": ""}})
    await hass.async_block_till_done()
    assert entry.options["salderen_until"] == ""


async def test_the_price_sensors_serve_the_energy_prices_consumers(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Intent: hems_import_price carries `price_curve` for the whole local day in UTC with start, end and price, and the four day statistics are filled.
    Why: the water heater add-on, a chart and a template read exactly this shape from the energy-prices sensor; moving them needs no change in them."""
    set_states(hass)
    await setup_entry(hass, freezer, aioclient_mock)
    curve = hass.states.get("sensor.hems_import_price").attributes["price_curve"]
    assert {"start", "end", "price"} == set(curve[0]) and datetime.fromisoformat(curve[0]["start"]).tzinfo is not None
    assert datetime.fromisoformat(curve[0]["start"]) < NOW, "quarters that already passed are part of the curve"
    assert datetime.fromisoformat(curve[0]["start"]) < datetime.fromisoformat(curve[1]["start"])
    low, high = float(hass.states.get("sensor.hems_price_min_today").state), float(hass.states.get("sensor.hems_price_max_today").state)
    average, profit = float(hass.states.get("sensor.hems_price_average_today").state), float(hass.states.get("sensor.hems_max_profit_today").state)
    assert low <= average <= high and profit > 0


class FakeConnection:
    """Stands in for a websocket connection: the frozen test clock would expire a real client's access token."""

    def __init__(self) -> None:
        self.messages, self.subscriptions = [], {}

    def send_message(self, message) -> None:
        self.messages.append(message)

    def send_result(self, msg_id, result=None) -> None:
        self.messages.append({"id": msg_id, "type": "result", "success": True, "result": result})

    def send_error(self, msg_id, code, message) -> None:
        self.messages.append({"id": msg_id, "type": "result", "success": False, "error": {"code": code}})

    def events(self) -> list[dict]:
        return [m["event"] for m in self.messages if m.get("type") == "event"]


async def test_the_panel_subscription_sends_the_whole_horizon_now_and_after_every_cycle(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """hems/subscribe answers with one payload per quarter of the known prices, the decision with its comparison, and pushes again on the next cycle."""
    set_states(hass, soc="60")
    await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    conn = FakeConnection()
    ws_subscribe(hass, conn, {"id": 1, "type": "hems/subscribe"})
    assert conn.messages[0]["success"] and 1 in conn.subscriptions
    first = conn.events()[0]
    payload = first["payload"]
    assert first["loaded"] is True and payload["meta"]["status"] == "ok" and payload["meta"]["dry_run"] is True
    assert payload["meta"]["stale_after_s"]["plan"] == 1200 and payload["meta"]["cycle_at"]
    assert payload["decision"]["action"] == "discharge" and payload["decision"]["reason"] and payload["decision"]["compare"]
    rows = payload["quarters"]
    assert rows[0]["t"] == payload["decision"]["slot_start"] and rows[0]["act"] == "discharge" and rows[0]["w"] < 0
    assert all({"imp", "exp", "pv", "load", "soc"} <= row.keys() for row in rows)
    assert payload["battery"]["reserve_kwh"] == pytest.approx(7.5) and payload["diff"]["available"] is False   # the first cycle has nothing to compare with
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    second = conn.events()[-1]["payload"]
    assert second["meta"]["cycle_at"] > payload["meta"]["cycle_at"] and second["diff"]["available"] is True
    assert second["diff"]["previous_soc"]
    conn.subscriptions[1]()                               # unsubscribing stops the pushes
    count = len(conn.events())
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(conn.events()) == count


async def test_the_settings_command_gives_the_options_and_roles_in_force(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The panel shows the settings in words and links to the options dialog by entry id."""
    set_states(hass)
    entry = await setup_entry(hass, freezer, aioclient_mock, options={"reserve_soc_pct": 35.0})
    conn = FakeConnection()
    ws_settings(hass, conn, {"id": 1, "type": "hems/settings"})
    result = conn.messages[0]["result"]
    assert result["entry_id"] == entry.entry_id and result["loaded"] is True
    assert result["options"]["reserve_soc_pct"] == 35.0 and result["roles"][CONF_SOC] == "sensor.soc"


async def test_the_plan_diff_and_last_cycle_sensors_follow_the_cycles(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """The first cycle has no previous plan (unknown); the next one counts changed quarters and names the stretches."""
    set_states(hass, soc="60")
    await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    assert hass.states.get("sensor.hems_plan_diff").state == "unknown"
    first = hass.states.get("sensor.hems_last_cycle").state
    hass.states.async_set("sensor.soc", "95")                 # a different starting point: the plan must shift
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    diff = hass.states.get("sensor.hems_plan_diff")
    assert int(diff.state) >= 0 and isinstance(diff.attributes["changes"], list) and diff.attributes["previous_plan_from"]
    assert hass.states.get("sensor.hems_last_cycle").state > first


async def test_the_panel_payload_follows_the_latest_snapshot_even_without_a_subscriber(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Cycles without an open panel must not leave an old payload behind: a later request gets the latest cycle."""
    set_states(hass, soc="60")
    entry = await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    coordinator = entry.runtime_data
    first = coordinator.dashboard_payload()["meta"]["cycle_at"]
    for _ in range(2):
        freezer.tick(timedelta(minutes=15))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert coordinator.dashboard_payload()["meta"]["cycle_at"] == coordinator.data.cycle_at.isoformat() != first


async def test_the_ledger_measures_the_quarter_and_publishes_the_result(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Live power sampled every 10 s becomes priced energy per quarter; the cost and baseline sensors and the panel payload follow."""
    set_states(hass, soc="60")
    entry = await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    hass.states.async_set("sensor.grid_power", "2000")
    for _ in range(150):                                        # 25 minutes: the first full quarter after the start closes
        freezer.tick(timedelta(seconds=10))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    cost = hass.states.get("sensor.hems_cost_today")
    assert float(cost.state) > 0 and cost.attributes["quarters"] >= 1
    assert hass.states.get("sensor.hems_realised_vs_baseline_today").state not in ("unknown", "unavailable")
    payload = entry.runtime_data.dashboard_payload()
    assert payload["realised"]["quarters"] and payload["realised"]["quarters"][-1]["import_price"] > 0
    assert payload["realised"]["bands"]["pv"]["source"] == "default" and payload["quarters"][0]["pv_hi"] is not None


async def test_advisory_mode_recommends_and_the_owner_applies_or_dismisses(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Dry-run recommends nothing; advisory turns the next window into a recommendation; apply fires an event, dismiss hides it."""
    set_states(hass, soc="60")
    await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    assert hass.states.get("sensor.hems_recommendations").state == "0" and hass.states.get("select.hems_battery_mode").state == "dry_run"
    await hass.services.async_call("select", "select_option", {"entity_id": "select.hems_battery_mode", "option": "advisory"}, blocking=True)
    recs = hass.states.get("sensor.hems_recommendations")
    assert recs.state == "1" and recs.attributes["items"][0]["module"] == "battery" and recs.attributes["items"][0]["payload"]["action"] == "discharge"
    rec_id = recs.attributes["items"][0]["id"]
    events = []
    hass.bus.async_listen("hems_recommendation_applied", events.append)
    result = await hass.services.async_call("hems", "apply_recommendation", {"id": rec_id}, blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert result["recommendation"]["id"] == rec_id and events and events[0].data["action"] == "discharge" and events[0].data["power_w"] > 0
    assert hass.states.get("sensor.hems_recommendations").attributes["items"][0]["status"] == "applied"
    with pytest.raises(Exception):                            # applying twice would fire the event twice
        await hass.services.async_call("hems", "apply_recommendation", {"id": rec_id}, blocking=True, return_response=True)
    assert len(events) == 1
    await hass.services.async_call("hems", "dismiss_recommendation", {"id": rec_id}, blocking=True)
    assert hass.states.get("sensor.hems_recommendations").state == "0"
    with pytest.raises(Exception):
        await hass.services.async_call("hems", "apply_recommendation", {"id": "nope"}, blocking=True, return_response=True)


async def test_the_master_starts_off_disarm_all_resets_and_modes_survive_a_reload(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """Modes are stored; the master switch is never restored; one service puts everything back to dry-run."""
    set_states(hass, soc="60")
    entry = await setup_entry(hass, freezer, aioclient_mock, now=EVENING)
    assert hass.states.get("switch.hems_master_arm").state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hems_master_arm"}, blocking=True)
    await hass.services.async_call("select", "select_option", {"entity_id": "select.hems_ev_mode", "option": "advisory"}, blocking=True)
    assert hass.states.get("switch.hems_master_arm").state == "on"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("select.hems_ev_mode").state == "advisory" and hass.states.get("switch.hems_master_arm").state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.hems_master_arm"}, blocking=True)
    await hass.services.async_call("hems", "disarm_all", {}, blocking=True)
    assert hass.states.get("select.hems_ev_mode").state == "dry_run" and hass.states.get("switch.hems_master_arm").state == "off"


async def test_alerts_turn_on_for_stale_data_and_an_overdue_legionella_run(recorder_mock, hass: HomeAssistant, freezer, aioclient_mock):
    """A missing SoC raises the data alert; a legionella run older than eight days raises that alert, with the reason."""
    set_states(hass, soc="unavailable")
    hass.states.async_set("sensor.last_legionella", (EVENING - timedelta(days=10)).isoformat())
    await setup_entry(hass, freezer, aioclient_mock, roles={**ROLES, "legionella_last_entity": "sensor.last_legionella"})
    assert hass.states.get("binary_sensor.hems_alert_data").state == "on" and "no_soc" in hass.states.get("binary_sensor.hems_alert_data").attributes["reason"]
    assert hass.states.get("binary_sensor.hems_alert_legionella").state == "on"
    assert hass.states.get("binary_sensor.hems_alert_deadline").state == "off"
