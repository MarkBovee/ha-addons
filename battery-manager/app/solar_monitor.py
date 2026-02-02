from typing import Any, Dict
import logging
import datetime

# State keys
KEY_PASSIVE_WIN_START = "passive_window_start"
KEY_LAST_SOLAR_CHECK = "last_solar_check"

class SolarMonitor:
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        
        entities = config.get("entities", {})
        self.solar_entity = entities.get("solar_power_entity")
        self.net_entity = entities.get("grid_power_entity")
        
        # Thresholds
        passive_config = config.get("passive_solar", {})
        self.enabled = passive_config.get("enabled", True)
        self.entry_threshold = passive_config.get("entry_threshold", 1000)
        self.exit_threshold = passive_config.get("exit_threshold", 200)
        
        # State
        self.is_passive_active = False
        self.active_since = None

    def check_passive_state(self, ha_api: Any) -> bool:
        """
        Check if we should be in 'Passive Solar' mode (0W charge gap).
        
        Logic:
        - Entry: Net Export > Entry Threshold (e.g. 1000W)
          (Assumes Net Power is negative for Export, so net < -1000)
        - Exit: Net Import > Exit Threshold (e.g. 200W) OR Low Solar (< 200W)
          (Assumes Net Power is positive for Import)
        """
        if not self.config.get("passive_solar_enabled", True):
            return False

        try:
            # Fetch sensor states
            solar_state = ha_api.get_state(self.solar_entity)
            net_state = ha_api.get_state(self.net_entity)

            if not solar_state or not net_state:
                self.logger.warning("Solar or Net power sensors unavailable")
                return False

            try:
                solar_w = float(solar_state.state)
                net_w = float(net_state.state)
            except (ValueError, TypeError):
                # Non-numeric state (unavailable/unknown)
                return False

            # Check Entry Condition
            # Net Export > 1000W (net_w < -1000)
            if not self.is_passive_active:
                if net_w < -self.entry_threshold:
                    self.is_passive_active = True
                    self.active_since = datetime.datetime.now()
                    self.logger.info(f"☀️ Passive Solar Mode ACTIVATED: Net Export {-net_w:.0f}W > {self.entry_threshold}W")
                    return True
            
            # Check Exit Condition
            # Net Import > 200W OR Low Solar < 200W
            else:
                if net_w > self.exit_threshold:
                    self.logger.info(f"☁️ Passive Solar Mode DEACTIVATED: Grid Import {net_w:.0f}W > {self.exit_threshold}W")
                    self.is_passive_active = False
                    self.active_since = None
                    return False
                
                if solar_w < 200: # Low solar hardcoded threshold mentioned in migration doc
                    self.logger.info(f"🌑 Passive Solar Mode DEACTIVATED: Low Solar {solar_w:.0f}W < 200W")
                    self.is_passive_active = False
                    self.active_since = None
                    return False

            return self.is_passive_active

        except Exception as e:
            self.logger.error(f"Error in SolarMonitor: {e}")
            return False
