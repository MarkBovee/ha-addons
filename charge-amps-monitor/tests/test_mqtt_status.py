from types import SimpleNamespace

from app.main import publish_automation_sensors_mqtt


class _Mqtt:
    def __init__(self):
        self.discovery = []
        self.states = []

    def publish_sensor(self, config):
        self.discovery.append((config.object_id, config.state))

    def publish_binary_sensor(self, config):
        pass

    def update_state(self, component, object_id, state, attributes=None):
        self.states.append((component, object_id, state))


def test_missing_next_schedule_uses_unavailable_mqtt_state():
    mqtt = _Mqtt()
    status = SimpleNamespace(
        state="waiting_for_prices",
        message="No qualifying charging slots",
        plan_date="2026-09-10",
        attributes={},
        next_start=None,
        next_end=None,
        last_error=None,
    )

    publish_automation_sensors_mqtt(mqtt, status, discovery=True)

    states = dict(mqtt.discovery)
    assert states["next_start"] == "unavailable"
    assert states["next_end"] == "unavailable"
