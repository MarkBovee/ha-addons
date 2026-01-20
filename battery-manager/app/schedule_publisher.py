"""MQTT schedule publishing helpers."""

from __future__ import annotations

import json
from typing import Any, Dict


def convert_to_json(schedule: Dict[str, Any]) -> str:
    """Convert schedule dictionary to JSON string."""

    return json.dumps(schedule, ensure_ascii=False)


def publish_to_mqtt(mqtt_client: Any, schedule: Dict[str, Any], topic: str) -> None:
    """Publish the schedule to MQTT using the provided client."""

    if mqtt_client is None:
        raise ValueError("mqtt_client is required")

    payload = convert_to_json(schedule)
    mqtt_client.publish(topic, payload)
