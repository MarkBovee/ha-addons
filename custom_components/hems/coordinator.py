"""Coordinator: every quarter gather the inputs, run the dry-run engine, trace the decision, publish.

It never writes to a device. Home Assistant entities are the only interface: states for SoC, power and prices,
recorder statistics for the consumption history, and one HTTP weather source owned by HEMS itself.
"""
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters import base_load_history, parse_price_curve, reading_from_state, statistic_rows
from .const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_EV, CONF_GRID, CONF_INVERTER, CONF_PRICE_CURVE,
                    CONF_PV, CONF_SOC, DEFAULT_OPTIONS, DOMAIN, EVENTS_FILE, EXECUTION_NOTICE_W, HISTORY_DAYS, HISTORY_REFRESH,
                    PLANS_FILE, RETRY_DELAY, RETRY_STATUSES, TRACE_DIR, TRACE_FILE, WEATHER_MAX_AGE, WEATHER_REFRESH)
from .engine.battery import BatteryConfig
from .engine.contracts import MarketPrices
from .engine.decision_log import cycle_line, event_line, plan_summary, plan_table, plan_tree, plan_windows, plan_words, settings_snapshot
from .engine.nordpool import NORD_POOL_HEADERS, NORD_POOL_URL, delivery_dates, fetch_due, merge_days, nordpool_params, parse_day_ahead, tomorrow_quarters
from .engine.dryrun import EngineInputs, EngineOutput, EngineSettings, step
from .engine.executor import AS_PLANNED, Execution, execute
from .engine.pvforecast import fit_gain_from_history
from .engine.prices import PriceModel
from .engine.rolling import Decision
from .engine.trace import TraceWriter
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


def settings_from_entry(entry: ConfigEntry, latitude: float, longitude: float) -> EngineSettings:
    """Engine settings from the options (defaults fill gaps) and the Home Assistant location."""
    o = {**DEFAULT_OPTIONS, **entry.options}
    battery = BatteryConfig(capacity_kwh=o["capacity_kwh"], max_power_kw=o["max_power_kw"], hard_min_soc=o["hard_min_soc_pct"] / 100,
                            reserve_soc=o["reserve_soc_pct"] / 100, round_trip_eff=o["round_trip_eff"], min_profit_margin=o["min_profit_margin"],
                            hold_cost_kwh_h=o["hold_cost_kwh_h"])
    prices = PriceModel(import_vat_multiplier=o["import_vat_multiplier"], import_markup=o["import_markup"],
                        import_energy_tax=o["import_energy_tax"], export_vat_multiplier=o["export_vat_multiplier"],
                        export_bonus_pct=o["export_bonus_pct"], export_fixed_bonus=o["export_fixed_bonus"],
                        export_energy_tax=o["export_energy_tax"], salderen=o["salderen"],
                        bonus_only_daylight=o["bonus_only_daylight"], bonus_only_positive_price=o["bonus_only_positive_price"])
    return EngineSettings(battery=battery, prices=prices, latitude=latitude, longitude=longitude,
                          pv_gain_w_per_wm2=o["pv_gain_w_per_wm2"] or 7.0, pv_max_ac_w=o["pv_max_ac_w"],
                          tz=dt_util.get_default_time_zone())


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
        self.build = "unknown"                      # set by async_setup_entry before the first cycle
        self._market_prices: dict[datetime, float] = {}
        self._market: MarketPrices | None = None
        self._market_tried_at: datetime | None = None
        self._weather_tried_at: datetime | None = None
        self._gain = 0.0
        self._retry_cancel = None

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
        snapshot = settings_snapshot({"battery": settings.battery, "prices": settings.prices, "engine": engine})
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
        wanted = {e for e in roles.values() if e}
        start = (now - timedelta(days=HISTORY_DAYS)).replace(minute=0, second=0, microsecond=0)
        series = await self._statistics(wanted, start)
        get = lambda role: series.get(roles[role], []) if roles[role] else []
        sign = -1.0 if self.config_entry.data.get(CONF_BATTERY_POSITIVE_DISCHARGING, True) else 1.0     # contract: + charging
        battery = [(t, v * sign) for t, v in get(CONF_BATTERY_POWER)]
        self._history = base_load_history(get(CONF_GRID), get(CONF_PV), battery, get(CONF_EV), get(CONF_INVERTER))
        self._pv_history = get(CONF_PV)
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
            await self._log_event("weather", ok=True, quarters=len(self._weather.ghi_w_m2))
        except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as err:
            _LOGGER.warning("Weather fetch failed (%s); using the last copy if it is recent enough", err)
            dropped = bool(self._weather and now - self._weather.fetched_at > WEATHER_MAX_AGE)
            if dropped:
                self._weather = None
            await self._log_event("weather", ok=False, error=str(err)[:200], kept_previous=self._weather is not None, dropped_stale=dropped)

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
                _LOGGER.warning("HEMS status %s: no decision this quarter", output.status)
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
        tree = plan_tree(record, tz)
        if tree:
            _LOGGER.info("%s", "\n".join(tree))

    async def _async_update_data(self) -> HemsSnapshot:
        """One planning cycle: inputs -> engine -> trace -> snapshot for the sensors."""
        now = dt_util.utcnow()
        settings = settings_from_entry(self.config_entry, self.hass.config.latitude, self.hass.config.longitude)
        await self._refresh_history(now)
        await self._refresh_market(now)
        await self._refresh_weather(now, settings)
        gain = self._calibrated_gain(settings)
        settings = replace(settings, pv_gain_w_per_wm2=gain)
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
            load_history_w=self._history, ghi_w_m2=self._weather.ghi_w_m2 if self._weather else None, market=self._market)
        output = await self.hass.async_add_executor_job(step, inputs, settings, self._previous)
        if output.decision:
            self._previous = output.decision
        weather_age = (now - self._weather.fetched_at).total_seconds() / 60 if self._weather else None
        execution = execute(output.decision, now, inputs.soc_pct, settings.battery, settings.soc_max_age)
        await self._log_cycle(output, now, gain, weather_age, bool(inputs.import_curve), execution)
        if output.status in RETRY_STATUSES and self._retry_cancel is None:
            self._retry_cancel = async_call_later(self.hass, RETRY_DELAY, self._retry)
            await self._log_event("retry", in_seconds=RETRY_DELAY.total_seconds(), status=output.status)
        known = set(self._market.starts if self._market else ()) | {t for t, _ in inputs.import_curve}
        prices_until = max(known) + timedelta(minutes=15) if known else None
        text, windows, table = self._plan_for_users(output)
        return HemsSnapshot(output, gain, len(self._history), weather_age, tomorrow_quarters(known, now), prices_until, execution, text, windows, table,
                            self._weather)

    def _plan_for_users(self, output: EngineOutput) -> tuple[str, tuple[dict, ...], str]:
        """The plan's windows as a sentence, as local-time records and as a Markdown table; empty when this cycle has no plan."""
        segments, slot_start = output.trace.get("segments"), output.trace.get("slot_start")
        if not segments or not slot_start:
            return "", (), ""
        tz, start, words = dt_util.get_default_time_zone(), datetime.fromisoformat(slot_start), plan_words(self.hass.config.language)
        return plan_summary(segments, start, tz, words), tuple(plan_windows(segments, tz)), plan_table(segments, start, tz, words)
