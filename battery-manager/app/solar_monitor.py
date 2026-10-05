from typing import Any, Callable, Dict, Optional
import datetime
import logging


class SolarMonitor:
    def __init__(
        self,
        config: Dict[str, Any],
        logger: logging.Logger,
        now_fn: Optional[Callable[[], datetime.datetime]] = None,
    ):
        self.config = config
        self.logger = logger
        self._now = now_fn or (lambda: datetime.datetime.now(datetime.timezone.utc))

        entities = config.get("entities", {})
        self.solar_entity = entities.get("solar_power_entity")
        self.net_entity = entities.get("grid_power_entity")

        passive_config = config.get("passive_solar", {})
        self.enabled = passive_config.get("enabled", True)
        self.entry_threshold = passive_config.get("entry_threshold", 1000)
        self.exit_threshold = passive_config.get("exit_threshold", 200)
        self.min_solar_entry_power = passive_config.get("min_solar_entry_power", self.exit_threshold)

        # Hysteresis timers: stop the 0W gap from toggling on its own grid effect.
        self.entry_hold_seconds = passive_config.get("entry_hold_seconds", 300)
        self.exit_hold_seconds = passive_config.get("exit_hold_seconds", 180)
        self.min_active_seconds = passive_config.get("min_active_seconds", 600)

        self.is_passive_active = False
        self.active_since = None
        self._entry_pending_since: Optional[datetime.datetime] = None
        self._exit_pending_since: Optional[datetime.datetime] = None

    def _held(self, since_attr: str, now: datetime.datetime, hold_seconds: float) -> bool:
        """Start/continue a condition timer; True once it held for hold_seconds."""
        since = getattr(self, since_attr)
        if since is None:
            setattr(self, since_attr, now)
            since = now
        return (now - since).total_seconds() >= hold_seconds

    def check_passive_state(self, ha_api: Any) -> bool:
        """Check if we should be in 'Passive Solar' mode (0W charge gap).

        Sign convention (standard P1/grid meter):
            positive = importing from grid
            negative = exporting to grid

        Entry: Exporting > entry_threshold (grid_power < -entry_threshold)
               AND solar generation >= min_solar_entry_power
        Exit:  Importing > exit_threshold (grid_power > exit_threshold) OR low solar
        """
        if not self.enabled:
            return False

        try:
            solar_state = ha_api.get_entity_state(self.solar_entity)
            net_state = ha_api.get_entity_state(self.net_entity)

            if not solar_state or not net_state:
                self.logger.warning("Solar or Net power sensors unavailable")
                return False

            try:
                solar_w = float(solar_state.get("state", 0))
                net_w = float(net_state.get("state", 0))
            except (ValueError, TypeError):
                return False

            now = self._now()

            if not self.is_passive_active:
                self._exit_pending_since = None
                # Activate only on true solar production, not incidental net export.
                if net_w < -self.entry_threshold and solar_w >= self.min_solar_entry_power:
                    if self._held("_entry_pending_since", now, self.entry_hold_seconds):
                        self.is_passive_active = True
                        self.active_since = now
                        self._entry_pending_since = None
                        self.logger.info(
                            "☀️ Passive Solar Mode ACTIVATED: Net Export %.0fW > %sW, Solar %.0fW >= %sW",
                            abs(net_w),
                            self.entry_threshold,
                            solar_w,
                            self.min_solar_entry_power,
                        )
                        return True
                else:
                    self._entry_pending_since = None
            else:
                self._entry_pending_since = None
                importing = net_w > self.exit_threshold
                low_solar = solar_w < self.exit_threshold
                if importing or low_solar:
                    min_active_done = (
                        self.active_since is None
                        or (now - self.active_since).total_seconds() >= self.min_active_seconds
                    )
                    if self._held("_exit_pending_since", now, self.exit_hold_seconds) and min_active_done:
                        if importing:
                            self.logger.info(
                                "☁️ Passive Solar Mode DEACTIVATED: Grid Import %.0fW > %sW",
                                net_w, self.exit_threshold,
                            )
                        else:
                            self.logger.info(
                                "🌑 Passive Solar Mode DEACTIVATED: Low Solar %.0fW < %sW",
                                solar_w, self.exit_threshold,
                            )
                        self.is_passive_active = False
                        self.active_since = None
                        self._exit_pending_since = None
                        return False
                else:
                    self._exit_pending_since = None

            return self.is_passive_active

        except Exception as exc:
            self.logger.error("Error in SolarMonitor: %s", exc)
            return False
