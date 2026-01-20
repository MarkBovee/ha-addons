import json
import logging
import pytest

from app.status_reporter import build_entity_configs, publish_discovery, update_entity_state

logger = logging.getLogger("battery-manager-tests")


class DummyMqtt:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload):
        self.messages.append((topic, payload))


def test_build_entity_configs():
    logger.info("status_reporter: builds discovery entity configs")
    configs = build_entity_configs()
    assert len(configs) == 5
    assert configs[0]["unique_id"] == "battery_manager_status"


def test_publish_discovery():
    logger.info("status_reporter: publishes discovery payloads")
    mqtt = DummyMqtt()
    configs = build_entity_configs()
    publish_discovery(mqtt, configs)

    assert len(mqtt.messages) == 5
    topic, payload = mqtt.messages[0]
    assert topic.endswith("/config")
    decoded = json.loads(payload)
    assert decoded["unique_id"] == "battery_manager_status"
    assert decoded["json_attributes_topic"].endswith("/attributes")


def test_update_entity_state_with_attributes():
    logger.info("status_reporter: publishes state and attributes")
    mqtt = DummyMqtt()
    configs = build_entity_configs()
    update_entity_state(mqtt, configs[0], "charging", {"power": 8000})

    assert mqtt.messages[0][0].endswith("/state")
    assert mqtt.messages[1][0].endswith("/attributes")


def test_publish_discovery_requires_client():
    logger.info("status_reporter: validates mqtt client presence")
    with pytest.raises(ValueError):
        publish_discovery(None, build_entity_configs())
