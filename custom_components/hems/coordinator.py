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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters import base_load_history, parse_price_curve, reading_from_state, statistic_rows
from .const import (CONF_BATTERY_POSITIVE_DISCHARGING, CONF_BATTERY_POWER, CONF_EV, CONF_GRID, CONF_INVERTER, CONF_PRICE_CURVE,
                    CONF_PV, CONF_SOC, DEFAULT_OPTIONS, DOMAIN, HISTORY_DAYS, HISTORY_REFRESH, TRACE_DIR, TRACE_FILE,
                    WEATHER_MAX_AGE, WEATHER_REFRESH)
from .engine.battery import BatteryConfig
from .engine.dryrun import EngineInputs, EngineOutput, EngineSettings, step
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


def settings_from_entry(entry: ConfigEntry, latitude: float, longitude: float) -> EngineSettings:
    """Engine settings from the options (defaults fill gaps) and the Home Assistant location."""
    o = {**DEFAULT_OPTIONS, **entry.options}
    battery = BatteryConfig(capacity_kwh=o["capacity_kwh"], max_power_kw=o["max_power_kw"], hard_min_soc=o["hard_min_soc_pct"] / 100,
                            reserve_soc=o["reserve_soc_pct"] / 100, round_trip_eff=o["round_trip_eff"], wear_cost=o["wear_cost"])
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
        self._trace = TraceWriter(Path(hass.config.path(TRACE_DIR, TRACE_FILE)))
        self._previous: Decision | None = None
        self._history: list[tuple[datetime, float]] = []
        self._pv_history: list[tuple[datetime, float]] = []
        self._history_at: datetime | None = None
        self._weather: Weather | None = None
        self._weather_tried_at: datetime | None = None
        self._gain = 0.0

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
        except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as err:
            _LOGGER.warning("Weather fetch failed (%s); using the last copy if it is recent enough", err)
            if self._weather and now - self._weather.fetched_at > WEATHER_MAX_AGE:
                self._weather = None

    def _calibrated_gain(self, settings: EngineSettings) -> float:
        """PV gain: the setting when given, otherwise fitted from recorded PV against the weather series."""
        configured = {**DEFAULT_OPTIONS, **self.config_entry.options}["pv_gain_w_per_wm2"]
        if configured or not self._weather:
            return configured or settings.pv_gain_w_per_wm2
        return fit_gain_from_history(self._pv_history, self._weather.ghi_w_m2, settings.pv_gain_w_per_wm2)

    async def _async_update_data(self) -> HemsSnapshot:
        """One planning cycle: inputs -> engine -> trace -> snapshot for the sensors."""
        now = dt_util.utcnow()
        settings = settings_from_entry(self.config_entry, self.hass.config.latitude, self.hass.config.longitude)
        await self._refresh_history(now)
        await self._refresh_weather(now, settings)
        gain = self._calibrated_gain(settings)
        settings = replace(settings, pv_gain_w_per_wm2=gain)
        price_state = self.hass.states.get(self._entity(CONF_PRICE_CURVE) or "")
        inputs = EngineInputs(
            now=now, soc_pct=reading_from_state(self.hass.states.get(self._entity(CONF_SOC) or "")),
            import_curve=parse_price_curve(price_state.attributes.get("price_curve") if price_state else None),
            load_history_w=self._history, ghi_w_m2=self._weather.ghi_w_m2 if self._weather else None)
        output = await self.hass.async_add_executor_job(step, inputs, settings, self._previous)
        if output.decision:
            self._previous = output.decision
        await self.hass.async_add_executor_job(self._trace.write, {"dry_run": True, "pv_gain": round(gain, 2), **output.trace})
        weather_age = (now - self._weather.fetched_at).total_seconds() / 60 if self._weather else None
        return HemsSnapshot(output, gain, len(self._history), weather_age)
