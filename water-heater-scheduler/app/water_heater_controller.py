"""Water heater controller - manages Home Assistant entity control."""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WaterHeaterController:
    """Control water heater entity via Home Assistant API."""
    
    def __init__(self, ha_api, entity_id: str):
        """Initialize the controller.
        
        Args:
            ha_api: HomeAssistantApi instance
            entity_id: Target water heater entity ID
        """
        self.ha_api = ha_api
        self.entity_id = entity_id
        self._current_state: Optional[Dict[str, Any]] = None
    
    def get_state(self) -> Optional[Dict[str, Any]]:
        """Get current water heater state from Home Assistant.
        
        Returns:
            State dict or None if unavailable
        """
        try:
            state = self.ha_api.get_entity_state(self.entity_id)
            self._current_state = state
            return state
        except Exception as e:
            logger.error("Failed to get water heater state: %s", e)
            return None
    
    @property
    def current_temperature(self) -> Optional[float]:
        """Get current water temperature."""
        if self._current_state:
            attrs = self._current_state.get("attributes", {})
            return attrs.get("current_temperature")
        return None
    
    @property
    def target_temperature(self) -> Optional[float]:
        """Get current target temperature."""
        if self._current_state:
            attrs = self._current_state.get("attributes", {})
            return attrs.get("temperature")
        return None
    
    def set_temperature(self, temperature: int) -> bool:
        """Set target temperature on water heater.
        
        Args:
            temperature: Target temperature in °C
            
        Returns:
            True if successful
        """
        try:
            # Use water_heater.set_temperature service
            self.ha_api.call_service(
                domain="water_heater",
                service="set_temperature",
                data={
                    "entity_id": self.entity_id,
                    "temperature": temperature
                }
            )
            logger.info("Set water heater temperature to %d°C", temperature)
            return True
        except Exception as e:
            logger.error("Failed to set temperature: %s", e)
            return False
    
    def set_operation_mode(self, mode: str = "Manual") -> bool:
        """Set operation mode on water heater.
        
        Args:
            mode: Operation mode (typically "Manual")
            
        Returns:
            True if successful
        """
        try:
            self.ha_api.call_service(
                domain="water_heater",
                service="set_operation_mode",
                data={
                    "entity_id": self.entity_id,
                    "operation_mode": mode
                }
            )
            logger.debug("Set operation mode to %s", mode)
            return True
        except Exception as e:
            logger.error("Failed to set operation mode: %s", e)
            return False
    
    def apply_program(self, target_temp: int) -> bool:
        """Apply a heating program by setting mode and temperature.
        
        Args:
            target_temp: Target temperature
            
        Returns:
            True if successful
        """
        # First set manual mode, then temperature
        mode_ok = self.set_operation_mode("Manual")
        if not mode_ok:
            logger.warning("Could not set manual mode, attempting temperature anyway")
        
        return self.set_temperature(target_temp)


class EntityStateReader:
    """Read entity states from Home Assistant."""
    
    def __init__(self, ha_api):
        """Initialize the reader.
        
        Args:
            ha_api: HomeAssistantApi instance
        """
        self.ha_api = ha_api
    
    def is_entity_on(self, entity_id: Optional[str]) -> bool:
        """Check if an entity is in 'on' state.
        
        Args:
            entity_id: Entity ID to check (returns False if None)
            
        Returns:
            True if entity exists and is 'on'
        """
        if not entity_id:
            return False
        
        try:
            state = self.ha_api.get_entity_state(entity_id)
            if state:
                return state.get("state", "").lower() == "on"
        except Exception as e:
            logger.debug("Could not read entity %s: %s", entity_id, e)
        
        return False
    
    def get_sensor_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get full sensor state including attributes.
        
        Args:
            entity_id: Sensor entity ID
            
        Returns:
            State dict or None
        """
        try:
            return self.ha_api.get_entity_state(entity_id)
        except Exception as e:
            logger.debug("Could not read sensor %s: %s", entity_id, e)
            return None
    
    def turn_off_entity(self, entity_id: Optional[str]) -> bool:
        """Turn off an entity (for bath mode auto-disable).
        
        Args:
            entity_id: Entity to turn off
            
        Returns:
            True if successful
        """
        if not entity_id:
            return False
        
        try:
            # Determine domain from entity_id
            domain = entity_id.split(".")[0]
            
            self.ha_api.call_service(
                domain=domain,
                service="turn_off",
                data={"entity_id": entity_id}
            )
            logger.info("Turned off %s", entity_id)
            return True
        except Exception as e:
            logger.error("Failed to turn off %s: %s", entity_id, e)
            return False
