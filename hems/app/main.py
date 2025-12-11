"""HEMS add-on entrypoint.

Implements Range-Based battery control using the energy-prices sensor and applies
schedules via the battery-api add-on. Provides adaptive discharge adjustments and
status exposure through the HA REST API.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.12 includes zoneinfo
    from backports.zoneinfo import ZoneInfo  # type: ignore

# Add parent directory to path for shared module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.config_loader import get_run_once_mode, load_addon_config
from shared.ha_api import HomeAssistantApi

logger = setup_logging(name="hems")


@dataclass
class PricePoint:
    start: datetime
    price: float


@dataclass
class SchedulePeriod:
    action: str  # "charge" or "discharge"
    start: datetime
    duration: int  # minutes
    power: int  # watts (positive magnitude)


CONFIG_DEFAULTS: Dict[str, Any] = {
    "price_sensor_entity_id": "sensor.energy_prices_electricity_import_price",
    "average_power_sensor_entity_id": "sensor.battery_api_load_power",
    "battery_power_sensor_entity_id": "sensor.battery_api_battery_power",
    "battery_grid_power_sensor_entity_id": "sensor.battery_api_grid_power",
    "battery_soc_sensor_entity_id": "sensor.battery_api_battery_soc",
    "battery_api_status_sensor_entity_id": "sensor.battery_api_api_status",
    "max_inverter_power_w": 8000,
    "default_charge_power_w": 8000,
    "default_discharge_power_w": 8000,
    "min_discharge_power_w": 0,
    "min_scaled_power_w": 2500,
    "conservative_soc_threshold_percent": 30.0,
    "minimum_discharge_soc_percent": 5.0,
    "topx_charge_count": 30,
    "topx_discharge_count": 10,
    "adaptive_monitor_interval_minutes": 1,
    "adaptive_power_grace_period_seconds": 60,
    "schedule_regeneration_cooldown_seconds": 60,
    "status_refresh_minutes": 15,
    "daily_reload_time": "01:00",
    "hourly_regeneration": True,
    "adaptive_disable_threshold_w": 1500,
    "adaptive_power_increment_w": 100,
    "temperature_based_discharge_enabled": True,
    "temperature_forecast_sensor_entity_id": "sensor.temperatuur_1d",
    "temperature_fallback_sensor_entity_id": "sensor.our_home_outdoor_temperature",
    "temperature_default_discharge_count": 10,
    "enable_opportunistic_solar": False,
    "solar_production_sensor_entity_id": "sensor.power_production_now",
    "solar_energy_today_sensor_entity_id": "sensor.energy_production_today",
    "solar_energy_next_hour_sensor_entity_id": "sensor.energy_next_hour",
    "solar_energy_tomorrow_sensor_entity_id": "sensor.energy_production_tomorrow",
    "sun_entity_id": "sun.sun",
    "simulation_mode": False,
}


def load_config() -> Dict[str, Any]:
    """Load add-on config with defaults."""
    return load_addon_config(defaults=CONFIG_DEFAULTS)


class HemsController:
    """Core controller for Range-Based scheduling and adaptive power."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ha = HomeAssistantApi()
        tz_name = self.ha.get_timezone() or "UTC"
        self.tz = ZoneInfo(tz_name)
        self.simulation = bool(config.get("simulation_mode", False))
        self.last_schedule: List[SchedulePeriod] = []
        self.last_schedule_published: Optional[datetime] = None
        self.last_status_update: Optional[datetime] = None
        self.last_adaptive_update: Optional[datetime] = None
        self.last_regeneration: Optional[datetime] = None
        self.last_price_state: Optional[str] = None
        if self.simulation:
            logger.info("Simulation mode enabled: no HA writes or schedule publishes will occur")
        logger.info("Using timezone %s", tz_name)

    # ---------- Data fetch helpers ----------
    def _get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self.ha.get_entity_state(entity_id)

    def _get_float_state(self, entity_id: str) -> Optional[float]:
        state = self._get_entity_state(entity_id)
        if not state:
            return None
        try:
            return float(state.get("state"))
        except (TypeError, ValueError):
            return None

    def _get_bool_state(self, entity_id: str) -> Optional[bool]:
        state = self._get_entity_state(entity_id)
        if not state:
            return None
        raw = str(state.get("state", "")).lower()
        if raw in ("on", "true", "1", "above_horizon"):
            return True
        if raw in ("off", "false", "0", "below_horizon"):
            return False
        return None

    # ---------- Price handling ----------
    def _load_price_curve(self) -> List[PricePoint]:
        entity_id = self.config.get("price_sensor_entity_id")
        state = self._get_entity_state(entity_id)
        if not state:
            logger.error("Price sensor %s not found", entity_id)
            return []

        attributes = state.get("attributes", {}) or {}
        curve = attributes.get("price_curve") or attributes.get("prices") or []
        price_points: List[PricePoint] = []
        now = datetime.now(self.tz)

        for item in curve:
            start_raw = item.get("start")
            price = item.get("price") or item.get("value")
            if start_raw is None or price is None:
                continue
            try:
                start_dt = datetime.fromisoformat(start_raw)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=self.tz)
                else:
                    start_dt = start_dt.astimezone(self.tz)
                price_points.append(PricePoint(start=start_dt, price=float(price)))
            except Exception as exc:  # defensive parsing
                logger.debug("Skipping price point %s due to parse error: %s", item, exc)

        if not price_points:
            # Fallback: try current state as single price
            try:
                current_price = float(state.get("state"))
                price_points.append(PricePoint(start=now, price=current_price))
            except (TypeError, ValueError):
                logger.error("Price sensor %s has no usable data", entity_id)

        price_points.sort(key=lambda p: p.start)
        return price_points

    # ---------- Schedule generation ----------
    def _select_action_intervals(
        self, price_points: List[PricePoint], now: datetime
    ) -> Tuple[List[PricePoint], Dict[str, List[PricePoint]]]:
        horizon_end = now + timedelta(hours=24)
        window = [p for p in price_points if now <= p.start < horizon_end]
        if not window:
            logger.error("No price points in the next 24h window")
            return [], {"charge": [], "discharge": []}

        # Rank cheapest for charge
        sorted_by_price = sorted(window, key=lambda p: p.price)
        charge = sorted_by_price[: self.config.get("topx_charge_count", 0)]

        # Rank most expensive for discharge, skipping already charge-selected times
        charge_times = {p.start for p in charge}
        sorted_desc = sorted(window, key=lambda p: p.price, reverse=True)
        discharge: List[PricePoint] = []
        for point in sorted_desc:
            if point.start in charge_times:
                continue
            if len(discharge) >= self.config.get("topx_discharge_count", 0):
                break
            discharge.append(point)

        # Log ranges for comparison with legacy NetDaemon output
        def _range(points: List[PricePoint]) -> Tuple[Optional[float], Optional[float]]:
            if not points:
                return None, None
            prices = [p.price for p in points]
            return min(prices), max(prices)

        charge_min, charge_max = _range(charge)
        discharge_min, discharge_max = _range(discharge)
        window_prices = [p.price for p in window]
        logger.info(
            "Price window 24h | min=%.3f max=%.3f | charge_top=%s-%s (n=%d) | discharge_top=%s-%s (n=%d)",
            min(window_prices),
            max(window_prices),
            f"{charge_min:.3f}" if charge_min is not None else None,
            f"{charge_max:.3f}" if charge_max is not None else None,
            len(charge),
            f"{discharge_min:.3f}" if discharge_min is not None else None,
            f"{discharge_max:.3f}" if discharge_max is not None else None,
            len(discharge),
        )

        return window, {"charge": charge, "discharge": discharge}

    def _merge_intervals(self, actions: Dict[str, List[PricePoint]], now: datetime) -> List[SchedulePeriod]:
        # Build interval map (15 minute cadence assumed)
        intervals: Dict[datetime, str] = {}
        for action, points in actions.items():
            for p in points:
                intervals[p.start] = action

        merged: List[SchedulePeriod] = []
        sorted_starts = sorted(intervals.keys())
        if not sorted_starts:
            return merged

        current_action = intervals[sorted_starts[0]]
        period_start = sorted_starts[0]
        duration = 15

        for idx in range(1, len(sorted_starts)):
            start = sorted_starts[idx]
            expected_next = sorted_starts[idx - 1] + timedelta(minutes=15)
            action = intervals[start]
            if action == current_action and start == expected_next:
                duration += 15
            else:
                merged.append(
                    SchedulePeriod(action=current_action, start=period_start, duration=duration, power=0)
                )
                current_action = action
                period_start = start
                duration = 15

        merged.append(SchedulePeriod(action=current_action, start=period_start, duration=duration, power=0))

        # Remove idle actions (None) if any crept in
        merged = [p for p in merged if p.action in ("charge", "discharge")]
        return merged

    def _apply_power_rules(self, periods: List[SchedulePeriod], soc: Optional[float]) -> List[SchedulePeriod]:
        result: List[SchedulePeriod] = []
        max_power = self.config.get("max_inverter_power_w", 8000)
        for period in periods:
            power = (
                self.config.get("default_charge_power_w")
                if period.action == "charge"
                else self.config.get("default_discharge_power_w")
            )

            if period.action == "discharge":
                if soc is not None:
                    if soc <= self.config.get("minimum_discharge_soc_percent", 5.0):
                        logger.info("Skipping discharge at %.1f%% SOC (below minimum)", soc)
                        continue
                    if soc < self.config.get("conservative_soc_threshold_percent", 30.0):
                        power = min(power, self.config.get("min_scaled_power_w", power))

                min_discharge = self.config.get("min_discharge_power_w", 0)
                if power > 0 and power < min_discharge:
                    power = min_discharge

            power = min(max_power, int(power))
            if power <= 0:
                continue

            result.append(
                SchedulePeriod(
                    action=period.action,
                    start=period.start,
                    duration=period.duration,
                    power=power,
                )
            )

        # SAJ limits: max 3 charge, 6 discharge
        charges = [p for p in result if p.action == "charge"]
        discharges = [p for p in result if p.action == "discharge"]
        if len(charges) > 3:
            logger.warning("Truncating charge periods from %d to 3", len(charges))
            charges = charges[:3]
        if len(discharges) > 6:
            logger.warning("Truncating discharge periods from %d to 6", len(discharges))
            discharges = discharges[:6]

        logger.info(
            "Schedule power rules | charges=%d discharges=%d | max_power=%d soc=%s",
            len(charges),
            len(discharges),
            max_power,
            f"{soc:.1f}%" if soc is not None else "n/a",
        )

        return sorted(charges + discharges, key=lambda p: p.start)

    def _build_schedule(self, now: datetime) -> List[SchedulePeriod]:
        prices = self._load_price_curve()
        if not prices:
            return []

        soc = self._get_float_state(self.config.get("battery_soc_sensor_entity_id"))
        window, actions = self._select_action_intervals(prices, now)
        if not window:
            return []

        merged = self._merge_intervals(actions, now)
        schedule = self._apply_power_rules(merged, soc)
        return schedule

    # ---------- Publishing ----------
    def _serialize_schedule(self, schedule: List[SchedulePeriod]) -> Dict[str, List[Dict[str, Any]]]:
        charge: List[Dict[str, Any]] = []
        discharge: List[Dict[str, Any]] = []
        for period in schedule:
            target = charge if period.action == "charge" else discharge
            start_local = period.start.astimezone(self.tz)
            target.append(
                {
                    "start": start_local.strftime("%H:%M"),
                    "duration": int(period.duration),
                    "power": int(period.power),
                }
            )
        return {"charge": charge, "discharge": discharge}

    def _publish_schedule(self, schedule: List[SchedulePeriod]) -> bool:
        payload = self._serialize_schedule(schedule)
        if self.simulation:
            self.last_schedule = schedule
            self.last_schedule_published = datetime.now(self.tz)
            logger.info(
                "[SIMULATION] Would publish schedule: %d charge, %d discharge | payload=%s",
                len(payload["charge"]),
                len(payload["discharge"]),
                payload,
            )
            return True

        ok = self.ha.call_service(
            "mqtt",
            "publish",
            {
                "topic": "battery_api/text/schedule/set",
                "payload": json.dumps(payload),
                "retain": False,
            },
        )
        if ok:
            self.last_schedule = schedule
            self.last_schedule_published = datetime.now(self.tz)
            logger.info("Published schedule: %d charge, %d discharge", len(payload["charge"]), len(payload["discharge"]))
        return ok

    # ---------- Status exposure ----------
    def _next_period(self, action: str) -> Optional[SchedulePeriod]:
        now = datetime.now(self.tz)
        future = [p for p in self.last_schedule if p.action == action and p.start >= now]
        if not future:
            return None
        return sorted(future, key=lambda p: p.start)[0]

    def _current_period(self, now: datetime) -> Optional[SchedulePeriod]:
        for period in self.last_schedule:
            end = period.start + timedelta(minutes=period.duration)
            if period.start <= now < end:
                return period
        return None

    def _update_status(self, adaptive_power: Optional[int]) -> None:
        now = datetime.now(self.tz)
        next_charge = self._next_period("charge")
        next_discharge = self._next_period("discharge")
        status_entity = "sensor.hems_status"

        attrs = {
            "friendly_name": "HEMS Status",
            "next_charge": next_charge.start.isoformat() if next_charge else None,
            "next_charge_power_w": next_charge.power if next_charge else None,
            "next_discharge": next_discharge.start.isoformat() if next_discharge else None,
            "next_discharge_power_w": next_discharge.power if next_discharge else None,
            "last_schedule_publish": self.last_schedule_published.isoformat() if self.last_schedule_published else None,
            "adaptive_power_w": adaptive_power,
        }

        if self.simulation:
            logger.info(
                "[SIMULATION] Status: next_charge=%s %sW | next_discharge=%s %sW | adaptive=%s",
                next_charge.start.isoformat() if next_charge else None,
                next_charge.power if next_charge else None,
                next_discharge.start.isoformat() if next_discharge else None,
                next_discharge.power if next_discharge else None,
                adaptive_power,
            )
        else:
            self.ha.create_or_update_entity(status_entity, state="ok", attributes=attrs, log_success=False)

            if adaptive_power is not None:
                self.ha.create_or_update_entity(
                    "sensor.hems_adaptive_power_w",
                    state=str(adaptive_power),
                    attributes={"friendly_name": "HEMS Adaptive Power", "unit_of_measurement": "W"},
                    log_success=False,
                )

        self.last_status_update = now

    # ---------- Adaptive control ----------
    def _compute_adaptive_target(
        self,
        soc: Optional[float],
        average_power: Optional[float],
        grid_power: Optional[float],
        current_period: Optional[SchedulePeriod],
    ) -> Optional[int]:
        if not current_period or current_period.action != "discharge":
            return None

        if soc is not None and soc <= self.config.get("minimum_discharge_soc_percent", 5.0):
            logger.info("Adaptive pause: SOC %.1f%% <= minimum", soc)
            return 0

        if average_power is None:
            return None

        import_w = max(average_power, 0)
        disable_threshold = self.config.get("adaptive_disable_threshold_w", 1500)
        if import_w < disable_threshold:
            return 0

        target = import_w + self.config.get("adaptive_power_increment_w", 100)
        target = min(target, self.config.get("max_inverter_power_w", 8000))

        if soc is not None and soc < self.config.get("conservative_soc_threshold_percent", 30.0):
            target = min(target, self.config.get("min_scaled_power_w", target))

        min_discharge = self.config.get("min_discharge_power_w", 0)
        target = max(min_discharge, int(target))
        logger.info(
            "Adaptive calc | avg=%.0fW grid=%s soc=%s current=%sW -> target=%dW",
            average_power if average_power is not None else -1,
            f"{grid_power:.0f}" if grid_power is not None else "n/a",
            f"{soc:.1f}%" if soc is not None else "n/a",
            current_period.power,
            target,
        )
        return target

    def _maybe_apply_adaptive(self, now: datetime) -> Optional[int]:
        current = self._current_period(now)
        avg_power = self._get_float_state(self.config.get("average_power_sensor_entity_id"))
        grid_power = self._get_float_state(self.config.get("battery_grid_power_sensor_entity_id"))
        soc = self._get_float_state(self.config.get("battery_soc_sensor_entity_id"))

        adaptive_target = self._compute_adaptive_target(soc, avg_power, grid_power, current)
        if adaptive_target is None:
            return None

        if not current:
            return adaptive_target

        if abs(adaptive_target - current.power) < self.config.get("adaptive_power_increment_w", 100):
            return adaptive_target

        if self.last_adaptive_update and (now - self.last_adaptive_update).total_seconds() < self.config.get(
            "adaptive_power_grace_period_seconds", 60
        ):
            return adaptive_target

        # Update current period power and re-publish schedule
        updated: List[SchedulePeriod] = []
        for period in self.last_schedule:
            if period is current:
                updated.append(
                    SchedulePeriod(action=period.action, start=period.start, duration=period.duration, power=adaptive_target)
                )
            else:
                updated.append(period)

        if self._publish_schedule(updated):
            self.last_adaptive_update = now
            logger.info(
                "Adaptive update applied: %.0f -> %.0f W (avg=%.0fW, soc=%.1f%%)",
                current.power,
                adaptive_target,
                avg_power if avg_power is not None else -1,
                soc if soc is not None else -1,
            )
            self._update_status(adaptive_target)

        return adaptive_target

    # ---------- Opportunistic solar ----------
    def _maybe_opportunistic_solar(self, now: datetime) -> None:
        if not self.config.get("enable_opportunistic_solar", False):
            return

        grid_power = self._get_float_state(self.config.get("battery_grid_power_sensor_entity_id"))
        soc = self._get_float_state(self.config.get("battery_soc_sensor_entity_id"))
        sun_up = self._get_bool_state(self.config.get("sun_entity_id"))

        if grid_power is None or soc is None or sun_up is None:
            return

        if grid_power < -1000 and soc < 99 and sun_up:
            logger.info("Opportunistic solar: export=%.0fW, soc=%.1f%%", grid_power, soc)
            new_charge = SchedulePeriod(
                action="charge",
                start=now,
                duration=60,
                power=min(self.config.get("default_charge_power_w", 8000), self.config.get("max_inverter_power_w", 8000)),
            )
            updated = [new_charge] + [p for p in self.last_schedule if p.start >= now]
            updated = self._apply_power_rules(updated, soc)
            if updated and self._publish_schedule(updated):
                logger.info("Opportunistic solar schedule published")
                self._update_status(adaptive_power=None)

    # ---------- Main loop ----------
    def regenerate_schedule(self, reason: str) -> None:
        now = datetime.now(self.tz)
        if self.last_regeneration:
            elapsed = (now - self.last_regeneration).total_seconds()
            cooldown = self.config.get("schedule_regeneration_cooldown_seconds", 60)
            if elapsed < cooldown:
                logger.debug("Skipping regeneration (cooldown %.0fs remaining)", cooldown - elapsed)
                return

        schedule = self._build_schedule(now)
        if not schedule:
            logger.error("No schedule generated (%s)", reason)
            return

        if self._publish_schedule(schedule):
            self.last_regeneration = now
            self._update_status(adaptive_power=None)
            logger.info(
                "Schedule regenerated (%s) | charge=%d discharge=%d",
                reason,
                len([p for p in schedule if p.action == "charge"]),
                len([p for p in schedule if p.action == "discharge"]),
            )

    def tick(self, run_once: bool = False) -> None:
        now = datetime.now(self.tz)

        # Regenerate on startup, hourly, or daily reload time
        if not self.last_schedule:
            self.regenerate_schedule("startup")
        elif self.config.get("hourly_regeneration", True) and now.minute == 0:
            self.regenerate_schedule("hourly")
        else:
            daily = self.config.get("daily_reload_time", "01:00")
            try:
                daily_hour, daily_minute = [int(x) for x in daily.split(":")]
                if now.hour == daily_hour and now.minute == daily_minute:
                    self.regenerate_schedule("daily reload")
            except Exception:
                logger.debug("Invalid daily_reload_time format: %s", daily)

        adaptive_power = self._maybe_apply_adaptive(now)
        self._maybe_opportunistic_solar(now)

        if run_once or not self.last_status_update or (
            now - self.last_status_update
        ).total_seconds() > self.config.get("status_refresh_minutes", 15) * 60:
            self._update_status(adaptive_power)


def main() -> None:
    config = load_config()
    run_once = get_run_once_mode()
    controller = HemsController(config)

    logger.info(
        "HEMS add-on started | price=%s average_power=%s run_once=%s",
        config.get("price_sensor_entity_id"),
        config.get("average_power_sensor_entity_id"),
        run_once,
    )

    shutdown_event = setup_signal_handlers(logger)
    interval_seconds = int(config.get("adaptive_monitor_interval_minutes", 1) * 60)

    while not shutdown_event.is_set():
        controller.tick(run_once=run_once)
        if run_once:
            break
        sleep_with_shutdown_check(shutdown_event, interval_seconds)

    logger.info("HEMS add-on stopped")


if __name__ == "__main__":
    main()
