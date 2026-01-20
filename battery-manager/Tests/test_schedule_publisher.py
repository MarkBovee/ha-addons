import json
import logging
import pytest

from app.schedule_publisher import convert_to_json, publish_to_mqtt

logger = logging.getLogger("battery-manager-tests")


class DummyMqtt:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload):
        self.messages.append((topic, payload))


def test_convert_to_json():
    logger.info("schedule_publisher: converts schedule to JSON")
    schedule = {"charge": [], "discharge": []}
    assert json.loads(convert_to_json(schedule)) == schedule


def test_publish_to_mqtt():
    logger.info("schedule_publisher: publishes schedule to MQTT")
    mqtt = DummyMqtt()
    schedule = {"charge": [], "discharge": []}
    publish_to_mqtt(mqtt, schedule, "battery_api/text/schedule/set")

    assert mqtt.messages[0][0] == "battery_api/text/schedule/set"


def test_publish_to_mqtt_requires_client():
    logger.info("schedule_publisher: validates mqtt client presence")
    with pytest.raises(ValueError):
        publish_to_mqtt(None, {"charge": []}, "topic")
