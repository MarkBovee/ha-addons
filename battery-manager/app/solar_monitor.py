from typing import Any, Dict
import datetime
import logging


class SolarMonitor:
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger

        entities = config.get("entities", {})
        self.solar_entity = entities.get("solar_power_entity")
        self.net_entity = entities.get("grid_power_entity")

        passive_config = config.get("passive_solar", {})
        self.enabled = passive_config.get("enabled", True)
        self.entry_threshold = passive_config.get("entry_threshold", 1000)
        self.exit_threshold = passive_config.get("exit_threshold", 200)

        self.is_passive_active = False
        self.active_since = None

    def check_passive_state(self, ha_api: Any) -> bool:
        """Check if we should be in 'Passive Solar' mode (0W charge gap).

        Sign convention (standard P1/grid meter):
            positive = importing from grid
            negative = exporting to grid

        Entry: Exporting > entry_threshold (grid_power < -entry_threshold)
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

            if not self.is_passive_active:
                # Exporting heavily: grid_power is negative and exceeds threshold
                if net_w < -self.entry_threshold:
                    self.is_passive_active = True
                    self.active_since = datetime.datetime.now(datetime.timezone.utc)
                    self.logger.info(
                        "☀️ Passive Solar Mode ACTIVATED: Net Export %.0fW > %sW",
                        abs(net_w), self.entry_threshold,
                    )
                    return True
            else:
                # Importing from grid: positive value exceeds exit threshold
                if net_w > self.exit_threshold:
                    self.logger.info(
                        "☁️ Passive Solar Mode DEACTIVATED: Grid Import %.0fW > %sW",
                        net_w, self.exit_threshold,
                    )
                    self.is_passive_active = False
                    self.active_since = None
                    return False

                if solar_w < self.exit_threshold:
                    self.logger.info(
                        "🌑 Passive Solar Mode DEACTIVATED: Low Solar %.0fW < %sW",
                        solar_w, self.exit_threshold,
                    )
                    self.is_passive_active = False
                    self.active_since = None
                    return False

            return self.is_passive_active

        except Exception as exc:
            self.logger.error("Error in SolarMonitor: %s", exc)
            return False
