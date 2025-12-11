"""Configuration loading utilities for Home Assistant add-ons.

This module provides standardized configuration loading from the
/data/options.json file (HA Supervisor pattern) with fallback to
environment variables for local development.

Usage:
    from shared.config_loader import load_addon_config

    config = load_addon_config(
        required_fields=['delivery_area', 'currency'],
        defaults={'timezone': 'CET', 'interval_minutes': 60}
    )
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def load_addon_config(
    config_path: str = '/data/options.json',
    defaults: Optional[Dict[str, Any]] = None,
    required_fields: Optional[List[str]] = None,
    env_prefix: str = ''
) -> Dict[str, Any]:
    """Load add-on configuration from JSON file or environment.
    
    Priority order:
    1. JSON config file (if exists)
    2. Environment variables (as fallback)
    3. Default values
    
    Args:
        config_path: Path to JSON config file (HA Supervisor pattern)
        defaults: Default values for optional fields
        required_fields: List of required field names
        env_prefix: Prefix for environment variables (e.g., 'EP_' for EP_DELIVERY_AREA)
        
    Returns:
        Configuration dictionary
        
    Raises:
        KeyError: If required fields are missing from both config and environment
        json.JSONDecodeError: If config file is invalid JSON
    """
    defaults = defaults or {}
    required_fields = required_fields or []
    config: Dict[str, Any] = {}
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info("Loaded configuration from %s", config_path)
    else:
        logger.warning("Config file %s not found, using environment/defaults", config_path)
    
    # Check required fields, try environment as fallback
    for field in required_fields:
        if field not in config or config[field] is None:
            env_key = f"{env_prefix}{field}".upper()
            env_value = os.getenv(env_key)
            if env_value:
                config[field] = env_value
                logger.debug("Loaded %s from environment variable %s", field, env_key)
            elif field not in defaults:
                raise KeyError(f"Required config field missing: {field} (env: {env_key})")
    
    # Apply defaults for missing optional fields
    for key, value in defaults.items():
        if key not in config or config[key] is None:
            # Try environment variable first
            env_key = f"{env_prefix}{key}".upper()
            env_value = os.getenv(env_key)
            if env_value is not None:
                # Type-cast based on default value type
                config[key] = _cast_env_value(env_value, type(value))
            else:
                config[key] = value
    
    return config


def _cast_env_value(value: str, target_type: type) -> Any:
    """Cast environment variable string to target type.
    
    Args:
        value: String value from environment
        target_type: Target type to cast to
        
    Returns:
        Cast value
    """
    if target_type == bool:
        return value.lower() in ('1', 'true', 'yes', 'on')
    elif target_type == int:
        return int(value)
    elif target_type == float:
        return float(value)
    else:
        return value


def get_env_with_fallback(
    key: str,
    fallback: Any = '',
    cast_type: Optional[type] = None
) -> Any:
    """Get environment variable with fallback and optional type casting.
    
    Args:
        key: Environment variable name
        fallback: Fallback value if not set
        cast_type: Type to cast to (default: infer from fallback type)
        
    Returns:
        Environment value or fallback, optionally cast to specified type
    """
    value = os.getenv(key)
    
    if value is None:
        return fallback
    
    if cast_type is None:
        cast_type = type(fallback) if fallback is not None else str
    
    return _cast_env_value(value, cast_type)


def get_run_once_mode() -> bool:
    """Check if add-on should run once and exit.
    
    Used for testing/debugging. Set RUN_ONCE=1 or RUN_ONCE=true in environment.
    
    Returns:
        True if RUN_ONCE mode is enabled
    """
    return os.getenv('RUN_ONCE', '').lower() in ('1', 'true', 'yes')
