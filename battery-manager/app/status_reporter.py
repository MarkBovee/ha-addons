"""MQTT discovery and status reporting helpers."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DEVICE_INFO = {
    "identifiers": ["battery_manager_addon"],
    "name": "Battery Manager",
    "manufacturer": "HA Addons",
    "model": "SAJ Battery Optimizer",
}


def build_entity_configs() -> List[Dict[str, Any]]:
    return [
        {
            "name": "Battery Manager Status",
            "unique_id": "battery_manager_status",
            "state_topic": "battery-manager/sensor/status/state",
            "config_topic": "homeassistant/sensor/battery_manager_status/config",
            "device_class": "enum",
        },
        {
            "name": "Battery Manager Reasoning",
            "unique_id": "battery_manager_reasoning",
            "state_topic": "battery-manager/sensor/reasoning/state",
            "config_topic": "homeassistant/sensor/battery_manager_reasoning/config",
        },
        {
            "name": "Battery Manager Forecast",
            "unique_id": "battery_manager_forecast",
            "state_topic": "battery-manager/sensor/forecast/state",
            "config_topic": "homeassistant/sensor/battery_manager_forecast/config",
        },
        {
            "name": "Battery Manager Price Ranges",
            "unique_id": "battery_manager_price_ranges",
            "state_topic": "battery-manager/sensor/price_ranges/state",
            "config_topic": "homeassistant/sensor/battery_manager_price_ranges/config",
        },
        {
            "name": "Battery Manager Current Action",
            "unique_id": "battery_manager_current_action",
            "state_topic": "battery-manager/sensor/current_action/state",
            "config_topic": "homeassistant/sensor/battery_manager_current_action/config",
        },
    ]


def publish_discovery(mqtt_client: Any, entity_configs: List[Dict[str, Any]]) -> None:
    if mqtt_client is None:
        raise ValueError("mqtt_client is required")

    for config in entity_configs:
        payload = {
            "name": config["name"],
            "unique_id": config["unique_id"],
            "state_topic": config["state_topic"],
            "device": DEVICE_INFO,
            "json_attributes_topic": f"{config['state_topic']}/attributes",
        }
        if "device_class" in config:
            payload["device_class"] = config["device_class"]

        mqtt_client.publish(config["config_topic"], json.dumps(payload, ensure_ascii=False))


def update_entity_state(
    mqtt_client: Any,
    entity_config: Dict[str, Any],
    state: str,
    attributes: Dict[str, Any] | None = None,
    dry_run: bool = False,
) -> None:
    if dry_run:
        logger.info(
            "📝 [Dry-Run] Output state for %s (%s): %s",
            entity_config["name"],
            entity_config["unique_id"],
            state,
        )
        if attributes:
            logger.info("   Attributes: %s", json.dumps(attributes, ensure_ascii=False))
        return

    if mqtt_client is None:
        raise ValueError("mqtt_client is required")

    mqtt_client.publish(entity_config["state_topic"], state)
    if attributes:
        attributes_topic = f"{entity_config['state_topic']}/attributes"
        mqtt_client.publish(attributes_topic, json.dumps(attributes, ensure_ascii=False))
