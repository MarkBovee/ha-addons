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
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


def get_ha_api_config() -> Tuple[str, str]:
    """Get Home Assistant API configuration from environment.
    
    Supports both Supervisor-managed add-ons (SUPERVISOR_TOKEN) and
    standalone development (HA_API_TOKEN, HA_API_URL).
    
    Returns:
        Tuple of (base_url, token)
    """
    token = os.getenv('HA_API_TOKEN') or os.getenv('SUPERVISOR_TOKEN', '')
    base_url = os.getenv('HA_API_URL') or 'http://supervisor/core/api'
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
    
    def create_or_update_entity(
        self,
        entity_id: str,
        state: str,
        attributes: Dict,
        log_success: bool = True
    ) -> bool:
        """Create or update a Home Assistant entity.
        
        Args:
            entity_id: Entity ID (e.g., sensor.ep_price_import)
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
    
    def test_connection(self) -> bool:
        """Test API connection by fetching states endpoint.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/states",
                headers=self._headers,
                timeout=10
            )
            if response.ok:
                logger.info("Home Assistant API connection successful")
                return True
            else:
                logger.warning(
                    "Home Assistant API test failed: %d - %s",
                    response.status_code, response.text[:200]
                )
                return False
        except Exception as e:
            logger.warning("Home Assistant API test exception: %s", e)
            return False
