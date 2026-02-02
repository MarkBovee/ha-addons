"""Home Assistant REST API client for add-ons.

This module provides a unified client for interacting with the Home Assistant
REST API for entity creation, updates, and deletion.

Usage:
    from shared.ha_api import HomeAssistantApi

    ha = HomeAssistantApi()  # Auto-detects Supervisor or uses env vars
    ha.create_or_update_entity("sensor.my_sensor", "42", {"friendly_name": "My Sensor"})
    ha.delete_entity("sensor.old_sensor")
"""

import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class HAState:
    """Type-safe representation of a Home Assistant state."""
    entity_id: str
    state: str
    attributes: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HAState':
        return cls(
            entity_id=data['entity_id'],
            state=data['state'],
            attributes=data.get('attributes', {})
        )


def get_ha_api_config() -> Tuple[str, str]:
    """Get Home Assistant API configuration from environment.
    
    Supports both Supervisor-managed add-ons (SUPERVISOR_TOKEN) and
    standalone development (HA_API_TOKEN, HA_API_URL).
    
    Returns:
        Tuple of (base_url, token)
    """
    token = os.getenv('HA_API_TOKEN') or os.getenv('SUPERVISOR_TOKEN', '')
    base_url = os.getenv('HA_API_URL') or 'http://supervisor/core/api'
    
    # Debug logging to help troubleshoot auth issues
    if token:
        token_preview = token[:10] + "..." if len(token) > 10 else token
        logger.debug("HA API config: url=%s, token=%s (len=%d)", base_url, token_preview, len(token))
    else:
        logger.warning("No HA API token found in environment (checked HA_API_TOKEN and SUPERVISOR_TOKEN)")
    
    return base_url.rstrip('/'), token


class HomeAssistantApi:
    """Client for Home Assistant REST API.
    
    Provides methods for creating, updating, and deleting Home Assistant
    entities via the REST API. Used as a fallback when MQTT Discovery
    is not available.
    
    Note: Entities created via REST API do not have unique_id, so they
    cannot be managed from the HA UI. Use MQTT Discovery for full UI support.
    """
    
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        """Initialize Home Assistant API client.
        
        Args:
            base_url: Base URL for HA API (default: auto-detect from environment)
            token: API token (default: auto-detect from environment)
        """
        if base_url is None or token is None:
            env_url, env_token = get_ha_api_config()
            self.base_url = (base_url or env_url).rstrip('/')
            self.token = token or env_token
        else:
            self.base_url = base_url.rstrip('/')
            self.token = token
        
        self._headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def get_state(self, entity_id: str) -> Optional[HAState]:
        """Get the current state of an entity.
        
        Args:
            entity_id: Entity ID to fetch
            
        Returns:
            HAState object or None if not found/error
        """
        try:
            url = f"{self.base_url}/states/{entity_id}"
            response = requests.get(url, headers=self._headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return HAState.from_dict(data)
            elif response.status_code == 404:
                return None
            else:
                logger.debug("Get state %s returned %d: %s", entity_id, response.status_code, response.text[:100])
                return None
                
        except Exception as e:
            logger.debug("Exception getting state for %s: %s", entity_id, e)
            return None

    def create_or_update_entity(
        self,
        entity_id: str,
        state: str,
        attributes: Dict,
        log_success: bool = True
    ) -> bool:
        """Create or update a Home Assistant entity.
        
        Args:
            entity_id: Entity ID (e.g., sensor.energy_prices_electricity_import_price)
            state: Entity state value
            attributes: Entity attributes dictionary
            log_success: Whether to log successful updates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/states/{entity_id}"
            payload = {'state': state, 'attributes': attributes}
            response = requests.post(url, json=payload, headers=self._headers, timeout=10)
            
            if response.ok:
                if log_success:
                    friendly_name = attributes.get('friendly_name', entity_id)
                    logger.info("Updated entity: %s (%s) = %s", entity_id, friendly_name, state)
                return True
            else:
                if response.status_code == 401:
                    logger.error(
                        "Failed to update %s: 401 Unauthorized. Token present: %s",
                        entity_id, 'YES' if self.token else 'NO'
                    )
                else:
                    logger.error(
                        "Failed to update %s: %d - %s",
                        entity_id, response.status_code, response.text[:200]
                    )
                return False
                
        except Exception as e:
            logger.error("Exception updating %s: %s", entity_id, e, exc_info=True)
            return False
    
    def delete_entity(self, entity_id: str) -> bool:
        """Delete a Home Assistant entity.
        
        Args:
            entity_id: Entity ID to delete
            
        Returns:
            True if deleted, False if not found or error
        """
        try:
            url = f"{self.base_url}/states/{entity_id}"
            response = requests.delete(url, headers=self._headers, timeout=10)
            
            if response.status_code == 200:
                logger.info("Deleted entity: %s", entity_id)
                return True
            elif response.status_code == 404:
                logger.debug("Entity %s not found (already deleted)", entity_id)
                return False
            else:
                logger.debug("Delete %s returned %d: %s", entity_id, response.status_code, response.text[:100])
                return False
                
        except Exception as e:
            logger.debug("Exception deleting %s: %s", entity_id, e)
            return False
    
    def delete_entities(self, entity_ids: List[str]) -> int:
        """Delete multiple entities.
        
        Args:
            entity_ids: List of entity IDs to delete
            
        Returns:
            Number of entities successfully deleted
        """
        deleted_count = 0
        for entity_id in entity_ids:
            if self.delete_entity(entity_id):
                deleted_count += 1
        return deleted_count
    
    def get_entity_state(self, entity_id: str) -> Optional[Dict]:
        """Get current state of an entity.
        
        Args:
            entity_id: Entity ID to query
            
        Returns:
            State dict with 'state' and 'attributes' keys, or None if not found
        """
        # Try direct endpoint first
        try:
            url = f"{self.base_url}/states/{entity_id}"
            response = requests.get(url, headers=self._headers, timeout=10)
            
            if response.ok:
                return response.json()
            elif response.status_code == 404:
                logger.debug("Entity %s not found", entity_id)
                return None
            elif response.status_code == 403:
                # Some Supervisor versions have issues with direct entity state access
                # Fall back to getting all states and filtering
                logger.debug(
                    "Direct state access denied for %s, trying fallback method",
                    entity_id
                )
                return self._get_entity_state_fallback(entity_id)
            else:
                logger.warning(
                    "Failed to get state for %s: %d - %s",
                    entity_id, response.status_code, response.text[:100]
                )
                return None
        except Exception as e:
            logger.error("Exception getting state for %s: %s", entity_id, e)
            return None
    
    def _get_entity_state_fallback(self, entity_id: str) -> Optional[Dict]:
        """Fallback method to get entity state by fetching all states.
        
        Used when direct /states/{entity_id} access is denied (403).
        """
        try:
            url = f"{self.base_url}/states"
            logger.debug("Fallback: fetching all states from %s", url)
            response = requests.get(url, headers=self._headers, timeout=30)
            
            if response.ok:
                all_states = response.json()
                for state in all_states:
                    if state.get('entity_id') == entity_id:
                        logger.debug("Found %s via fallback method", entity_id)
                        return state
                logger.debug("Entity %s not found in all states", entity_id)
                return None
            else:
                logger.warning(
                    "Fallback state fetch failed: %d - %s (url=%s)",
                    response.status_code, response.text[:100], url
                )
                return None
        except Exception as e:
            logger.error("Exception in fallback state fetch: %s", e)
            return None
    
    def call_service(self, domain: str, service: str, data: Dict) -> bool:
        """Call a Home Assistant service.
        
        Args:
            domain: Service domain (e.g., 'water_heater', 'switch')
            service: Service name (e.g., 'set_temperature', 'turn_off')
            data: Service data dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/services/{domain}/{service}"
            response = requests.post(url, json=data, headers=self._headers, timeout=10)
            
            if response.ok:
                logger.debug("Called %s.%s with %s", domain, service, data)
                return True
            else:
                logger.error(
                    "Failed to call %s.%s: %d - %s",
                    domain, service, response.status_code, response.text[:200]
                )
                return False
        except Exception as e:
            logger.error("Exception calling %s.%s: %s", domain, service, e)
            return False
    
    def test_connection(self) -> bool:
        """Test API connection by fetching states endpoint.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            url = f"{self.base_url}/states"
            logger.debug("Testing HA API connection: url=%s, token_len=%d", url, len(self.token) if self.token else 0)
            response = requests.get(
                url,
                headers=self._headers,
                timeout=10
            )
            if response.ok:
                logger.info("Home Assistant API connection successful")
                return True
            else:
                logger.warning(
                    "Home Assistant API test failed: %d - %s (url=%s)",
                    response.status_code, response.text[:200], url
                )
                return False
        except Exception as e:
            logger.warning("Home Assistant API test exception: %s", e)
            return False

    def get_config(self) -> Optional[Dict]:
        """Fetch Home Assistant configuration (timezone, unit system, etc.)."""
        try:
            response = requests.get(f"{self.base_url}/config", headers=self._headers, timeout=10)
            if response.ok:
                return response.json()
            logger.debug("Failed to fetch HA config: %s - %s", response.status_code, response.text[:200])
            return None
        except Exception as exc:
            logger.debug("Exception fetching HA config: %s", exc)
            return None

    def get_timezone(self) -> Optional[str]:
        cfg = self.get_config()
        if cfg:
            return cfg.get("time_zone") or cfg.get("timeZone")
        return None

    def get_error_log(self) -> Optional[str]:
        """Get the Home Assistant error log (home-assistant.log).
        
        Returns:
            The content of the error log as a string, or None if failed.
        """
        try:
            url = f"{self.base_url}/error_log"
            response = requests.get(url, headers=self._headers, timeout=20)
            
            if response.ok:
                return response.text
            else:
                logger.warning(
                    "Failed to fetch error log: %d - %s",
                    response.status_code, response.text[:200]
                )
                return None
        except Exception as e:
            logger.error("Exception fetching error log: %s", e)
            return None
