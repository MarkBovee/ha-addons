import json
from datetime import datetime, timedelta, timezone

from app.hems_manager import HEMSScheduleManager


class _Mqtt:
    def __init__(self):
        self.statuses = []

    def is_connected(self):
        return True

    def subscribe(self, topic, callback):
        return True

    def publish_raw(self, topic, payload, retain=True):
        self.statuses.append((topic, payload))
        return True


def _payload():
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(hours=2)
    return json.dumps({
        "periods": [{"start": start.isoformat(), "end": end.isoformat()}],
        "source_id": "legacy-test",
    })


def test_missing_apply_callback_is_not_reported_as_success():
    mqtt = _Mqtt()
    manager = HEMSScheduleManager(mqtt, 1, "Europe/Amsterdam", 12)

    manager._handle_schedule_set(_payload())

    assert manager.has_active_schedule is False
    assert manager._last_command_result == "error"
    assert "No schedule apply boundary" in manager._last_error


def test_failed_apply_callback_does_not_store_schedule():
    mqtt = _Mqtt()
    manager = HEMSScheduleManager(
        mqtt,
        1,
        "Europe/Amsterdam",
        12,
        on_schedule_received=lambda periods: False,
    )

    manager._handle_schedule_set(_payload())

    assert manager.has_active_schedule is False
    assert manager._last_command_result == "error"


def test_successful_apply_callback_stores_schedule():
    mqtt = _Mqtt()
    manager = HEMSScheduleManager(
        mqtt,
        1,
        "Europe/Amsterdam",
        12,
        on_schedule_received=lambda periods: True,
    )

    manager._handle_schedule_set(_payload())

    assert manager.has_active_schedule is True
    assert manager._last_command_result == "success"
