"""Shared modules for Home Assistant add-ons.

This package provides common functionality used across all add-ons:

- addon_base: Signal handling, logging setup, main loop utilities
- ha_api: Home Assistant REST API client
- ha_mqtt_discovery: MQTT Discovery for entities with unique_id
- mqtt_setup: MQTT client initialization helper
- config_loader: Configuration loading from JSON/environment
"""

from .addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check, run_addon_loop
from .ha_api import HomeAssistantApi, get_ha_api_config
from .config_loader import load_addon_config, get_env_with_fallback, get_run_once_mode
from .ha_mqtt_discovery import (
    MqttDiscovery,
    EntityConfig,
    NumberConfig,
    SelectConfig,
    ButtonConfig,
    TextConfig,
    get_mqtt_config_from_env,
)

__all__ = [
    # addon_base
    'setup_logging',
    'setup_signal_handlers', 
    'sleep_with_shutdown_check',
    'run_addon_loop',
    # ha_api
    'HomeAssistantApi',
    'get_ha_api_config',
    # config_loader
    'load_addon_config',
    'get_env_with_fallback',
    'get_run_once_mode',
    # ha_mqtt_discovery
    'MqttDiscovery',
    'EntityConfig',
    'NumberConfig',
    'SelectConfig',
    'ButtonConfig',
    'TextConfig',
    'get_mqtt_config_from_env',
]
