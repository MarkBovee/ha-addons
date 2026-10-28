"""Coordinator: every quarter gather the inputs, run the dry-run engine, trace the decision, publish.

It never writes to a device. Home Assistant entities are the only interface: states for SoC, power and prices,
recorder statistics for the consumption history, and one HTTP weather source owned by HEMS itself.
"""
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters import base_load_history, parse_price_curve, reading_from_state, statistic_rows, sum_series
from .const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_EV, CONF_EV_CHARGING, CONF_EV_CURRENTS, CONF_EV_LIMIT, CONF_EV_PLUGGED,
                    CONF_EV_PROBLEM, CONF_EV_SOC, CONF_GRID, CONF_INVERTER, CONF_METER_CURRENTS, CONF_METER_EXPORTS, CONF_PRICE_CURVE,
                    CONF_PV, CONF_PV_EXTRA, CONF_SOC, DEFAULT_OPTIONS, DOMAIN, EVENTS_FILE, EXECUTION_NOTICE_W, HISTORY_DAYS, HISTORY_REFRESH,
                    PLANS_FILE, RETRY_DELAY, CONF_COMPARE_ACTION, CONF_LEGIONELLA_LAST, LEGIONELLA_OVERDUE, STORE_VERSION, RETRY_STATUSES, TRACE_DIR, TRACE_FILE, WEATHER_MAX_AGE, WEATHER_REFRESH)
from .engine.battery import BatteryConfig
from .engine.contracts import MarketPrices
from .engine.decision_log import cycle_line, event_line, plan_summary, plan_table, plan_tree, plan_windows, plan_words, settings_snapshot, window_tree
from .engine.nordpool import NORD_POOL_HEADERS, NORD_POOL_URL, delivery_dates, fetch_due, merge_days, nordpool_params, parse_day_ahead, tomorrow_quarters
from .engine.dryrun import EngineInputs, EngineOutput, EngineSettings, step
from .engine.balancer import phase_room_a
from .engine.executor import AS_PLANNED, Execution, execute
from .engine.ev import EvConfig, EvSetpoint, EvState, STATUS_FORCED, setpoint as ev_setpoint
from .engine.heater import WaterHeaterConfig
from .engine.pvforecast import fit_gain_from_history
from .engine.prices import PriceModel
from .engine.rolling import Decision
from .engine.trace import TraceWriter
from .engine.windows import UNSOLD
from .dashboard import build_payload
from .advice import EVENT_APPLIED, MODE_AUTO, MODES, MODULES, Control
from .realised import Ledger, PlannedQuarter, QuarterPrice, quarter_start
from .saj import SajAdvice, advise, async_apply, read_inputs
from .engine.saj_protocol import entity_names, plan_writes
from .const import SAJ_PREFIX, WRITE_UNLOCKED
from .engine.weather import OPEN_METEO_URL, Weather, open_meteo_params, parse_open_meteo

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HemsSnapshot:
    """What the sensors show after one cycle."""
    output: EngineOutput
    pv_gain_w_per_wm2: float
    history_hours: int
    weather_age_min: float | None
    tomorrow_quarters: int                 # quarters of tomorrow's delivery day that are known (0 = not published)
    prices_until: datetime | None          # end of the last known price quarter
    execution: Execution                   # what the executor would send now, after checking the live SoC
    plan_text: str = ""                    # the charge and discharge windows as one readable line, in the language of Home Assistant
    plan_windows: tuple[dict, ...] = ()    # the same windows with local times, for the plan sensor's attributes
    plan_table: str = ""                   # the plan as a Markdown table for a dashboard card
    weather: Weather | None = None         # the irradiance and temperature forecast the PV forecast was computed from
    ev_setpoint: EvSetpoint | None = None  # what the EV module would ask of the charger now (None when the module is off)
    ev_allowed_a: float | None = None      # what the live per-phase meter leaves for the car (None = no per-phase data)
    cycle_at: datetime | None = None       # when this cycle ran (UTC)
    previous_decision: Decision | None = None   # the plan of the cycle before, for the dashboard's plan diff
    saj: SajAdvice | None = None           # the SAJ slots HEMS would write now and how they differ from the inverter (advisory)


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def water_heater_from_options(o: dict[str, Any]) -> WaterHeaterConfig:
    """The water heater module's settings from the (default-filled) options; an unknown weekday falls back to the default one."""
    weekday = o["water_heater_legionella_weekday"]
    return WaterHeaterConfig(enabled=bool(o["water_heater_enabled"]), energy_kwh=float(o["water_heater_energy_kwh"]), hours=int(o["water_heater_hours"]), night_energy_kwh=float(o["water_heater_night_energy_kwh"]),
                             legionella_energy_kwh=float(o["water_heater_legionella_energy_kwh"]), legionella_hours=int(o["water_heater_legionella_hours"]),
                             legionella_weekday=WEEKDAYS.index(weekday) if weekday in WEEKDAYS else WEEKDAYS.index(DEFAULT_OPTIONS["water_heater_legionella_weekday"]))


def netting_end_from_options(o: dict[str, Any]) -> date | None:
    """The first day without netting: empty means only the `salderen` switch decides; an unreadable date falls back to the legal 2027-01-01 and says so."""
    text = str(o["salderen_until"]).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        _LOGGER.warning("salderen_until %r is not an ISO date; using %s", text, DEFAULT_OPTIONS["salderen_until"])
        return date.fromisoformat(DEFAULT_OPTIONS["salderen_until"])


def deadlines_from_options(o: dict[str, Any]) -> tuple[time | None, ...]:
    """The weekly deadline schedule (Monday first) from the HH:MM texts of the options; an empty or unreadable text means no deadline that day."""
    out: list[time | None] = []
    for day in WEEKDAYS:
        text = str(o[f"ev_deadline_{day}"]).strip()
        try:
            out.append(time.fromisoformat(text) if text else None)
        except ValueError:
            _LOGGER.warning("ev_deadline_%s %r is not a time of day (HH:MM); no deadline that day", day, text)
            out.append(None)
    return tuple(out)


def ev_config_from_options(o: dict[str, Any]) -> EvConfig:
    """The EV module's settings from the (default-filled) options."""
    return EvConfig(enabled=bool(o["ev_enabled"]), capacity_kwh=float(o["ev_capacity_kwh"]), charge_efficiency=float(o["ev_charge_efficiency"]),
                    target_required_pct=float(o["ev_target_required_pct"]), target_max_pct=float(o["ev_target_max_pct"]), max_price_eur_kwh=float(o["ev_max_price"]),
                    solar_only=bool(o["ev_solar_only"]), min_current_a=float(o["ev_min_current_a"]), max_current_a=float(o["ev_max_current_a"]),
                    deadlines=deadlines_from_options(o), min_on_minutes=float(o["ev_min_on_minutes"]), min_off_minutes=float(o["ev_min_off_minutes"]))


def settings_from_entry(entry: ConfigEntry, latitude: float, longitude: float) -> EngineSettings:
    """Engine settings from the options (defaults fill gaps) and the Home Assistant location."""
    o = {**DEFAULT_OPTIONS, **entry.options}
    battery = BatteryConfig(capacity_kwh=o["capacity_kwh"], max_power_kw=o["max_power_kw"], hard_min_soc=o["hard_min_soc_pct"] / 100,
                            reserve_soc=o["reserve_soc_pct"] / 100, reserve_max_soc=max(o["reserve_soc_pct"], o["reserve_max_soc_pct"]) / 100,
                            reserve_load_factor=o["reserve_load_factor"], round_trip_eff=o["round_trip_eff"], min_profit_margin=o["min_profit_margin"],
                            hold_cost_kwh_h=o["hold_cost_kwh_h"])
    prices = PriceModel(import_vat_multiplier=o["import_vat_multiplier"], import_markup=o["import_markup"],
                        import_energy_tax=o["import_energy_tax"], export_vat_multiplier=o["export_vat_multiplier"],
                        export_bonus_pct=o["export_bonus_pct"], export_fixed_bonus=o["export_fixed_bonus"],
                        export_energy_tax=o["export_energy_tax"], salderen=o["salderen"], netting_ends=netting_end_from_options(o),
                        bonus_only_daylight=o["bonus_only_daylight"], bonus_only_positive_price=o["bonus_only_positive_price"])
    return EngineSettings(battery=battery, prices=prices, latitude=latitude, longitude=longitude,
                          pv_gain_w_per_wm2=o["pv_gain_w_per_wm2"] or 7.0, pv_max_ac_w=o["pv_max_ac_w"],
                          tz=dt_util.get_default_time_zone(), water_heater=water_heater_from_options(o), ev=ev_config_from_options(o),
                          grid_limit_a=float(o["grid_limit_a"]), grid_margin_a=float(o["grid_margin_a"]))


class HemsCoordinator(DataUpdateCoordinator[HemsSnapshot]):
    """Runs the planner in dry-run every quarter (triggered from __init__) and keeps its own caches."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """No polling interval: the integration schedules refreshes on the quarter boundaries."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        trace_path = lambda name: Path(hass.config.path(TRACE_DIR, name))
        self._trace = TraceWriter(trace_path(TRACE_FILE), generations=3)
        self._plans = TraceWriter(trace_path(PLANS_FILE), max_bytes=30_000_000, compact=True, generations=2)
        self._events = TraceWriter(trace_path(EVENTS_FILE), max_bytes=5_000_000, generations=2)
        self._settings_hash: str | None = None
        self._last_status: str | None = None
        self._last_action: str | None = None
        self._last_execution_code: str | None = None
        self._settings: EngineSettings | None = None
        self._last_gain: float | None = None
        self._previous: Decision | None = None
        self._history: list[tuple[datetime, float]] = []
        self._pv_history: list[tuple[datetime, float]] = []
        self._history_at: datetime | None = None
        self._weather: Weather | None = None
        self._last_windows: tuple | None = None
        self.build = "unknown"                      # set by async_setup_entry before the first cycle
        self._market_prices: dict[datetime, float] = {}
        self._market: MarketPrices | None = None
        self._market_tried_at: datetime | None = None
        self._weather_tried_at: datetime | None = None
        self._weather_retry_used = False            # one quick retry per outage: an outage must not turn into a fetch every minute
        self._weather_retry_wanted = False
        self._gain = 0.0
        self._retry_cancel = None
        self._payload: dict[str, Any] | None = None
        self._payload_key: tuple | None = None
        self.control = Control()
        self.ledger: Ledger | None = None
        self._quarter_info: dict[datetime, QuarterPrice] = {}
        self._store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.force_charge = False                  # the owner's override on the EV module; a restart clears it on purpose
        self.saj_names = entity_names(SAJ_PREFIX)
        self._cycles = 0                           # cycles since start: the first one never writes (no old schedule is repeated)

    def _on(self, role: str) -> bool | None:
        """A binary role as a flag: True, False, or None when the role is not set or its entity has no usable state."""
        state = self.hass.states.get(self._entity(role) or "")
        return None if state is None or state.state in ("unavailable", "unknown") else state.state == "on"

    def ev_state(self, settings: EngineSettings) -> EvState:
        """The car and its socket from the configured entities (read only); a role that is not set reads as unknown."""
        charging_state = self.hass.states.get(self._entity(CONF_EV_CHARGING) or "")
        plugged, problem = self._on(CONF_EV_PLUGGED), self._on(CONF_EV_PROBLEM)
        soc = reading_from_state(self.hass.states.get(self._entity(CONF_EV_SOC) or ""))
        if self.force_charge and (plugged is False or (soc is not None and soc.value >= settings.ev.target_required_pct)):
            self.force_charge = False                       # the override ends with the car leaving or the required target
        return EvState(plugged, soc, bool(self._on(CONF_EV_CHARGING)), bool(problem), self.force_charge,
                       charging_state.last_changed if charging_state else None)

    def ev_ceiling_a(self, settings: EngineSettings) -> EvConfig:
        """The EV settings with the ceiling held under what the charger says it accepts (the `max` of its limit number), when it says."""
        state = self.hass.states.get(self._entity(CONF_EV_LIMIT) or "")
        try:
            accepted = float(state.attributes["max"]) if state else None
        except (KeyError, TypeError, ValueError):
            accepted = None
        return settings.ev if accepted is None else replace(settings.ev, max_current_a=min(settings.ev.max_current_a, accepted))

    def ev_allowed_a(self, settings: EngineSettings) -> float | None:
        """The current per phase the car may draw now: what the tightest phase leaves under the limit minus the margin, from the live meter.

        The meter's own current per phase has no sign, so a phase that feeds in (its feed-in power above zero) counts negative. The car's
        own current is taken off first, because the question is what everything else leaves. None when a phase has no reading."""
        meter, ev = [], []
        for phase, (current_role, export_role, ev_role) in enumerate(zip(CONF_METER_CURRENTS, CONF_METER_EXPORTS, CONF_EV_CURRENTS)):
            current = reading_from_state(self.hass.states.get(self._entity(current_role) or ""))
            if current is None:
                return None
            exporting = reading_from_state(self.hass.states.get(self._entity(export_role) or ""))
            car = reading_from_state(self.hass.states.get(self._entity(ev_role) or ""))
            meter.append(current.value * (-1.0 if exporting is not None and exporting.value > 0 else 1.0))
            ev.append(car.value if car is not None else 0.0)
        others = [m - e for m, e in zip(meter, ev)]
        return phase_room_a(others, (1.0, 1.0, 1.0), settings.grid_limit_a - settings.grid_margin_a)

    async def set_force_charge(self, on: bool) -> None:
        """Switch the owner's override and replan at once, so the sensors follow the switch."""
        self.force_charge = on
        await self._log_event("ev_force", on=on)
        await self.async_refresh()                          # not the debounced request: a switch that answers late looks broken

    async def _log_event(self, event: str, **fields: Any) -> None:
        """Append one line to events.jsonl (fetches, status and action changes, settings) and log it in Home Assistant too."""
        _LOGGER.info("%s", event_line(event, fields))
        _LOGGER.debug("HEMS event %s (full): %s", event, fields)
        await self.hass.async_add_executor_job(self._events.write, {"event": event, **fields})

    async def _log_settings(self, settings: EngineSettings) -> None:
        """Log the settings in force whenever their hash changes (first cycle included), plus the entity roles."""
        engine = {"pv_max_ac_w": settings.pv_max_ac_w, "load_days": settings.load_days, "default_load_w": settings.default_load_w,
                  "max_slots": settings.max_slots, "soc_max_age_s": settings.soc_max_age.total_seconds(),
                  "latitude": round(settings.latitude, 2), "longitude": round(settings.longitude, 2)}
        snapshot = settings_snapshot({"battery": settings.battery, "prices": settings.prices, "engine": engine, "water_heater": settings.water_heater, "ev": settings.ev, "grid": {"limit_a": settings.grid_limit_a, "margin_a": settings.grid_margin_a}})
        if snapshot["hash"] != self._settings_hash:
            roles = {k: v for k, v in self.config_entry.data.items()}
            await self._log_event("settings", hash=snapshot["hash"], build=self.build, previous=self._settings_hash, values=snapshot["values"], roles=roles)
            self._settings_hash = snapshot["hash"]

    async def _retry(self, _now: datetime) -> None:
        """Replan once after RETRY_DELAY because an input (SoC, prices) was missing."""
        self._retry_cancel = None
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Cancel a pending retry together with the coordinator."""
        if self._retry_cancel:
            self._retry_cancel()
            self._retry_cancel = None
        await super().async_shutdown()

    def _entity(self, key: str) -> str | None:
        """Entity id configured for a role, or None."""
        return self.config_entry.data.get(key)

    async def _statistics(self, entity_ids: set[str], start: datetime) -> dict[str, list[tuple[datetime, float]]]:
        """Hourly means from the recorder's long-term statistics for the given entities."""
        raw = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period, self.hass, start, None, entity_ids, "hour", None, {"mean"})
        return {eid: statistic_rows(raw.get(eid)) for eid in entity_ids}

    async def _refresh_history(self, now: datetime) -> None:
        """Rebuild the hourly base-load and PV history when the cache is older than HISTORY_REFRESH."""
        if self._history_at and now - self._history_at < HISTORY_REFRESH:
            return
        roles = {k: self._entity(k) for k in (CONF_GRID, CONF_PV, CONF_BATTERY_POWER, CONF_EV, CONF_INVERTER)}
        extras = list(self.config_entry.data.get(CONF_PV_EXTRA) or [])
        wanted = {e for e in roles.values() if e} | set(extras)
        start = (now - timedelta(days=HISTORY_DAYS)).replace(minute=0, second=0, microsecond=0)
        series = await self._statistics(wanted, start)
        get = lambda role: series.get(roles[role], []) if roles[role] else []
        sign = -1.0 if self.config_entry.data.get(CONF_BATTERY_POSITIVE_DISCHARGING, True) else 1.0     # contract: + charging
        battery = [(t, v * sign) for t, v in get(CONF_BATTERY_POWER)]
        pv = sum_series([get(CONF_PV), *(series.get(e, []) for e in extras)])          # several arrays or inverters count as one PV
        self._history = base_load_history(get(CONF_GRID), pv, battery, get(CONF_EV), get(CONF_INVERTER))
        self._pv_history = pv
        self._history_at = now
        await self._log_event("history", base_load_hours=len(self._history), pv_hours=len(self._pv_history),
                              entities_with_statistics=sorted(e for e in wanted if series.get(e)),
                              entities_without_statistics=sorted(e for e in wanted if not series.get(e)))

    async def _refresh_market(self, now: datetime) -> None:
        """Fetch the day-ahead prices that should be known now (today, tomorrow once published).

        HTTP 204 means 'not published yet'. A failed request keeps the prices already held; the engine then
        falls back to the price-curve sensor when the market series does not cover the current quarter."""
        options = {**DEFAULT_OPTIONS, **self.config_entry.options}
        if not options["nordpool_enabled"]:
            self._market = None
            return
        if not fetch_due(now, self._market, self._market_tried_at):
            return
        self._market_tried_at = now
        area = options["delivery_area"]
        results: list[dict[str, Any]] = []
        for day in delivery_dates(now):
            try:
                async with async_get_clientsession(self.hass).get(
                        NORD_POOL_URL, params=nordpool_params(day, area), headers=NORD_POOL_HEADERS,
                        timeout=aiohttp.ClientTimeout(total=20)) as response:
                    if response.status == 204:
                        results.append({"day": day.isoformat(), "http": 204, "quarters": 0})
                        continue
                    response.raise_for_status()
                    parsed = parse_day_ahead(await response.json(), area)
                    self._market_prices.update(parsed)
                    results.append({"day": day.isoformat(), "http": response.status, "quarters": len(parsed)})
            except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as err:
                _LOGGER.warning("Nord Pool fetch for %s failed (%s); keeping the prices already known", day, err)
                results.append({"day": day.isoformat(), "error": str(err)[:200]})
        cutoff = now - timedelta(days=2)
        self._market_prices = {s: p for s, p in self._market_prices.items() if s >= cutoff}
        self._market = merge_days([self._market_prices], now)
        await self._log_event("market", fetched=results, known_quarters=len(self._market_prices),
                              covers_until=self._market.covers_until().isoformat() if self._market else None)

    async def _refresh_weather(self, now: datetime, settings: EngineSettings) -> None:
        """Fetch Open-Meteo at most every WEATHER_REFRESH; keep the last good copy for WEATHER_MAX_AGE."""
        if not {**DEFAULT_OPTIONS, **self.config_entry.options}["weather_enabled"]:
            self._weather = None
            return
        if self._weather_tried_at and now - self._weather_tried_at < WEATHER_REFRESH:
            return
        self._weather_tried_at = now
        try:
            async with async_get_clientsession(self.hass).get(
                    OPEN_METEO_URL, params=open_meteo_params(settings.latitude, settings.longitude),
                    timeout=aiohttp.ClientTimeout(total=20)) as response:
                response.raise_for_status()
                self._weather = parse_open_meteo(await response.json(), now)
            self._weather_retry_used = False
            await self._log_event("weather", ok=True, quarters=len(self._weather.ghi_w_m2))
        except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as err:
            _LOGGER.warning("Weather fetch failed (%s); using the last copy if it is recent enough", err)
            dropped = bool(self._weather and now - self._weather.fetched_at > WEATHER_MAX_AGE)
            if dropped:
                self._weather = None
            await self._log_event("weather", ok=False, error=str(err)[:200], kept_previous=self._weather is not None, dropped_stale=dropped)
            if self._weather is None and not self._weather_retry_used:
                # Right after a restart Open-Meteo may answer 503 once; without a copy the plan would run on no PV forecast for
                # half an hour. Try again at the next retry (a minute away) instead of after WEATHER_REFRESH, once per outage.
                self._weather_retry_used = self._weather_retry_wanted = True
                self._weather_tried_at = None

    def _calibrated_gain(self, settings: EngineSettings) -> float:
        """PV gain: the setting when given, otherwise fitted from recorded PV against the weather series."""
        configured = {**DEFAULT_OPTIONS, **self.config_entry.options}["pv_gain_w_per_wm2"]
        if configured or not self._weather:
            return configured or settings.pv_gain_w_per_wm2
        return fit_gain_from_history(self._pv_history, self._weather.ghi_w_m2, settings.pv_gain_w_per_wm2)

    async def _note_execution(self, execution: Execution) -> None:
        """Log the executor's outcome when its code changes (first cycle included): that is where plan and live SoC disagree."""
        if execution.code == self._last_execution_code:
            return
        await self._log_event("executor", **{"from": self._last_execution_code, "to": execution.code}, planned_w=execution.planned_w,
                              power_w=execution.power_w, soc_pct=execution.soc_pct, reason=execution.reason)
        if execution.overridden:
            _LOGGER.warning("HEMS executor overrides the plan: %s (planned %s W, now %s W)", execution.reason, execution.planned_w, execution.power_w)
        self._last_execution_code = execution.code

    async def _note_windows(self, output: EngineOutput) -> None:
        """Log the sell windows when what the plan does with them changes, and warn about a window that pays but is not sold.

        'unsold' (energy is there, the window pays, no better window explains it) and sales outside every window are what a
        reviewer would otherwise have to find by hand: a missed peak, or a plan that sells where the prices do not say so."""
        windows = output.trace.get("windows")
        if windows is None:
            return
        outside = output.trace.get("windows_outside_kwh", 0.0)
        signature = (tuple((w["from"], w["status"]) for w in windows), outside > 0)
        if signature == self._last_windows:
            return
        self._last_windows = signature
        compact = [{k: w[k] for k in ("from", "to", "peak", "viable", "status", "sold_kwh", "from_stock_kwh")} for w in windows]
        await self._log_event("windows", windows=compact, outside_kwh=outside)
        unsold = [w for w in windows if w["status"] == UNSOLD]
        if unsold or outside >= 0.5:
            _LOGGER.warning("HEMS window check: %s unsold window(s) %s, %.1f kWh sold outside every window", len(unsold), [(w["from"], w["peak"]) for w in unsold], outside)

    async def async_recheck_execution(self) -> None:
        """Check the plan's command against the live SoC again inside the quarter; publish and log when the outcome changes.

        The planner only runs on the quarter; the SoC moves in between (a discharge reaching the floor, a battery that
        fills up), so this runs on every SoC update and costs nothing when nothing changes."""
        snapshot, settings = self.data, self._settings
        if snapshot is None or settings is None or snapshot.output.decision is None:
            return
        reading = reading_from_state(self.hass.states.get(self._entity(CONF_SOC) or ""))
        execution = execute(snapshot.output.decision, dt_util.utcnow(), reading, settings.battery, settings.soc_max_age)
        previous = snapshot.execution
        if execution.code == previous.code and abs(execution.power_w - previous.power_w) < EXECUTION_NOTICE_W:
            return
        self.async_set_updated_data(replace(snapshot, execution=execution))
        await self._note_execution(execution)

    async def _log_cycle(self, output: EngineOutput, now: datetime, gain: float, weather_age: float | None, has_curve: bool,
                         execution: Execution) -> None:
        """Write the cycle's decision record and full plan, log status/action changes, and the decision to the HA log."""
        decision = output.decision
        action = decision.plan.slots[0].action if decision else None
        inputs = {**output.trace.get("inputs", {}), "history_hours": len(self._history), "weather_age_min": None if weather_age is None else round(weather_age),
                  "market_age_min": round((now - self._market.fetched_at).total_seconds() / 60) if self._market else None, "price_curve_configured": has_curve}
        record = {"dry_run": True, "build": self.build, "pv_gain": round(gain, 2), "settings": self._settings_hash, **output.trace, "inputs": inputs,
                  "previous_action": self._last_action, "action_changed": bool(action and self._last_action and action != self._last_action),
                  "execution": {"code": execution.code, "planned_w": execution.planned_w, "power_w": execution.power_w, "reason": execution.reason}}
        await self.hass.async_add_executor_job(self._trace.write, record)
        if output.detail and {**DEFAULT_OPTIONS, **self.config_entry.options}["trace_full_plan"]:
            await self.hass.async_add_executor_job(self._plans.write, output.detail)
        if output.status != self._last_status:
            await self._log_event("status", **{"from": self._last_status, "to": output.status})
            if output.status != "ok":
                # the battery sensors appear shortly after HA starts and the retry plans within a minute, so a missing SoC on the first cycle is not a warning
                startup = self._last_status is None and output.status == "no_soc"
                _LOGGER.log(logging.INFO if startup else logging.WARNING, "HEMS status %s: no decision this quarter", output.status)
            self._last_status = output.status
        if action and action != self._last_action:
            await self._log_event("action", **{"from": self._last_action, "to": action}, power_w=output.trace.get("power_w"), reason=output.trace.get("reason"),
                                  soc_pct=output.trace.get("soc_pct"), slot_start=output.trace.get("slot_start"))
        if action:
            self._last_action = action
        await self._note_execution(execution)
        tz = dt_util.get_default_time_zone()
        suffix = ""
        if execution.code != AS_PLANNED:
            suffix = f" | executor {execution.code}" + (f": {execution.power_w} W instead of {execution.planned_w} W" if execution.overridden else "")
        _LOGGER.info("%s%s", cycle_line(record, tz), suffix)
        tree = plan_tree(record, tz) + window_tree(record, tz)
        if tree:
            _LOGGER.info("%s", "\n".join(tree))
        await self._note_windows(output)

    async def _async_update_data(self) -> HemsSnapshot:
        """One planning cycle: inputs -> engine -> trace -> snapshot for the sensors."""
        now = dt_util.utcnow()
        settings = settings_from_entry(self.config_entry, self.hass.config.latitude, self.hass.config.longitude)
        await self._refresh_history(now)
        await self._refresh_market(now)
        await self._refresh_weather(now, settings)
        gain = self._calibrated_gain(settings)
        settings = replace(settings, pv_gain_w_per_wm2=gain, ev=self.ev_ceiling_a(settings))
        self._settings = settings
        await self._log_settings(settings)
        if self._last_gain is None or abs(gain - self._last_gain) > 0.02 * self._last_gain:
            await self._log_event("pv_gain", gain=round(gain, 3), previous=self._last_gain and round(self._last_gain, 3),
                                  source="setting" if {**DEFAULT_OPTIONS, **self.config_entry.options}["pv_gain_w_per_wm2"] else "fit")
            self._last_gain = gain
        price_state = self.hass.states.get(self._entity(CONF_PRICE_CURVE) or "")
        inputs = EngineInputs(
            now=now, soc_pct=reading_from_state(self.hass.states.get(self._entity(CONF_SOC) or "")),
            import_curve=parse_price_curve(price_state.attributes.get("price_curve") if price_state else None),
            load_history_w=self._history, ghi_w_m2=self._weather.ghi_w_m2 if self._weather else None, market=self._market,
            ev=self.ev_state(settings) if settings.ev.enabled else None)
        previous = self._previous
        output = await self.hass.async_add_executor_job(step, inputs, settings, previous)
        if output.decision:
            self._previous = output.decision
        self._remember_quarters(output)
        weather_age = (now - self._weather.fetched_at).total_seconds() / 60 if self._weather else None
        execution = execute(output.decision, now, inputs.soc_pct, settings.battery, settings.soc_max_age)
        allowed = self.ev_allowed_a(settings) if output.ev_plan is not None else None
        car = ev_setpoint(output.ev_plan, now, inputs.ev, settings.ev, allowed) if output.ev_plan is not None and inputs.ev is not None else None
        if car is not None:
            output.trace.setdefault("ev", {})["setpoint"] = {"current_a": car.current_a, "planned_a": car.planned_a, "code": car.code, "allowed_a": allowed}
        await self._log_cycle(output, now, gain, weather_age, bool(inputs.import_curve), execution)
        reason = output.status if output.status in RETRY_STATUSES else "weather" if self._weather_retry_wanted else None
        if reason and self._retry_cancel is None:
            self._weather_retry_wanted = False
            self._retry_cancel = async_call_later(self.hass, RETRY_DELAY, self._retry)
            await self._log_event("retry", in_seconds=RETRY_DELAY.total_seconds(), status=reason)
        known = set(self._market.starts if self._market else ()) | {t for t, _ in inputs.import_curve}
        prices_until = max(known) + timedelta(minutes=15) if known else None
        text, windows, table = self._plan_for_users(output)
        self._cycles += 1
        saj = await self._saj_round(output)
        return HemsSnapshot(output, gain, len(self._history), weather_age, tomorrow_quarters(known, now), prices_until, execution, text, windows, table,
                            self._weather, car, allowed, cycle_at=now, previous_decision=previous, saj=saj)

    def may_write(self, output: EngineOutput) -> bool:
        """True only when every condition for a write round holds: the phase lock open, the battery in auto, the master switch on,
        a healthy cycle with a plan, and not the first cycle after a start."""
        return (WRITE_UNLOCKED and self.control.modes.get("battery") == MODE_AUTO and self.control.armed and output.status == "ok"
                and output.decision is not None and self._cycles > 1)

    async def _saj_round(self, output: EngineOutput) -> SajAdvice | None:
        """Work out the SAJ slots for this plan (always, for advisory), and write them when may_write allows. Never breaks the cycle."""
        try:
            advice = advise(self.hass, output, self.saj_names, dt_util.get_default_time_zone())
        except Exception as err:  # noqa: BLE001 - the advisory view must not stop planning
            _LOGGER.warning("HEMS could not work out the SAJ slots: %s", err)
            return None
        if advice is None or not self.may_write(output) or advice.missing or not advice.writes:
            return advice
        plan = plan_writes(read_inputs(self.hass, self.saj_names), advice.target, self.saj_names)
        result = await async_apply(self.hass, plan, self.saj_names)
        await self._log_event("write", module="battery", writes=result.written, ok=result.ok, error=result.error, mismatches=list(result.mismatches)[:5])
        return advice

    # ------------------------------------------------------------------ realised result, control, alerts (dashboard side)

    async def async_load_state(self) -> None:
        """Read the ledger and the owner's modes back from .storage; the master switch always starts off."""
        settings = settings_from_entry(self.config_entry, self.hass.config.latitude, self.hass.config.longitude)
        b = settings.battery
        self.ledger = Ledger(capacity_kwh=b.capacity_kwh, floor_kwh=b.capacity_kwh * b.hard_min_soc, max_kw=b.max_power_kw, round_trip_eff=b.round_trip_eff)
        data = await self._store.async_load() or {}
        self.ledger.restore(data.get("ledger"))
        self.control.restore(data.get("control"))

    def _stored(self) -> dict[str, Any]:
        return {"ledger": self.ledger.state() if self.ledger else None, "control": self.control.state()}

    def _save(self) -> None:
        self._store.async_delay_save(self._stored, 30)

    async def async_save_now(self) -> None:
        """Write the state at once (unload): a delayed save would be lost with the entry."""
        await self._store.async_save(self._stored())

    def _power(self, role: str, sign: float = 1.0) -> float | None:
        reading = reading_from_state(self.hass.states.get(self._entity(role) or ""), sign)
        return None if reading is None else reading.value

    @callback
    def async_sample(self, now: datetime) -> None:
        """Integrate the live grid, PV and battery power into the open quarter; close and price quarters that ended."""
        if self.ledger is None:
            return
        battery_sign = -1.0 if self.config_entry.data.get(CONF_BATTERY_POSITIVE_DISCHARGING, True) else 1.0
        pv_ids = [self._entity(CONF_PV), *(self.config_entry.data.get(CONF_PV_EXTRA) or [])]
        pv_values = [reading_from_state(self.hass.states.get(e or "")) for e in pv_ids if e]
        pv = sum(r.value for r in pv_values if r is not None) if pv_values else None
        soc = self._power(CONF_SOC)
        soc_kwh = None if soc is None else soc / 100 * self.ledger.capacity_kwh
        closed = self.ledger.sample(now, self._power(CONF_GRID), pv, self._power(CONF_BATTERY_POWER, battery_sign), soc_kwh,
                                    ev_w=self._power(CONF_EV) or 0.0, prices=self._quarter_info, tz=dt_util.get_default_time_zone())
        if closed:
            cutoff = quarter_start(now) - timedelta(hours=2)
            self._quarter_info = {t: q for t, q in self._quarter_info.items() if t >= cutoff}
            self._payload_key = None
            self._save()
            self.async_update_listeners()

    def _remember_quarters(self, output: EngineOutput) -> None:
        """Keep the prices, forecast and planned action of the coming quarters, so a quarter can be priced and judged when it closes."""
        prices, decision = output.prices, output.decision
        if not prices:
            return
        planned = {decision.slot_start + i * timedelta(minutes=15): s.action for i, s in enumerate(decision.plan.slots)} if decision else {}
        other = self.hass.states.get(self._entity(CONF_COMPARE_ACTION) or "")
        now_q = quarter_start(dt_util.utcnow())
        for at, imp, exp in zip(prices.starts, prices.import_eur_kwh, prices.export_eur_kwh):
            if now_q <= at < now_q + timedelta(hours=1):
                known = self._quarter_info.get(at)
                self._quarter_info[at] = QuarterPrice(imp, exp, output.pv_kwh.get(at), output.load_kwh.get(at), planned.get(at),
                                                      (other.state if other and at == now_q else (known.other_action if known else None)))

    async def async_set_mode(self, module: str, mode: str) -> None:
        """The owner's mode of a module (dry_run or advisory)."""
        if module not in MODULES or mode not in MODES:
            raise ValueError(f"unknown module or mode: {module} {mode}")
        await self._log_event("mode", module=module, **{"from": self.control.modes.get(module), "to": mode})
        self.control.modes[module] = mode
        self._payload_key = None
        self._save()
        self.async_update_listeners()

    async def async_set_armed(self, armed: bool) -> None:
        """The master switch. It moves nothing yet: no module writes to a device; it is here so the dashboard and the logbook show it."""
        await self._log_event("master", armed=armed)
        self.control.armed = armed
        self._payload_key = None
        self.async_update_listeners()

    async def async_disarm_all(self) -> None:
        """Master off and every module back to dry-run, in one step."""
        await self._log_event("disarm_all", modes=dict(self.control.modes))
        self.control.armed = False
        self.control.modes = {m: "dry_run" for m in MODULES}
        self._payload_key = None
        self._save()
        self.async_update_listeners()

    def recommendations(self) -> list[dict[str, Any]]:
        return self.control.recommendations(self.data)

    async def async_apply(self, rec_id: str) -> dict[str, Any]:
        """Mark an open recommendation applied and fire `hems_recommendation_applied`; an automation of the owner does the work."""
        rec = next((r for r in self.recommendations() if r["id"] == rec_id and r["status"] == "open"), None)
        if rec is None:
            raise KeyError(rec_id)
        self.control.applied[rec_id] = dt_util.utcnow().isoformat()
        self.hass.bus.async_fire(EVENT_APPLIED, {"id": rec_id, "module": rec["module"], "kind": rec["kind"], **rec["payload"]})
        await self._log_event("recommendation_applied", id=rec_id, module=rec["module"], payload=rec["payload"])
        self._payload_key = None
        self._save()
        self.async_update_listeners()
        return rec

    async def async_dismiss(self, rec_id: str) -> None:
        """Hide a recommendation until the plan asks something else (a new id)."""
        self.control.dismissed[rec_id] = None
        await self._log_event("recommendation_dismissed", id=rec_id)
        self._payload_key = None
        self._save()
        self.async_update_listeners()

    def alerts(self) -> dict[str, dict[str, Any]]:
        """The conditions worth a notification, each with on/off and a reason in words."""
        snap = self.data
        out: dict[str, dict[str, Any]] = {}
        if snap is None:
            return out
        status, code = snap.output.status, snap.execution.code
        bad = status != "ok" or code in ("no_soc", "stale_soc")
        out["data"] = {"on": bad, "reason": f"status {status}, executor {code}" if bad else ""}
        ev = snap.output.ev_plan
        risk = bool(ev and ev.status == "deadline_at_risk")
        out["deadline"] = {"on": risk, "reason": f"{ev.shortfall_kwh:.1f} kWh short before {ev.deadline.isoformat() if ev.deadline else '?'}" if risk else ""}
        out["not_executed"] = {"on": bool(snap.execution.overridden), "reason": snap.execution.reason if snap.execution.overridden else ""}
        last = self.hass.states.get(self._entity(CONF_LEGIONELLA_LAST) or "")
        when = None
        if last and last.state not in ("unknown", "unavailable", ""):
            when = dt_util.parse_datetime(last.state)
            if when is None and (day := dt_util.parse_date(last.state)) is not None:
                when = datetime.combine(day, time(0), tzinfo=dt_util.get_default_time_zone())
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=dt_util.get_default_time_zone())
        overdue = bool(when and dt_util.utcnow() - when > LEGIONELLA_OVERDUE)
        out["legionella"] = {"on": overdue, "reason": f"last run {when.isoformat()}" if overdue else "", "last": when.isoformat() if when else None,
                             "configured": bool(self._entity(CONF_LEGIONELLA_LAST))}
        return out

    def dashboard_payload(self) -> dict[str, Any] | None:
        """The panel's data for the latest snapshot (hems.dashboard), cached until the snapshot changes; None before the first cycle."""
        snap = self.data
        if snap is None or self._settings is None:
            return None
        key = (snap, self.force_charge)          # the snapshot itself, not id(): a freed snapshot's address can be reused
        if self._payload_key is None or self._payload_key[0] is not snap or self._payload_key[1] != self.force_charge:
            ledger = self.ledger
            bands = {k: ledger.bands(k) for k in ("pv", "load")} if ledger else None
            self._payload = build_payload(snap, build=self.build, cycle_at=snap.cycle_at, previous=snap.previous_decision,
                                          battery=self._settings.battery, soc_max_age=self._settings.soc_max_age, force_charge=self.force_charge,
                                          bands=bands)
            self._payload["control"] = {"modes": dict(self.control.modes), "armed": self.control.armed, "writers": [],
                                        "recommendations": self.recommendations()}
            self._payload["alerts"] = self.alerts()
            self._payload["saj"] = _saj_payload(snap.saj)
            if ledger:
                self._payload["realised"] = {"today": ledger.result_today(), "gain_total": ledger.gain_total(), "since": ledger.total.get("since"),
                                             "daily": ledger.daily(), "quarters": ledger.quarters[-96:],
                                             "rest_of_day": ledger.rest_of_day(_planned_quarters(snap.output), dt_util.get_default_time_zone()),
                                             "errors": {k: ledger.forecast_error(k) for k in ("pv", "load")}, "bands": bands}
            self._payload_key = key
        return self._payload

    def _plan_for_users(self, output: EngineOutput) -> tuple[str, tuple[dict, ...], str]:
        """The plan's windows as a sentence, as local-time records and as a Markdown table; empty when this cycle has no plan."""
        segments, slot_start = output.trace.get("segments"), output.trace.get("slot_start")
        if not segments or not slot_start:
            return "", (), ""
        # always English, whatever the language of Home Assistant: Mark wants no Dutch in HEMS
        tz, start, words = dt_util.get_default_time_zone(), datetime.fromisoformat(slot_start), plan_words("en")
        return plan_summary(segments, start, tz, words), tuple(plan_windows(segments, tz)), plan_table(segments, start, tz, words, output.decision.analysis if output.decision else None)


def _planned_quarters(output: EngineOutput) -> list[PlannedQuarter]:
    """The plan's coming quarters with the prices and forecast it was made on, for the rest-of-day forecast; empty without a plan."""
    decision, prices = output.decision, output.prices
    if decision is None or not prices:
        return []
    price_at = {at: (imp, exp) for at, imp, exp in zip(prices.starts, prices.import_eur_kwh, prices.export_eur_kwh)}
    rows = []
    for i, slot in enumerate(decision.plan.slots):
        at = decision.slot_start + i * timedelta(minutes=15)
        if at not in price_at:
            continue
        imp, exp = price_at[at]
        rows.append(PlannedQuarter(at, imp, exp, output.pv_kwh.get(at) or 0.0, output.load_kwh.get(at) or 0.0, slot.grid_kwh, slot.soc_kwh))
    return rows


def _saj_payload(advice: SajAdvice | None) -> dict[str, Any] | None:
    """The advisory SAJ schedule for the panel: slots, changes against the inverter, missing entities, the mode it would set."""
    if advice is None:
        return None
    slot = lambda s: {"start": s.start, "end": s.end, "power_pct": s.power_pct, "kwh": s.kwh}
    return {"charge": [slot(s) for s in advice.schedule.charge], "discharge": [slot(s) for s in advice.schedule.discharge],
            "writes": advice.writes, "missing": list(advice.missing), "mode": advice.target.mode, "merge_cost_eur": advice.schedule.merge_cost_eur}
