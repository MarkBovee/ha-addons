"""MQTT Discovery setup helper for add-ons.

This module provides standardized MQTT client initialization with
automatic fallback handling and configuration from environment or config dict.

Usage:
    from shared.mqtt_setup import setup_mqtt_client

    mqtt_client = setup_mqtt_client(
        addon_name="Energy Prices",
        addon_id="energy_prices",
        config=config  # Optional config dict with mqtt_host, mqtt_port, etc.
    )
    
    if mqtt_client:
        # Use MQTT Discovery
        mqtt_client.publish_sensor(...)
    else:
        # Fall back to REST API
        ...
"""

import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .ha_mqtt_discovery import MqttDiscovery

logger = logging.getLogger(__name__)

# Lazy import tracking
_mqtt_module_loaded = False
_MqttDiscovery = None
_EntityConfig = None
_get_mqtt_config_from_env = None
_MQTT_AVAILABLE: Optional[bool] = None


def _load_mqtt_module() -> bool:
    """Lazy load MQTT Discovery module.
    
    Returns:
        True if module loaded successfully, False otherwise
    """
    global _mqtt_module_loaded, _MqttDiscovery, _EntityConfig, _get_mqtt_config_from_env, _MQTT_AVAILABLE
    
    if _MQTT_AVAILABLE is not None:
        return _MQTT_AVAILABLE
    
    try:
        from .ha_mqtt_discovery import MqttDiscovery, EntityConfig, get_mqtt_config_from_env
        _MqttDiscovery = MqttDiscovery
        _EntityConfig = EntityConfig
        _get_mqtt_config_from_env = get_mqtt_config_from_env
        _mqtt_module_loaded = True
        _MQTT_AVAILABLE = True
        return True
    except ImportError as e:
        logger.debug("MQTT Discovery module not available: %s", e)
        _MQTT_AVAILABLE = False
        return False


def is_mqtt_available() -> bool:
    """Check if MQTT Discovery is available.
    
    Returns:
        True if paho-mqtt is installed and module loaded
    """
    return _load_mqtt_module()


def setup_mqtt_client(
    addon_name: str,
    addon_id: str,
    config: Optional[Dict[str, Any]] = None,
    manufacturer: str = "HA Addons",
    model: Optional[str] = None,
    connection_timeout: float = 10.0,
    client_id_suffix: Optional[str] = None,
) -> Optional['MqttDiscovery']:
    """Set up MQTT Discovery client if available.
    
    Attempts to connect to MQTT broker with configuration from:
    1. Provided config dict (mqtt_host, mqtt_port, mqtt_user, mqtt_password)
    2. Environment variables (via get_mqtt_config_from_env)
    
    Args:
        addon_name: Human-readable addon name (e.g., "Energy Prices")
        addon_id: Machine-friendly addon ID (e.g., "energy_prices")
        config: Optional config dict with MQTT settings
        manufacturer: Device manufacturer for HA UI (default: "HA Addons")
        model: Device model for HA UI (default: addon_name)
        connection_timeout: Timeout for MQTT connection in seconds
        client_id_suffix: Optional suffix appended to the MQTT client ID
        
    Returns:
        Connected MqttDiscovery client, or None if unavailable/failed
    """
    if not _load_mqtt_module():
        logger.info("MQTT Discovery not available (paho-mqtt not installed)")
        return None
    
    config = config or {}
    env_config = _get_mqtt_config_from_env()
    
    # Config dict takes precedence, but fall back to env config
    # Treat empty strings as "not configured"
    mqtt_host = config.get('mqtt_host') or os.getenv('MQTT_HOST') or env_config['mqtt_host']
    mqtt_port = config.get('mqtt_port') or int(os.getenv('MQTT_PORT', '0')) or env_config['mqtt_port']
    mqtt_user = config.get('mqtt_user') or os.getenv('MQTT_USER') or env_config['mqtt_user']
    mqtt_password = config.get('mqtt_password') or os.getenv('MQTT_PASSWORD') or env_config['mqtt_password']
    suffix = (
        client_id_suffix
        or config.get('mqtt_client_id_suffix')
        or os.getenv('MQTT_CLIENT_ID_SUFFIX')
    )
    
    logger.info("Attempting MQTT Discovery connection to %s:%d...", mqtt_host, mqtt_port)
    
    try:
        mqtt_client = _MqttDiscovery(
            addon_name=addon_name,
            addon_id=addon_id,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_user=mqtt_user,
            mqtt_password=mqtt_password,
            manufacturer=manufacturer,
            model=model or addon_name,
            client_id_suffix=suffix,
        )
        
        if mqtt_client.connect(timeout=connection_timeout):
            logger.info("MQTT Discovery connected - entities will have unique_id")
            return mqtt_client
        else:
            logger.warning("MQTT connection failed, falling back to REST API")
            return None
            
    except Exception as e:
        logger.warning("MQTT setup failed (%s), falling back to REST API", e)
        return None


def get_entity_config_class():
    """Get EntityConfig class for creating entity configurations.
    
    Returns:
        EntityConfig class, or None if not available
    """
    if _load_mqtt_module():
        return _EntityConfig
    return None
